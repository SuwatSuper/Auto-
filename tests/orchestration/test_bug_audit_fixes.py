# Tests — bug-audit fixes at the orchestration layer:
#   C2  ambiguous live-order result halts the engine (+ alert); a plain
#       exchange rejection does not.
#   M4  a resting LIMIT order with no confirmed fill is NOT mirrored as a held
#       paper position.
#   M1  arming live is refused unless real capital backstops are set.
#   H2  a persisted live flag is re-validated on restart and dropped to paper
#       when the arm-time invariants no longer hold.
#   M3  two concurrent manual BUY clicks place only ONE real bid.
#   L2  releasing a reservation rolls back the per-day entry counters.
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


class _RaisingGateway:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def place_bid(self, *a: object, **k: object) -> dict[str, object]:
        self.calls += 1
        raise self.exc

    async def place_ask(self, *a: object, **k: object) -> dict[str, object]:
        self.calls += 1
        raise self.exc


class _AckGateway:
    """Returns an order id but NO fill fields (rec/amt) — a resting limit."""

    def __init__(self) -> None:
        self.bids: list[tuple[object, ...]] = []

    async def place_bid(self, sym: object, amount: object, rate: object, typ: object = "limit") -> dict[str, object]:
        self.bids.append((sym, amount, rate, typ))
        return {"error": 0, "result": {"id": 1}}


def _exec_agent(bus: InMemoryEventBus, gw: object, breaker: CircuitBreaker,
                spec: dict[str, str], alerts: list[tuple[str, str]]) -> ExecutionAgent:
    return ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=Settings(execution_engine="live", live_trading_confirm=_LIVE, persist_state=False),
        breaker=breaker,
        rate_limiter=TokenBucket(capacity=10, refill_per_sec=100.0),
        logger=structlog.get_logger("t"),
        rest_gateway=gw,
        live_order_fn=lambda _d: spec,
        alert_fn=lambda m, lvl: alerts.append((m, lvl)),
    )


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


_BID_SPEC = {"action": "bid", "symbol": "thb_btc", "amount": "100.00", "rate": "1500000", "typ": "market"}


@pytest.mark.asyncio
async def test_c2_ambiguous_order_halts_engine_and_alerts() -> None:
    bus = InMemoryEventBus()
    breaker = CircuitBreaker(max_consecutive_losses=5)
    alerts: list[tuple[str, str]] = []
    gw = _RaisingGateway(TimeoutError("read timed out"))  # transport-ambiguous
    agent = _exec_agent(bus, gw, breaker, dict(_BID_SPEC), alerts)
    await _run_one(agent, bus, orjson.dumps({"decision": "EXECUTE", "signal": "BUY"}))
    assert gw.calls == 1
    assert breaker.is_open is True  # engine halted for manual reconciliation
    assert alerts and alerts[-1][1] == "critical"


@pytest.mark.asyncio
async def test_c2_exchange_rejection_does_not_halt() -> None:
    from infrastructure.gateway.bitkub_rest import BitkubApiError  # noqa: PLC0415
    bus = InMemoryEventBus()
    breaker = CircuitBreaker(max_consecutive_losses=5)
    alerts: list[tuple[str, str]] = []
    gw = _RaisingGateway(BitkubApiError(11, "insufficient balance"))  # reached + rejected
    agent = _exec_agent(bus, gw, breaker, dict(_BID_SPEC), alerts)
    await _run_one(agent, bus, orjson.dumps({"decision": "EXECUTE", "signal": "BUY"}))
    assert gw.calls == 1
    assert breaker.is_open is False  # a clean rejection means no fill → keep trading
    assert alerts == []


@pytest.mark.asyncio
async def test_m4_resting_limit_is_not_mirrored() -> None:
    bus = InMemoryEventBus()
    breaker = CircuitBreaker(max_consecutive_losses=5)
    approved = bus.subscribe("decisions.approved.v1")
    gw = _AckGateway()
    spec = {"action": "bid", "symbol": "thb_btc", "amount": "100.00", "rate": "1500000", "typ": "limit"}
    agent = _exec_agent(bus, gw, breaker, spec, [])
    await _run_one(agent, bus, orjson.dumps({"decision": "EXECUTE", "signal": "BUY"}))
    assert gw.bids and agent.live_orders_placed == 1  # the real order WAS placed
    # …but nothing was mirrored to the paper trader (no invented position).
    assert approved.empty()


