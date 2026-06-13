# Layer 1 — Domain (strategy/confluence)
"""SetupGate — a pure confluence filter that only approves an entry when several
independent conditions agree AND the estimated win-probability clears a floor.

This is the real implementation of the gate the docs described. It is honest by
construction: ``p_win`` is an ESTIMATE supplied by the caller (measured from
historical + recent outcomes by the Timeline Analyst) — never a promise. Raising
``min_p_win`` raises selectivity and LOWERS trade count; no setting guarantees a
win. All parameters live in ``GateParams`` so the runtime can hot-swap them.
"""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from domain.strategy.base import SignalAction


class EntryReason(StrEnum):
    """Machine-readable reasons an entry was blocked."""

    NO_SIGNAL = "NO_SIGNAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    REGIME_VOLATILE_BLOCKED = "REGIME_VOLATILE_BLOCKED"
    STRATEGY_REGIME_MISMATCH = "STRATEGY_REGIME_MISMATCH"
    SENTIMENT_OPPOSED = "SENTIMENT_OPPOSED"
    TREND_DISAGREE = "TREND_DISAGREE"
    P_WIN_BELOW_MIN = "P_WIN_BELOW_MIN"
    SAMPLE_TOO_SMALL = "SAMPLE_TOO_SMALL"


class GateParams(BaseModel, frozen=True):
    """Tunable thresholds for the gate (hot-swappable by the runtime)."""

    min_confidence: Decimal = Decimal("0.50")
    # The headline win-probability floor. Operator default 0.80 = "only fire
    # when ≥80% of comparable historical setups won". Higher → fewer, stronger.
    min_p_win: Decimal = Decimal("0.80")
    # Minimum number of graded historical setups before p_win is trusted.
    min_samples: int = 20
    block_high_vol: bool = True
    require_trend_agree: bool = False
    sentiment_veto: bool = True


class EntryInputs(BaseModel, frozen=True):
    """Everything the gate needs to judge one proposed entry."""

    signal_action: SignalAction
    signal_confidence: Decimal = Decimal("0")
    regime: str = "RANGE"            # TREND_UP/TREND_DOWN/RANGE/HIGH_VOL
    sentiment_score: Decimal = Decimal("0")   # −1..+1
    p_win: Decimal = Decimal("0")    # estimated win probability 0..1
    p_win_samples: int = 0           # how many setups p_win was measured over
    trend_agree: bool = True         # does the broader trend agree with the side?


class EntryDecision(BaseModel, frozen=True):
    """Result of the gate. ``approved`` only when ``reasons`` is empty."""

    approved: bool
    reasons: tuple[EntryReason, ...] = ()
    p_win: Decimal = Decimal("0")


def evaluate_entry(inputs: EntryInputs, params: GateParams) -> EntryDecision:
    """Pure confluence check. Runs ALL checks; reports ALL failing reasons."""
    reasons: list[EntryReason] = []

    if inputs.signal_action not in (SignalAction.BUY, SignalAction.SELL):
        reasons.append(EntryReason.NO_SIGNAL)

    if inputs.signal_confidence < params.min_confidence:
        reasons.append(EntryReason.LOW_CONFIDENCE)

    if params.block_high_vol and inputs.regime == "HIGH_VOL":
        reasons.append(EntryReason.REGIME_VOLATILE_BLOCKED)

    # Long against a down-trend / short against an up-trend is a regime mismatch.
    if inputs.signal_action == SignalAction.BUY and inputs.regime == "TREND_DOWN":
        reasons.append(EntryReason.STRATEGY_REGIME_MISMATCH)
    if inputs.signal_action == SignalAction.SELL and inputs.regime == "TREND_UP":
        reasons.append(EntryReason.STRATEGY_REGIME_MISMATCH)

    if params.sentiment_veto:
        if inputs.signal_action == SignalAction.BUY and inputs.sentiment_score <= Decimal("-0.5"):
            reasons.append(EntryReason.SENTIMENT_OPPOSED)
        if inputs.signal_action == SignalAction.SELL and inputs.sentiment_score >= Decimal("0.5"):
            reasons.append(EntryReason.SENTIMENT_OPPOSED)

    if params.require_trend_agree and not inputs.trend_agree:
        reasons.append(EntryReason.TREND_DISAGREE)

    # Win-probability floor — the headline "only fire at ≥X%" rule. Requires a
    # trustworthy sample first (never fire on a number measured from too little).
    if inputs.p_win_samples < params.min_samples:
        reasons.append(EntryReason.SAMPLE_TOO_SMALL)
    elif inputs.p_win < params.min_p_win:
        reasons.append(EntryReason.P_WIN_BELOW_MIN)

    return EntryDecision(
        approved=not reasons, reasons=tuple(reasons), p_win=inputs.p_win
    )
