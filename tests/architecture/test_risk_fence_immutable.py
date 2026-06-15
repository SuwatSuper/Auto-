# Architecture guard — RISK FENCE is immutable to the learning loop
"""Phase 1.4 / 4.2: the survival floor, daily-loss cap, per-order hard cap, and
the bracket (H1) are guard rails. The self-improvement loop may tune a STRATEGY's
own parameters within bounded ranges, but it can NEVER reach the risk fence.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog
from pydantic import ValidationError

from infrastructure.config import Settings
from orchestration.agents.extended import BreakoutSpecialistAgent, MeanReversionAgent
from orchestration.control import (
    _FRAC_FIELDS,
    _INT_FIELDS,
    _PCT_FIELDS,
    _THB_FIELDS,
    HARD_CAP_SINGLE_ORDER_THB,
    RiskSettings,
    validate_risk_settings,
)
from orchestration.runtime_strategy import _apply_params

_LOG = structlog.get_logger("test")

# The strategy parameters the learning loop is allowed to tune (and nothing else).
_TUNABLE_STRATEGY_PARAMS = {"min_gap_pct", "rsi_oversold", "rsi_overbought", "channel_n"}
# Risk-fence parameters that must NEVER be tunable by learning.
_RISK_FENCE_PARAMS = {
    "survival_floor_pct", "max_daily_loss_pct", "max_single_order_thb",
    "max_deployable_thb", "hard_cap", "HARD_CAP_SINGLE_ORDER_THB",
}


def test_survival_floor_is_not_operator_or_learning_tunable() -> None:
    operator_fields = set(_PCT_FIELDS) | set(_INT_FIELDS) | set(_THB_FIELDS) | set(_FRAC_FIELDS)
    # survival_floor_pct is set only at construction (TreasuryLimits) — not exposed.
    assert "survival_floor_pct" not in operator_fields
    # and never in the strategy learning vocabulary.
    assert "survival_floor_pct" not in _TUNABLE_STRATEGY_PARAMS


def test_strategy_tunables_are_disjoint_from_the_risk_fence() -> None:
    assert _TUNABLE_STRATEGY_PARAMS.isdisjoint(_RISK_FENCE_PARAMS)


def test_learning_param_apply_rejects_risk_fence_keys() -> None:
    """Feeding a risk-fence key through the strategy param path is rejected —
    learning can NOT move the fence even by name."""
    agent = MeanReversionAgent("mean_reversion", _bus(), "p", "s", _LOG)  # type: ignore[arg-type]
    for bad in _RISK_FENCE_PARAMS:
        errors = _apply_params(agent, {bad: "1"})
        assert errors, f"risk-fence key {bad!r} must be rejected as a strategy param"


def test_hard_cap_cannot_be_raised_through_the_operator_api() -> None:
    base = RiskSettings(
        risk_per_trade_pct=Decimal("1"), stop_pct=Decimal("0.5"),
        take_profit_pct=Decimal("1.5"), max_daily_loss_pct=Decimal("100"),
        max_consecutive_losses=0, max_open_positions=1,
        max_deployable_thb=Decimal("0"), max_single_order_thb=Decimal("0"),
    )
    over = str(HARD_CAP_SINGLE_ORDER_THB + 1)
    settings, errors = validate_risk_settings(base, {"max_single_order_thb": over})
    assert settings is None
    assert any("hard cap" in e for e in errors)


def test_daily_loss_cap_enforced_in_treasury_not_strategy() -> None:
    """The daily-loss cap lives in the treasury limits (code), not in the
    strategy-tunable set."""
    s = Settings(persist_state=False)
    # max_daily_loss_pct is an OPERATOR setting (their risk choice) but is applied
    # via TreasuryLimits — strategies/learning cannot touch it.
    assert "max_daily_loss_pct" in _PCT_FIELDS          # operator-settable
    assert "max_daily_loss_pct" not in _TUNABLE_STRATEGY_PARAMS  # not learning-settable
    assert hasattr(s, "survival_floor_pct")


def test_bracket_h1_is_atomic_no_naked_position() -> None:
    """A position cannot exist without stop < entry < take-profit (H1)."""
    from domain.trading.paper import PaperPosition

    # missing/invalid stop (above entry) → rejected at the model level.
    with pytest.raises(ValidationError):
        PaperPosition(
            symbol="thb_btc", qty=Decimal("0.01"),
            entry_price=Decimal("1000000"),
            stop_price=Decimal("1010000"),         # ABOVE entry — invalid
            take_profit_price=Decimal("1020000"),
            entry_fee=Decimal("0"), opened_ms=0,
        )
    with pytest.raises(ValidationError):
        PaperPosition(
            symbol="thb_btc", qty=Decimal("0.01"),
            entry_price=Decimal("1000000"),
            stop_price=Decimal("990000"),
            take_profit_price=Decimal("980000"),   # BELOW entry — invalid
            entry_fee=Decimal("0"), opened_ms=0,
        )


def test_breakout_channel_param_stays_in_bounds() -> None:
    """Learning can widen/narrow the channel only within its bounded range."""
    agent = BreakoutSpecialistAgent("breakout_specialist", _bus(), "p", "s", _LOG)  # type: ignore[arg-type]
    assert _apply_params(agent, {"channel_n": "500"})   # > 200 → rejected
    assert _apply_params(agent, {"channel_n": "1"})     # < 2 → rejected
    assert _apply_params(agent, {"channel_n": "40"}) == []
    assert agent._n == 40


def _bus():  # type: ignore[no-untyped-def]
    import asyncio

    class _B:
        def subscribe(self, t, maxsize=10_000):  # type: ignore[no-untyped-def]
            return asyncio.Queue()

        def unsubscribe(self, t, q):  # type: ignore[no-untyped-def]
            pass

        async def publish(self, t, k, v):  # type: ignore[no-untyped-def]
            pass

    return _B()
