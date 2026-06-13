# Layer 2 — Orchestration (tests/orchestration/test_paper_pipeline)
"""Paper-trading pipeline + watchdog + persistence tests.

Key invariant pinned here (money conservation):
    cash_after_close == initial_capital + trade.pnl
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import orjson
import pytest
import structlog

from domain.portfolio.treasury import TreasuryLimits, VetoReason
from domain.trading.paper import ClosedTrade, ExitReason
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.state.sqlite_store import SqliteStateStore
from orchestration.agents.paper_trader import PaperTraderAgent, TradeParams
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.runtime import PipelineRuntime

D = Decimal
_LOG = structlog.get_logger("test")


def _limits() -> TreasuryLimits:
    return TreasuryLimits(initial_capital=D("1000"))


def _mk(bus: InMemoryEventBus, store=None):  # type: ignore[no-untyped-def]
    treasury = TreasuryAgent(bus, "treasury.v1", _LOG, _limits(), store)
    trader = PaperTraderAgent(
        bus, "decisions.v1", "prices.v1", "paper.events.v1", _LOG, treasury, TradeParams(), store
    )
    return treasury, trader


async def _until(cond, timeout: float = 3.0):  # type: ignore[no-untyped-def]
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached in time")


async def _drive(bus: InMemoryEventBus, topic: str, payload: dict, cond, timeout: float = 3.0):  # type: ignore[no-untyped-def]
    """Publish repeatedly until cond() holds.

    The in-memory bus has no replay: a message published before the agent's
    subscribe is silently lost. Re-publishing (all our messages are idempotent
    for the asserted condition) removes the startup race deterministically.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    raw = orjson.dumps(payload)
    while asyncio.get_event_loop().time() < deadline:
        await bus.publish(topic, b"t", raw)
        if cond():
            return
        await asyncio.sleep(0.03)
    raise AssertionError(f"condition not reached driving {topic}")


async def _drive_price(bus, trader, price: str, cond=None, timeout: float = 3.0):  # type: ignore[no-untyped-def]
    target = D(price)
    check = cond if cond is not None else (lambda: trader.mark_price == target)
    await _drive(bus, "prices.v1", {"price": price, "ts_ms": 1}, check, timeout)


async def _send_decision(bus, signal: str, cond, timeout: float = 3.0):  # type: ignore[no-untyped-def]
    """Publish exactly ONE decision, then await cond.

    Must be called only after a successful _drive_price: both queues are
    subscribed before the trader loop processes anything, so once any price
    is received, the decisions subscription provably exists — a single
    publish cannot be lost, and no stale duplicate decisions linger to
    reopen positions behind the test's back.
    """
    await bus.publish(
        "decisions.v1", b"d", orjson.dumps({"decision": "EXECUTE", "signal": signal})
    )
    await _until(cond, timeout)