# ── runtime-level fixes ─────────────────────────────────────────────────
def _fresh_runtime(**kw: object) -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, **kw),  # type: ignore[arg-type]
        logger=structlog.get_logger("t"),
    )
    rt.agents = rt._make_agents()
    return rt


def _set_backstops(rt: PipelineRuntime) -> None:
    from domain.portfolio.treasury import TreasuryLimits  # noqa: PLC0415
    assert rt._circuit_breaker is not None and rt._treasury is not None
    rt._circuit_breaker.update_threshold(5)
    rt._treasury.update_limits(TreasuryLimits(
        initial_capital=rt._initial_capital,
        survival_floor_pct=Decimal("70"),
        max_daily_loss_pct=Decimal("5"),
    ))


def test_m1_arm_refused_without_backstops() -> None:
    rt = _fresh_runtime()
    rt._max_single_order_thb = Decimal("500")  # cap set, but backstops still off
    ok, payload = rt.set_execution_mode("live", confirm=_LIVE)
    assert ok is False
    assert payload.get("field") in {"max_consecutive_losses", "max_daily_loss_pct"}
    # once real backstops are set, arming succeeds
    _set_backstops(rt)
    ok2, _ = rt.set_execution_mode("live", confirm=_LIVE)
    assert ok2 is True


def test_h2_persisted_live_is_revalidated_on_restart() -> None:
    rt = _fresh_runtime()
    # Simulate a persisted live flag (as .env would carry) but WITHOUT the
    # arm-time invariants (no per-order cap) — a reboot must not stay armed.
    rt.settings.execution_engine = "live"  # type: ignore[attr-defined]
    rt.settings.live_trading_confirm = _LIVE  # type: ignore[attr-defined]
    rt._max_single_order_thb = Decimal("0")
    rt._revalidate_persisted_execution_mode()
    assert rt.settings.execution_engine == "paper"  # dropped to paper, must re-arm
    assert rt.settings.live_trading_confirm == ""


def test_l2_release_reservation_rolls_back_daily_counters() -> None:
    rt = _fresh_runtime(initial_capital="100000")
    tr = rt._treasury
    assert tr is not None
    dec = tr.request_open(order_cost=Decimal("500"), worst_case=Decimal("50"),
                          open_market_value=Decimal("0"))
    assert dec.approved
    assert tr.entries_today == 1 and tr.approved_count == 1
    tr.release_reservation(Decimal("500"))  # the open failed after approval
    assert tr.entries_today == 0 and tr.approved_count == 0  # quota not burned


class _ManualGateway:
    def __init__(self) -> None:
        self.bids: list[tuple[object, ...]] = []

    async def place_bid(self, sym: object, amount: object, rate: object, typ: object = "market") -> dict[str, object]:
        await asyncio.sleep(0.02)  # widen the race window
        self.bids.append((sym, amount, rate, typ))
        return {"error": 0, "result": {"id": len(self.bids)}}


@pytest.mark.asyncio
async def test_m9_restore_does_not_disable_kelly() -> None:
    rt = _fresh_runtime()
    rt.settings.kelly_sizing_enabled = True  # type: ignore[attr-defined]
    # A machine-driven restore carries risk_per_trade_pct but must NOT be
    # mistaken for an operator hand-setting it (which disables Kelly).
    await rt.update_risk_settings({"risk_per_trade_pct": "1.5"}, from_restore=True)
    assert rt.settings.kelly_sizing_enabled is True
    # A genuine operator edit still disables Kelly (their typed % must stick).
    await rt.update_risk_settings({"risk_per_trade_pct": "2.0"})
    assert rt.settings.kelly_sizing_enabled is False


@pytest.mark.asyncio
async def test_m3_concurrent_manual_buys_place_one_real_bid() -> None:
    rt = _fresh_runtime(initial_capital="5000000")
    assert rt._trader is not None
    rt._trader.mark_price = Decimal("1500000")
    rt.settings.execution_engine = "live"  # type: ignore[attr-defined]
    rt.settings.live_trading_confirm = _LIVE  # type: ignore[attr-defined]
    rt._max_single_order_thb = Decimal("1000")
    gw = _ManualGateway()
    rt._rest_gateway = gw
    rt.agents["risk_gate"].set_rest_gateway(gw)  # type: ignore[attr-defined]
    assert rt._live_orders_armed() is True
    # Two operator BUY clicks fired concurrently.
    await asyncio.gather(rt.manual_order("BUY"), rt.manual_order("BUY"))
    assert len(gw.bids) == 1  # the lock prevented a double real order
