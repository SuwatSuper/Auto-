# Layer 2 — Orchestration (tests/orchestration/test_risk_limits_unlocked)
"""The unlocked limits: ten-million starting capital, per-trade risk up to
100%, and an UNLIMITED circuit breaker (0 = ปลดลิมิตเบรกเกอร์ 5/5)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.config import Settings
from orchestration.control import RiskSettings, validate_risk_settings
from orchestration.runtime import PipelineRuntime


def _base() -> RiskSettings:
    return RiskSettings(
        risk_per_trade_pct=Decimal("1"),
        stop_pct=Decimal("1"),
        take_profit_pct=Decimal("1.5"),
        max_daily_loss_pct=Decimal("5"),
        max_consecutive_losses=5,
        max_open_positions=3,
        max_deployable_thb=Decimal("0"),
        max_single_order_thb=Decimal("0"),
    )


# ── pure validation bounds ───────────────────────────────────────────
def test_risk_per_trade_accepts_full_100() -> None:
    new, errors = validate_risk_settings(_base(), {"risk_per_trade_pct": "100"})
    assert errors == []
    assert new is not None
    assert new.risk_per_trade_pct == Decimal("100")


def test_risk_per_trade_rejects_above_100() -> None:
    new, errors = validate_risk_settings(_base(), {"risk_per_trade_pct": "100.01"})
    assert new is None
    assert any("risk_per_trade_pct" in e for e in errors)


def test_breaker_threshold_zero_is_accepted_as_unlimited() -> None:
    new, errors = validate_risk_settings(_base(), {"max_consecutive_losses": "0"})
    assert errors == []
    assert new is not None
    assert new.max_consecutive_losses == 0


# ── circuit breaker unlimited behaviour ──────────────────────────────
def test_zero_threshold_never_auto_trips() -> None:
    cb = CircuitBreaker(max_consecutive_losses=0)
    assert cb.unlimited is True
    for _ in range(50):
        cb.record_trade(Decimal("-100"))
    assert cb.is_open is False
    assert cb.consecutive_losses == 50  # still counted, just never trips


def test_update_threshold_to_zero_unlocks_and_negative_rejected() -> None:
    cb = CircuitBreaker(max_consecutive_losses=3)
    assert cb.unlimited is False
    cb.update_threshold(0)
    assert cb.unlimited is True
    with pytest.raises(ValueError):
        cb.update_threshold(-1)


def test_manual_trip_still_works_when_unlimited() -> None:
    cb = CircuitBreaker(max_consecutive_losses=0)
    cb.trip("MANUAL", 1)
    assert cb.is_open is True


# ── live application through the runtime control plane ───────────────
@pytest.mark.asyncio
async def test_unlocked_settings_apply_live() -> None:
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("test"))
    rt.agents = rt._make_agents()
    ok, payload = await rt.update_risk_settings(
        {"risk_per_trade_pct": "100", "max_consecutive_losses": "0"}
    )
    assert ok, payload
    assert rt._circuit_breaker is not None and rt._circuit_breaker.unlimited is True
    assert rt._trade_params is not None
    assert rt._trade_params.risk_per_trade_pct == Decimal("100")  # type: ignore[union-attr]


# ── shipped defaults ─────────────────────────────────────────────────
def test_defaults_ship_ten_million_and_unlimited_breaker() -> None:
    s = Settings()
    assert s.initial_capital == "10000000"   # สิบล้าน
    assert s.max_consecutive_losses == "0"   # unlimited breaker
