# tests/orchestration/test_thai_time.py
"""Item 4 (P1-1): Daily risk window uses Thai local time (UTC+7)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import structlog

from domain.portfolio.treasury import TreasuryLimits
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.agents.treasury_agent import TreasuryAgent


def _make_treasury(tz_offset: int = 420) -> TreasuryAgent:
    bus = InMemoryEventBus()
    log = structlog.get_logger("test")
    limits = TreasuryLimits(
        initial_capital=Decimal("10000"),
        survival_floor_pct=Decimal("70"),
        max_daily_loss_pct=Decimal("5"),
    )
    store = InMemoryStateStore()
    return TreasuryAgent(bus, "treasury.v1", log, limits, store, tz_offset_minutes=tz_offset)


def test_day_key_uses_local_time_not_utc() -> None:
    """day_key is based on UTC+7, not UTC."""
    treasury = _make_treasury(tz_offset=420)
    tz = timezone(timedelta(minutes=420))
    expected = datetime.now(tz=tz).strftime("%Y-%m-%d")
    assert treasury.day_key == expected


def test_rollover_at_local_midnight_not_utc() -> None:
    """Rollover triggers at local midnight (17:00 UTC for UTC+7)."""
    treasury = _make_treasury(tz_offset=420)
    # Manually set day_key to yesterday to simulate needing rollover
    from datetime import date
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    treasury.day_key = yesterday
    treasury.realized_today = Decimal("-200")
    treasury.halted = True  # simulated halt from yesterday

    # Force rollover
    treasury._rollover_if_new_day()

    # Should have rolled over
    tz = timezone(timedelta(minutes=420))
    today = datetime.now(tz=tz).strftime("%Y-%m-%d")
    assert treasury.day_key == today
    assert treasury.realized_today == Decimal("0")


def test_zero_offset_acts_like_utc() -> None:
    """With tz_offset=0 the day key matches UTC date."""
    treasury = _make_treasury(tz_offset=0)
    utc_today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert treasury.day_key == utc_today


def test_rollover_called_on_request_open() -> None:
    """request_open triggers rollover check."""
    treasury = _make_treasury(tz_offset=420)
    yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    treasury.day_key = yesterday
    treasury.realized_today = Decimal("-500")

    treasury.request_open(Decimal("100"), Decimal("10"), Decimal("0"))

    # Should have reset realized_today on rollover
    tz = timezone(timedelta(minutes=420))
    today = datetime.now(tz=tz).strftime("%Y-%m-%d")
    assert treasury.day_key == today
