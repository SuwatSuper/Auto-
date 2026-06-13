# Tests — live order routing (gated) + sizing/cap builder
from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal

import orjson
import pytest
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.rate_limiter import TokenBucket
from orchestration.agents.execution_agent import ExecutionAgent
from orchestration.runtime import PipelineRuntime

_LIVE = "I_ACCEPT_REAL_MONEY_RISK"


class _MockGateway:
    def __init__(self) -> None:
        self.bids: list[tuple[str, str, str]] = []
        self.asks: list[tuple[str, str, str]] = []

    async def place_bid(self, sym: str, amount: str, rate: str, typ: str = "limit") -> dict[str, object]:
        self.bids.append((sym, amount, rate))
        return {"error": 0, "result": {"id": 1}}

    async def place_ask(self, sym: str, amount: str, rate: str, typ: str = "limit") -> dict[str, object]:
        self.asks.append((sym, amount, rate))
        return {"error": 0, "result": {"id": 2}}


async def _run_one(agent: ExecutionAgent, bus: InMemoryEventBus, payload: bytes) -> None:
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    try:
        await bus.publish("decisions.v1", b"k", payload)
        await asyncio.sleep(0.2)
    finally:
        await agent.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _agent(bus, gw, settings, order_fn):  # type: ignore[no-untyped-def]
    return ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=settings,
        breaker=CircuitBreaker(),
        rate_limiter=TokenBucket(capacity=10, refill_per_sec=100.0),
        logger=structlog.get_logger("t"),
        rest_gateway=gw,
        live_order_fn=order_fn,
    )


@pytest.mark.asyncio
async def test_live_order_placed_when_gates_open() -> None:
    bus = InMemoryEventBus()
    gw = _MockGateway()
    settings = Settings(training_mode=False, execution_engine="live", live_trading_confirm=_LIVE, persist_state=False)
    spec = {"action": "bid", "symbol": "thb_btc", "amount": "100.00", "rate": "1500000"}
    agent = _agent(bus, gw, settings, lambda _d: spec)
    await _run_one(agent, bus, orjson.dumps({"decision": "EXECUTE", "signal": "BUY"}))
    assert gw.bids == [("thb_btc", "100.00", "1500000")]
    assert agent.live_orders_placed == 1


@pytest.mark.asyncio
async def test_no_live_order_when_gate_closed() -> None:
    bus = InMemoryEventBus()
    gw = _MockGateway()
    # engine paper -> live gate closed
    settings = Settings(training_mode=False, execution_engine="paper", persist_state=False)
    agent = _agent(bus, gw, settings, lambda _d: {"action": "bid", "symbol": "x", "amount": "1", "rate": "1"})
    await _run_one(agent, bus, orjson.dumps({"decision": "EXECUTE", "signal": "BUY"}))
    assert gw.bids == [] and gw.asks == []
    assert agent.live_orders_placed == 0


@pytest.mark.asyncio
async def test_live_order_skipped_when_spec_none() -> None:
    bus = InMemoryEventBus()
    gw = _MockGateway()
    settings = Settings(training_mode=False, execution_engine="live", live_trading_confirm=_LIVE, persist_state=False)
    agent = _agent(bus, gw, settings, lambda _d: None)  # nothing to place
    await _run_one(agent, bus, orjson.dumps({"decision": "EXECUTE", "signal": "BUY"}))
    assert gw.bids == [] and agent.live_orders_placed == 0


# ── sizing + single-order cap ────────────────────────────────────────

def _rt() -> PipelineRuntime:
    rt = PipelineRuntime(settings=Settings(training_mode=False, persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    return rt


def test_build_live_order_buy_sizes_and_caps() -> None:
    rt = _rt()
    assert rt._trader is not None
    rt._trader.mark_price = Decimal("1500000")
    rt._max_single_order_thb = Decimal("50")  # hard cap
    spec = rt._build_live_order({"decision": "EXECUTE", "signal": "BUY", "symbol": "thb_btc"})
    assert spec is not None
    assert spec["action"] == "bid"
    # notional clamped to the 50 THB cap
    assert Decimal(spec["amount"]) <= Decimal("50")
    assert spec["rate"] == "1500000"
    # R-1: orders default to market type so entries/stops actually fill
    assert spec["typ"] == "market"


def test_build_live_order_sell_uses_position_qty() -> None:
    rt = _rt()
    assert rt._trader is not None
    rt._trader.mark_price = Decimal("1500000")
    # no position -> SELL yields None
    assert rt._build_live_order({"signal": "SELL"}) is None
