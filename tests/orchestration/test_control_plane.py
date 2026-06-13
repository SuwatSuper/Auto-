# Layer 2 — Orchestration (tests/orchestration/test_control_plane)
"""Operator control plane: live risk settings, breaker control, execution-mode switch."""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog

from infrastructure.config import Settings
from orchestration.control import RiskSettings, validate_risk_settings
from orchestration.runtime import PipelineRuntime


def _rt() -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False), logger=structlog.get_logger("test")
    )
    rt.agents = rt._make_agents()  # builds trader, treasury, breaker, risk gate (as start() does)
    return rt


# ── pure validation ──────────────────────────────────────────────────

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


def test_validate_accepts_partial_patch() -> None:
    new, errors = validate_risk_settings(_base(), {"risk_per_trade_pct": "2.5"})
    assert errors == []
    assert new is not None
    assert new.risk_per_trade_pct == Decimal("2.5")
    assert new.stop_pct == Decimal("1")  # unchanged


def test_validate_rejects_out_of_range() -> None:
    new, errors = validate_risk_settings(_base(), {"risk_per_trade_pct": "999"})
    assert new is None
    assert any("risk_per_trade_pct" in e for e in errors)


def test_validate_rejects_non_number_and_unknown() -> None:
    new, errors = validate_risk_settings(_base(), {"stop_pct": "abc", "bogus": 1})
    assert new is None
    assert any("stop_pct" in e for e in errors)
    assert any("unknown field" in e for e in errors)


# ── live application ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_risk_settings_applies_live() -> None:
    rt = _rt()
    ok, payload = await rt.update_risk_settings(
        {"risk_per_trade_pct": "3", "max_consecutive_losses": "2", "max_open_positions": "4"}
    )
    assert ok, payload
    # trade params mutated (next trade uses these)
    assert rt._trade_params.risk_per_trade_pct == Decimal("3")  # type: ignore[union-attr]
    # breaker threshold mutated
    assert rt._circuit_breaker.max_consecutive_losses == 2  # type: ignore[union-attr]
    # open-position cap mutated on the risk gate
    assert rt.agents["risk_gate"]._max_open_positions == 4  # type: ignore[attr-defined]
    # surfaced in status
    st = rt.status()
    assert st["risk_settings"]["risk_per_trade_pct"] == "3"


@pytest.mark.asyncio
async def test_update_risk_settings_rejects_bad() -> None:
    rt = _rt()
    ok, payload = await rt.update_risk_settings({"stop_pct": "-5"})
    assert not ok
    assert "errors" in payload


# ── breaker control ──────────────────────────────────────────────────

def test_breaker_trip_and_reset() -> None:
    rt = _rt()
    assert rt.trip_breaker("MANUAL")["is_open"] is True
    assert rt._circuit_breaker.is_open is True  # type: ignore[union-attr]
    # wrong token fails
    assert rt.reset_breaker("nope")["ok"] is False
    assert rt._circuit_breaker.is_open is True  # type: ignore[union-attr]
    # correct token succeeds
    assert rt.reset_breaker("MANUAL_RESET_CONFIRMED")["ok"] is True
    assert rt._circuit_breaker.is_open is False  # type: ignore[union-attr]


# ── execution mode switch (gated) ────────────────────────────────────

def test_execution_mode_defaults_paper() -> None:
    rt = _rt()
    assert rt.get_execution_mode()["mode"] == "paper"


def test_switch_to_live_requires_token() -> None:
    rt = _rt()
    ok, payload = rt.set_execution_mode("live", confirm="")
    assert not ok
    assert "token" in str(payload).lower()
    assert rt.get_execution_mode()["mode"] == "paper"


def test_switch_to_live_blocked_when_breaker_open() -> None:
    rt = _rt()
    rt.trip_breaker("MANUAL")
    ok, payload = rt.set_execution_mode("live", confirm="I_ACCEPT_REAL_MONEY_RISK")
    assert not ok
    assert "breaker" in str(payload).lower()


def test_switch_to_live_succeeds_when_gates_open() -> None:
    rt = _rt()
    ok, payload = rt.set_execution_mode("live", confirm="I_ACCEPT_REAL_MONEY_RISK")
    assert ok, payload
    assert rt.get_execution_mode()["mode"] == "live"
    assert rt.settings.execution_engine == "live"
    # and back to paper
    ok2, _ = rt.set_execution_mode("paper")
    assert ok2
    assert rt.settings.execution_engine == "paper"


def test_control_audit_records_actions() -> None:
    rt = _rt()
    rt.trip_breaker("MANUAL")
    rt.set_execution_mode("paper")
    actions = [r["action"] for r in rt.control_audit()]
    assert "breaker_trip" in actions
    assert "execution_mode" in actions
