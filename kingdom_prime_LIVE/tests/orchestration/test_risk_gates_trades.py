"""P0-1: Verify that the ExecutionAgent circuit-breaker and position-limit gates
actually block paper trades.

Acceptance criteria (from MASTER_FIX_PROMPT):
- With the circuit breaker open, an EXECUTE decision produces NO new paper position
  and EXECUTION_VETOED is emitted to decisions.approved.v1.
- With the breaker closed, the decision is forwarded and the paper trader can open
  a position.
- PaperTrader no longer subscribes to raw decisions.v1 — it only sees
  decisions.approved.v1.
- After N consecutive losing trades the breaker trips and subsequent decisions are
  vetoed.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import orjson
import pytest
import structlog

from domain.portfolio.treasury import TreasuryLimits
from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.rate_limiter import TokenBucket
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.agents.execution_agent import ExecutionAgent
from orchestration.agents.paper_trader import PaperTraderAgent, TradeParams
from orchestration.agents.treasury_agent import TreasuryAgent


def _make_components(
    max_consecutive_losses: int = 5,
    max_open_positions: int = 1,
) -> tuple[InMemoryEventBus, CircuitBreaker, ExecutionAgent, PaperTraderAgent]:
    bus = InMemoryEventBus()
    log = structlog.get_logger("test")
    breaker = CircuitBreaker(max_consecutive_losses=max_consecutive_losses)
    bucket = TokenBucket(capacity=100, refill_per_sec=1000.0)

    store = InMemoryStateStore()
    limits = TreasuryLimits(
        initial_capital=Decimal("100000"),
        survival_floor_pct=Decimal("70"),
        max_daily_loss_pct=Decimal("5"),
    )
    treasury = TreasuryAgent(bus, "treasury.v1", log, limits, store)

    params = TradeParams(
        risk_per_trade_pct="1.0",
        stop_pct="1.0",
        take_profit_pct="1.5",
        fee_taker_bps="25",
        slippage_bps="5",
    )

    trader = PaperTraderAgent(
        bus, "decisions.approved.v1", "prices.v1", "paper.events.v1",
        log, treasury, params, store, circuit_breaker=breaker
    )

    exec_agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=type("S", (), {"execution_engine": "paper", "live_trading_confirm": ""})(),
        breaker=breaker,
        rate_limiter=bucket,
        logger=log,
        get_open_positions=lambda: trader.open_positions(),
        max_open_positions=max_open_positions,
    )
    return bus, breaker, exec_agent, trader


@pytest.mark.asyncio
async def test_circuit_breaker_open_vetoes_execute_decision() -> None:
    """Open circuit breaker → EXECUTE is rejected, EXECUTION_VETOED published."""
    bus, breaker, exec_agent, trader = _make_components()

    veto_queue = bus.subscribe("decisions.approved.v1")
    approved_queue = bus.subscribe("decisions.approved.v1")

    task = asyncio.create_task(exec_agent.start())
    await asyncio.sleep(0.02)  # let agent start

    # Trip the breaker manually
    breaker.trip("test", 0)
    assert breaker.is_open

    # Send an EXECUTE decision
    decision = orjson.dumps({
        "decision": "EXECUTE",
        "signal": "BUY",
        "decision_id": "test-001",
    })
    await bus.publish("decisions.v1", b"k", decision)
    await asyncio.sleep(0.05)

    await exec_agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Should have published a veto
    assert not veto_queue.empty(), "Expected EXECUTION_VETOED on approved topic"
    veto = orjson.loads(veto_queue.get_nowait())
    assert veto["type"] == "EXECUTION_VETOED"
    assert "CIRCUIT_BREAKER_OPEN" in veto["reasons"]

    # Paper trader position must still be None
    assert trader.position is None
    assert exec_agent.rejected_count >= 1


@pytest.mark.asyncio
async def test_circuit_breaker_closed_allows_execution() -> None:
    """With breaker closed, EXECUTE is forwarded to decisions.approved.v1."""
    bus, breaker, exec_agent, _trader = _make_components()

    approved_q = bus.subscribe("decisions.approved.v1")

    task = asyncio.create_task(exec_agent.start())
    await asyncio.sleep(0.02)

    assert not breaker.is_open

    decision = orjson.dumps({
        "decision": "EXECUTE",
        "signal": "BUY",
        "decision_id": "test-open-001",
    })
    await bus.publish("decisions.v1", b"k", decision)
    await asyncio.sleep(0.05)

    await exec_agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Message should arrive on approved topic (not vetoed)
    assert not approved_q.empty(), "Expected forwarded decision on approved topic"
    msg = orjson.loads(approved_q.get_nowait())
    # Either the original decision forwarded or a veto — should be the decision
    assert msg.get("decision") == "EXECUTE" or msg.get("type") != "EXECUTION_VETOED"


@pytest.mark.asyncio
async def test_max_open_positions_blocks_additional_buy() -> None:
    """Once open_positions() >= max_open_positions, BUY → EXECUTION_VETOED."""
    bus, breaker, exec_agent, trader = _make_components(max_open_positions=1)

    # Inject a fake open position
    from domain.trading.paper import PaperPosition
    trader.position = PaperPosition(
        symbol="THB_BTC",
        qty=Decimal("0.001"),
        entry_price=Decimal("1500000"),
        stop_price=Decimal("1485000"),
        take_profit_price=Decimal("1522500"),
        entry_fee=Decimal("37.50"),
        opened_ms=1_700_000_000_000,
    )
    assert trader.open_positions() == 1

    approved_q = bus.subscribe("decisions.approved.v1")

    task = asyncio.create_task(exec_agent.start())
    await asyncio.sleep(0.02)

    decision = orjson.dumps({
        "decision": "EXECUTE",
        "signal": "BUY",
        "decision_id": "test-pos-limit-001",
    })
    await bus.publish("decisions.v1", b"k", decision)
    await asyncio.sleep(0.05)

    await exec_agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert not approved_q.empty()
    veto = orjson.loads(approved_q.get_nowait())
    assert veto["type"] == "EXECUTION_VETOED"
    assert "MAX_OPEN_POSITIONS_EXCEEDED" in veto["reasons"]
    assert exec_agent.rejected_count >= 1


def test_paper_trader_subscribes_to_approved_topic_not_raw() -> None:
    """PaperTrader must not subscribe to raw decisions.v1 — only approved.v1."""
    bus, _, _, trader = _make_components()
    # Verify the _decisions_topic field is the approved topic
    assert trader._decisions_topic == "decisions.approved.v1", (
        f"PaperTrader subscribes to {trader._decisions_topic!r}, "
        "expected 'decisions.approved.v1'"
    )


@pytest.mark.asyncio
async def test_consecutive_losses_trip_breaker_and_veto_trades() -> None:
    """After max_consecutive_losses losing trades, breaker auto-trips and
    subsequent EXECUTE decisions are vetoed."""
    bus, breaker, exec_agent, trader = _make_components(max_consecutive_losses=3)

    # Simulate 3 losing trades recorded directly on the breaker
    for _ in range(3):
        breaker.record_trade(Decimal("-100"))

    assert breaker.is_open, "Breaker should have tripped after 3 consecutive losses"

    approved_q = bus.subscribe("decisions.approved.v1")

    task = asyncio.create_task(exec_agent.start())
    await asyncio.sleep(0.02)

    decision = orjson.dumps({
        "decision": "EXECUTE",
        "signal": "BUY",
        "decision_id": "test-losses-001",
    })
    await bus.publish("decisions.v1", b"k", decision)
    await asyncio.sleep(0.05)

    await exec_agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert not approved_q.empty()
    veto = orjson.loads(approved_q.get_nowait())
    assert veto["type"] == "EXECUTION_VETOED"
    assert "CIRCUIT_BREAKER_OPEN" in veto["reasons"]
