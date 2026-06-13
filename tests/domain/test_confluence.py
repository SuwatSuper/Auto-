"""SetupGate (confluence) — pure win-probability entry gate."""
from __future__ import annotations

from decimal import Decimal

from domain.strategy.base import SignalAction
from domain.strategy.confluence import (
    EntryInputs,
    EntryReason,
    GateParams,
    evaluate_entry,
)

D = Decimal
P = GateParams(min_p_win=D("0.80"), min_confidence=D("0.50"), min_samples=20)


def _inp(**kw: object) -> EntryInputs:
    base: dict[str, object] = dict(
        signal_action=SignalAction.BUY, signal_confidence=D("1"),
        regime="TREND_UP", sentiment_score=D("0"), p_win=D("0.9"),
        p_win_samples=40, trend_agree=True,
    )
    base.update(kw)
    return EntryInputs(**base)  # type: ignore[arg-type]


def test_high_pwin_trend_up_approved() -> None:
    d = evaluate_entry(_inp(), P)
    assert d.approved and d.reasons == () and d.p_win == D("0.9")


def test_pwin_below_min_blocked() -> None:
    d = evaluate_entry(_inp(p_win=D("0.6")), P)
    assert not d.approved and EntryReason.P_WIN_BELOW_MIN in d.reasons


def test_small_sample_blocked_even_if_high_pwin() -> None:
    d = evaluate_entry(_inp(p_win=D("0.99"), p_win_samples=5), P)
    assert not d.approved and EntryReason.SAMPLE_TOO_SMALL in d.reasons


def test_high_vol_regime_blocked() -> None:
    d = evaluate_entry(_inp(regime="HIGH_VOL"), P)
    assert not d.approved and EntryReason.REGIME_VOLATILE_BLOCKED in d.reasons


def test_buy_against_downtrend_mismatch() -> None:
    d = evaluate_entry(_inp(regime="TREND_DOWN"), P)
    assert EntryReason.STRATEGY_REGIME_MISMATCH in d.reasons


def test_sentiment_opposed_blocks_buy() -> None:
    d = evaluate_entry(_inp(sentiment_score=D("-0.7")), P)
    assert EntryReason.SENTIMENT_OPPOSED in d.reasons


def test_low_confidence_blocked() -> None:
    d = evaluate_entry(_inp(signal_confidence=D("0.2")), P)
    assert EntryReason.LOW_CONFIDENCE in d.reasons


def test_all_reasons_reported_together() -> None:
    d = evaluate_entry(
        _inp(signal_action=SignalAction.HOLD, signal_confidence=D("0.1"),
             regime="HIGH_VOL", p_win=D("0.1"), p_win_samples=3), P)
    assert not d.approved
    assert EntryReason.NO_SIGNAL in d.reasons
    assert EntryReason.LOW_CONFIDENCE in d.reasons
    assert EntryReason.REGIME_VOLATILE_BLOCKED in d.reasons
    assert EntryReason.SAMPLE_TOO_SMALL in d.reasons
