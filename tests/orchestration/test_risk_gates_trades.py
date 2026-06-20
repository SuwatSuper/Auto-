# tests/orchestration/test_risk_gates_trades.py
"""Item 1 (P0-1): Risk gate — ExecutionAgent blocks/allows trades."""
from __future__ import annotations

from decimal import Decimal

import orjson
import pytest
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.rate_limiter import TokenBucket
from orchestration.agents.execution_agent import ExecutionAgent


def _make_exec(breaker: CircuitBreaker, open_positions_fn=None, max_open=1, halts_paper=True) -> tuple[ExecutionAgent, InMemoryEventBus]:
    bus = InMemoryEventBus()
    bucket = TokenBucket(capacity=100, refill_per_sec=100.0)

    class FakeSettings:
        execution_engine = "paper"
        live_trading_confirm = ""
        # Default True here so the breaker-veto tests exercise the halt path; the
        # production default is False (paper keeps trading — gains experience).
        circuit_breaker_halts_paper = halts_paper

    agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=FakeSettings(),
        breaker=breaker,
        rate_limiter=bucket,
        logger=structlog.get_logger("test"),
        open_positions_fn=open_positions_fn,
        max_open_positions=max_open,
    )
    return agent, bus


def _execute_msg(signal: str = "BUY", decision_id: str = "test-001") -> bytes:
    return orjson.dumps({"decision": "EXECUTE", "signal": signal, "decision_id": decision_id})


@pytest.mark.asyncio
async def test_open_breaker_vetoes_trade() -> None:
    """When circuit breaker is open, trade is vetoed (EXECUTION_VETOED published)."""
    breaker = CircuitBreaker(max_consecutive_losses=3)
    breaker.trip("TEST", 0)
    assert breaker.is_open

    agent, bus = _make_exec(breaker)
    approved_q = bus.subscribe("decisions.approved.v1")

    await agent._handle(_execute_msg())

    msg = approved_q.get_nowait()
    data = orjson.loads(msg)
    assert data["type"] == "EXECUTION_VETOED"
    assert "CIRCUIT_BREAKER_OPEN" in data["reasons"]


@pytest.mark.asyncio
async def test_closed_breaker_allows_trade() -> None:
    """When circuit breaker is closed, decision is forwarded."""
    breaker = CircuitBreaker(max_consecutive_losses=3)
    assert not breaker.is_open

    agent, bus = _make_exec(breaker)
    approved_q = bus.subscribe("decisions.approved.v1")

    await agent._handle(_execute_msg())

    msg = approved_q.get_nowait()
    data = orjson.loads(msg)
    assert data.get("decision") == "EXECUTE"


@pytest.mark.asyncio
async def test_consecutive_losses_trip_breaker_and_veto() -> None:
    """After N consecutive losses, breaker trips and new trades are vetoed."""
    breaker = CircuitBreaker(max_consecutive_losses=3)
    for _ in range(3):
        breaker.record_trade(Decimal("-100"))

    assert breaker.is_open

    agent, bus = _make_exec(breaker)
    approved_q = bus.subscribe("decisions.approved.v1")

    await agent._handle(_execute_msg(decision_id="after-trip"))

    msg = approved_q.get_nowait()
    data = orjson.loads(msg)
    assert data["type"] == "EXECUTION_VETOED"


@pytest.mark.asyncio
async def test_paper_keeps_trading_through_open_breaker() -> None:
    """Default (circuit_breaker_halts_paper=False): a tripped breaker must NOT halt
    PAPER trading — the sandbox keeps trading to gain experience. The trade is
    forwarded (EXECUTE), not vetoed."""
    breaker = CircuitBreaker(max_consecutive_losses=3)
    for _ in range(3):
        breaker.record_trade(Decimal("-100"))
    assert breaker.is_open  # streak still tripped it (for display)

    agent, bus = _make_exec(breaker, halts_paper=False)  # production default
    approved_q = bus.subscribe("decisions.approved.v1")

    await agent._handle(_execute_msg(decision_id="paper-through-breaker"))

    data = orjson.loads(approved_q.get_nowait())
    assert data.get("decision") == "EXECUTE"  # forwarded, NOT vetoed
    assert data.get("type") != "EXECUTION_VETOED"


@pytest.mark.asyncio
async def test_paper_trader_no_longer_reads_raw_decisions() -> None:
    """PaperTraderAgent subscribes to approved topic, not raw decisions.v1."""
    from domain.portfolio.treasury import TreasuryLimits
    from infrastructure.state.in_memory_store import InMemoryStateStore
    from orchestration.agents.paper_trader import PaperTraderAgent, TradeParams
    from orchestration.agents.treasury_agent import TreasuryAgent

    bus = InMemoryEventBus()
    log = structlog.get_logger("test")
    limits = TreasuryLimits(
        initial_capital=Decimal("10000"),
        survival_floor_pct=Decimal("70"),
        max_daily_loss_pct=Decimal("5"),
    )
    store = InMemoryStateStore()
    treasury = TreasuryAgent(bus, "treasury.v1", log, limits, store)
    params = TradeParams()
    trader = PaperTraderAgent(
        bus, "decisions.approved.v1", "prices.v1", "paper.events.v1",
        log, treasury, params, store,
    )
    assert trader._decisions_topic == "decisions.approved.v1"
    assert trader._decisions_topic != "decisions.v1"


@pytest.mark.asyncio
async def test_position_cap_blocks_second_buy() -> None:
    """When a position is already open, a second BUY is rejected."""
    breaker = CircuitBreaker(max_consecutive_losses=5)
    open_count = 1  # simulate open position

    agent, bus = _make_exec(breaker, open_positions_fn=lambda: open_count, max_open=1)
    approved_q = bus.subscribe("decisions.approved.v1")

    await agent._handle(_execute_msg(signal="BUY", decision_id="second-buy"))

    msg = approved_q.get_nowait()
    data = orjson.loads(msg)
    assert data["type"] == "EXECUTION_VETOED"
    assert "POSITION_CAP_REACHED" in data["reasons"]
