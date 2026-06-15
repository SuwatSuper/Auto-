# tests/orchestration/test_crash_recovery.py
"""Item 3 (P0-3): Crash-safe atomic state — torn/legacy state loads safely."""
from __future__ import annotations

from decimal import Decimal

import orjson
import pytest
import structlog

from domain.portfolio.treasury import TreasuryLimits
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.agents.paper_trader import (
    _POSITION_KEY,
    _SESSION_KEY,
    PaperTraderAgent,
    TradeParams,
)
from orchestration.agents.treasury_agent import TreasuryAgent


def _make_agents(store: InMemoryStateStore) -> tuple[TreasuryAgent, PaperTraderAgent]:
    bus = InMemoryEventBus()
    log = structlog.get_logger("test")
    limits = TreasuryLimits(
        initial_capital=Decimal("10000"),
        survival_floor_pct=Decimal("70"),
        max_daily_loss_pct=Decimal("5"),
    )
    treasury = TreasuryAgent(bus, "treasury.v1", log, limits, store)
    params = TradeParams()
    trader = PaperTraderAgent(
        bus, "decisions.approved.v1", "prices.v1", "paper.events.v1",
        log, treasury, params, store,
    )
    return treasury, trader


@pytest.mark.asyncio
async def test_combined_session_key_loads_both_treasury_and_position() -> None:
    """Combined session key restores both treasury and position atomically."""
    store = InMemoryStateStore()
    treasury, trader = _make_agents(store)

    # Write a consistent combined session record
    pos_data = {
        "symbol": "THB_BTC", "qty": "0.001", "entry_price": "1000000",
        "stop_price": "990000", "take_profit_price": "1015000",
        "entry_fee": "250", "opened_ms": 1000,
    }
    session = orjson.dumps({
        "seq": 5,
        "treasury": {
            "cash": "9500",
            "realized_pnl": "-100",
            "realized_today": "-100",
            "day_key": "2025-01-01",
            "wins": 1,
            "losses": 2,
            "halted": False,
        },
        "position": pos_data,
        "trades_closed": 3,
        "entries_opened": 4,
    })
    await store.set(_SESSION_KEY, session)

    await trader._load()

    assert trader.position is not None
    assert trader.trades_closed == 3
    assert trader.entries_opened == 4
    assert treasury.cash == Decimal("9500")
    assert treasury.wins == 1
    assert treasury.losses == 2
    assert trader.state_loaded is True


@pytest.mark.asyncio
async def test_torn_state_legacy_position_with_full_cash_is_repaired() -> None:
    """Legacy split keys: phantom position with full cash is dropped (never invent money)."""
    store = InMemoryStateStore()
    treasury, trader = _make_agents(store)

    # Simulate torn state: position key exists but treasury cash is still at initial_capital
    # (crash happened before cash was debited)
    pos_data = {
        "symbol": "THB_BTC", "qty": "0.001", "entry_price": "1000000",
        "stop_price": "990000", "take_profit_price": "1015000",
        "entry_fee": "250", "opened_ms": 1000,
    }
    legacy = orjson.dumps({
        "position": pos_data,
        "trades_closed": 0,
        "entries_opened": 1,
    })
    await store.set(_POSITION_KEY, legacy)
    # No session key — treasury loads at full initial_capital

    await trader._load()

    # Position must be dropped; cash is intact
    assert trader.position is None
    assert treasury.cash == Decimal("10000")  # full initial capital — cash never lost


@pytest.mark.asyncio
async def test_no_session_key_and_no_legacy_starts_fresh() -> None:
    """Clean start: no keys → fresh state, no crash."""
    store = InMemoryStateStore()
    treasury, trader = _make_agents(store)

    await trader._load()

    assert trader.position is None
    assert treasury.cash == Decimal("10000")
    assert trader.state_loaded is False