@pytest.mark.asyncio
async def test_full_trade_cycle_stop_loss_conserves_money() -> None:
    bus = InMemoryEventBus()
    treasury, trader = _mk(bus)
    task = asyncio.create_task(trader.start())
    try:
        await _drive_price(bus, trader, "1500000")
        await _send_decision(bus, "BUY", lambda: trader.position is not None)

        pos = trader.position
        assert pos is not None
        # H1: bracket attached atomically
        assert pos.stop_price < pos.entry_price < pos.take_profit_price
        # treasury reserved exactly notional + entry fee
        order_cost = pos.qty * pos.entry_price + pos.entry_fee
        assert treasury.cash == D("1000") - order_cost
        assert treasury.approved_count == 1

        # crash through the stop → close
        await _drive_price(bus, trader, "1480000", cond=lambda: trader.trades_closed >= 1)
        assert trader.position is None
        trade = trader.last_trade
        assert trade is not None and trade.reason == ExitReason.STOP_LOSS
        assert trade.pnl < 0  # H2: the loss is real and counted
        # money conservation: all cash back except the realized loss
        assert treasury.cash == D("1000") + trade.pnl
        assert treasury.losses == 1 and treasury.wins == 0
        assert trader.trades_closed == 1
        assert treasury.win_rate() == 0.0
    finally:
        await trader.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_take_profit_cycle_books_a_win() -> None:
    bus = InMemoryEventBus()
    treasury, trader = _mk(bus)
    task = asyncio.create_task(trader.start())
    try:
        await _drive_price(bus, trader, "1500000")
        await _send_decision(bus, "BUY", lambda: trader.position is not None)
        await _drive_price(bus, trader, "1600000", cond=lambda: trader.trades_closed >= 1)
        assert trader.position is None
        trade = trader.last_trade
        assert trade is not None and trade.reason == ExitReason.TAKE_PROFIT
        assert trade.pnl > 0
        assert treasury.cash == D("1000") + trade.pnl
        assert treasury.wins == 1
    finally:
        await trader.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_opposite_signal_closes_and_emergency_flatten() -> None:
    bus = InMemoryEventBus()
    treasury, trader = _mk(bus)
    task = asyncio.create_task(trader.start())
    try:
        await _drive_price(bus, trader, "1500000")
        await _send_decision(bus, "BUY", lambda: trader.position is not None)
        await _send_decision(bus, "SELL", lambda: trader.position is None)
        assert trader.last_trade is not None
        assert trader.last_trade.reason == ExitReason.OPPOSITE_SIGNAL

        # reopen then emergency flatten
        await _send_decision(bus, "BUY", lambda: trader.position is not None)
        await trader.flatten()
        assert trader.position is None
        assert trader.last_trade.reason == ExitReason.EMERGENCY
        # conservation across two closed trades
        total_pnl = treasury.realized_pnl
        assert treasury.cash == D("1000") + total_pnl
    finally:
        await trader.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_trailing_stop_locks_profit_above_entry() -> None:
    """The trailing-stop overlay can sit ABOVE entry (lock profit) and fires
    before the fixed bracket stop, closing the trade in profit."""
    bus = InMemoryEventBus()
    treasury, trader = _mk(bus)
    # wide TP so the bracket take-profit doesn't close first
    trader._params.take_profit_pct = D("50")
    task = asyncio.create_task(trader.start())
    try:
        await _drive_price(bus, trader, "1500000")
        await _send_decision(bus, "BUY", lambda: trader.position is not None)
        entry = trader.position.entry_price
        # ratchet the trailing stop above entry once price has risen
        await _drive_price(bus, trader, "1600000")
        assert trader.set_trail_stop(D("1590000")) is True
        assert trader.trail_stop > entry  # profit locked above cost
        # a dip below the trailing stop (but above the fixed bracket stop)
        await _drive_price(bus, trader, "1585000", cond=lambda: trader.trades_closed >= 1)
        assert trader.position is None
        trade = trader.last_trade
        assert trade is not None and trade.reason == ExitReason.TRAILING_STOP
        assert trade.pnl > 0  # closed in profit, not at the loss bracket
        assert treasury.cash == D("1000") + treasury.realized_pnl
    finally:
        await trader.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_set_trail_stop_only_ratchets_up_and_below_mark() -> None:
    bus = InMemoryEventBus()
    _, trader = _mk(bus)
    # no position → no-op
    assert trader.set_trail_stop(D("100")) is False
    from domain.trading.paper import PaperPosition
    trader.position = PaperPosition(
        symbol="THB_BTC", qty=D("0.001"), entry_price=D("1500000"),
        stop_price=D("1485000"), take_profit_price=D("1600000"),
        entry_fee=D("3.75"), opened_ms=1,
    )
    trader.mark_price = D("1600000")
    assert trader.set_trail_stop(D("1590000")) is True       # first set
    assert trader.set_trail_stop(D("1580000")) is False      # lower → ignored
    assert trader.set_trail_stop(D("1595000")) is True       # higher → raised
    assert trader.set_trail_stop(D("1600000")) is False      # >= mark → rejected
    assert trader.trail_stop == D("1595000")


@pytest.mark.asyncio
async def test_treasury_halt_blocks_new_entries() -> None:
    bus = InMemoryEventBus()
    treasury, trader = _mk(bus)
    treasury.halted = True
    task = asyncio.create_task(trader.start())
    try:
        await _drive_price(bus, trader, "1500000")
        await _send_decision(bus, "BUY", lambda: trader.entries_rejected >= 1)
        assert trader.position is None
        assert treasury.rejected_count == 1
    finally:
        await trader.stop()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_treasury_survival_floor_veto_direct() -> None:
    bus = InMemoryEventBus()
    treasury, _ = _mk(bus)
    treasury.cash = D("710")  # equity 710, floor 700
    d = treasury.request_open(order_cost=D("100"), worst_case=D("10.01"), open_market_value=D("0"))
    assert d.approved is False and VetoReason.SURVIVAL_FLOOR in d.reasons
    assert treasury.cash == D("710")  # nothing reserved on veto


@pytest.mark.asyncio
async def test_state_persists_across_restart(tmp_path: Path) -> None:
    store = SqliteStateStore(tmp_path / "state.db")
    bus = InMemoryEventBus()
    treasury1, _ = _mk(bus, store)
    trade = ClosedTrade(
        symbol="THB_BTC", qty=D("0.001"), entry_price=D("1500000"),
        exit_price=D("1510000"), entry_fee=D("3.75"), exit_fee=D("3.775"),
        pnl=D("2.475"), reason=ExitReason.TAKE_PROFIT, opened_ms=1, closed_ms=2,
    )
    treasury1.cash = D("996.25")  # as if notional reserved earlier
    treasury1.settle_close(trade)
    await treasury1.persist()
    cash_before = treasury1.cash

    treasury2, _ = _mk(bus, store)
    await treasury2._load()
    assert treasury2.cash == cash_before
    assert treasury2.wins == 1
    assert treasury2.realized_pnl == D("2.475")
    store.close()


class _CrashyAgent:
    """Raises right after starting — for watchdog tests."""

    def __init__(self) -> None:
        self.running = False
        self.msg_count = 0
        self.last_beat_ms = 0

    async def start(self) -> None:
        self.running = True
        await asyncio.sleep(0.01)
        raise RuntimeError("boom")

    async def stop(self) -> None:
        self.running = False


class _StubSettings:
    prices_topic = "prices.thb_btc.v1"
    bitkub_ws_url = ""
    initial_capital = "1000"
    persist_state = False
    watchdog_interval_s = 0.05
    heartbeat_stale_ms = 5000


@pytest.mark.asyncio
async def test_watchdog_restarts_crashed_agent_and_records_reason() -> None:
    runtime = PipelineRuntime(_StubSettings(), _LOG)
    await runtime.start("live")
    try:
        crashy = _CrashyAgent()
        runtime.agents["crashy"] = crashy
        await runtime.start_agent("crashy")
        await _until(lambda: runtime.restart_counts.get("crashy", 0) >= 1, timeout=3.0)
        assert "RuntimeError: boom" in runtime.crashed_agents["crashy"]
        # restarted task exists again
        assert "crashy" in runtime.agent_tasks
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_status_reports_crashed_truth_not_claim() -> None:
    """H5: a dead task must show running=False + crashed=True, never 'running'."""
    runtime = PipelineRuntime(_StubSettings(), _LOG)
    crashy = _CrashyAgent()
    runtime.agents = {"crashy": crashy}

    async def _boom() -> None:
        crashy.running = True
        raise RuntimeError("dead")

    task = asyncio.create_task(_boom())
    await asyncio.sleep(0.05)
    runtime.agent_tasks = {"crashy": task}
    st = runtime._agent_status("crashy", crashy)
    assert st["claimed_running"] is True   # the agent still THINKS it runs
    assert st["running"] is False          # the truth: task is dead
    assert st["crashed"] is True
    with pytest.raises(RuntimeError):
        await task
