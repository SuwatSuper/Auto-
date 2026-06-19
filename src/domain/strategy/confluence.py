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
    BOOK_IMBALANCE_OPPOSED = "BOOK_IMBALANCE_OPPOSED"
    # Bus-fed confluence inputs (Task 1) — each is a quantified read PUBLISHED by
    # a department agent over the Event Bus and consumed by the runtime gate.
    # No hidden attribute coupling: the gate only ever sees these via the bus.
    PROBABILITY_OPPOSED = "PROBABILITY_OPPOSED"          # probability_lab (RSI p_bull)
    SWARM_CONSENSUS_OPPOSED = "SWARM_CONSENSUS_OPPOSED"  # division chiefs' bias
    PRICE_OVEREXTENDED = "PRICE_OVEREXTENDED"            # research_dept percentile
    SIM_WIN_RATE_LOW = "SIM_WIN_RATE_LOW"                # execution_agent (Sim) backtest


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
    # Block a long in a down-trend / short in an up-trend. Default ON (selective)
    # but the runtime can turn it OFF for an active profile that also dip-buys
    # (mean-reversion entries legitimately fire in mild down-trends).
    block_regime_mismatch: bool = True
    # U1 microstructure: veto a BUY into a heavily-offered book (or a SELL into a
    # heavily-bid book). OFF by default — a soft confirm the runtime opts into
    # only when a live depth feed is wired, so price-only setups are unaffected.
    book_imbalance_veto: bool = False
    # How lopsided the book must be (against the side) to veto, in [0, 1].
    # 0.40 = the opposing side holds ≥70% of the top-of-book size.
    min_book_imbalance: Decimal = Decimal("0.40")

    # ── Bus-fed confluence inputs (Task 1) — opt-in like the book veto ────────
    # probability_lab: veto a BUY when the RSI-derived bullish probability is
    # below this floor (or a SELL when it is above 1-floor). Neutral 0.5 passes.
    probability_veto: bool = False
    min_prob_bull: Decimal = Decimal("0.30")
    # division chiefs: veto a BUY when the swarm's net consensus bias [-1,+1] is
    # strongly against it (or a SELL when strongly for it). 0.0 (neutral) passes.
    swarm_veto: bool = False
    min_swarm_bias: Decimal = Decimal("-0.50")
    # research_dept: veto a BUY when price sits in the top ``max_entry_pctl`` of
    # its rolling range (chasing an over-extended price). −1 means "no read".
    research_veto: bool = False
    max_entry_pctl: Decimal = Decimal("0.97")
    # execution_agent (Sim): veto when the rolling backtest win-rate is below this
    # floor over a real window. −1 (no read yet) always passes.
    sim_veto: bool = False
    min_sim_win_rate: Decimal = Decimal("0.20")


class EntryInputs(BaseModel, frozen=True):
    """Everything the gate needs to judge one proposed entry."""

    signal_action: SignalAction
    signal_confidence: Decimal = Decimal("0")
    regime: str = "RANGE"            # TREND_UP/TREND_DOWN/RANGE/HIGH_VOL
    sentiment_score: Decimal = Decimal("0")   # −1..+1
    p_win: Decimal = Decimal("0")    # estimated win probability 0..1
    p_win_samples: int = 0           # how many setups p_win was measured over
    trend_agree: bool = True         # does the broader trend agree with the side?
    # U1: order-book imbalance in [-1, +1] (+ = resting bid pressure). 0 = no
    # book read available (one-sided/empty/warming-up) → never vetoes.
    book_imbalance: Decimal = Decimal("0")
    # Bus-fed confluence reads (Task 1). Defaults are NEUTRAL so a gate with the
    # new vetoes enabled still passes until a real read arrives over the bus.
    prob_bull: Decimal = Decimal("0.5")        # probability_lab: P(bullish) 0..1
    swarm_bias: Decimal = Decimal("0")         # chiefs: net consensus [-1,+1]
    price_pctl: Decimal = Decimal("-1")        # research_dept: price percentile 0..1 (−1 = none)
    sim_win_rate: Decimal = Decimal("-1")      # execution_agent (Sim): 0..1 (−1 = none)


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

    # Long against a down-trend / short against an up-trend is a regime mismatch
    # (only enforced when block_regime_mismatch is on).
    if params.block_regime_mismatch:
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

    # U1 microstructure veto — a BUY into a book dominated by offers (negative
    # imbalance) or a SELL into a book dominated by bids is fighting the resting
    # order flow. Only enforced when the runtime has a live depth feed wired.
    if params.book_imbalance_veto and params.min_book_imbalance > 0:
        threshold = params.min_book_imbalance
        if inputs.signal_action == SignalAction.BUY and inputs.book_imbalance <= -threshold:
            reasons.append(EntryReason.BOOK_IMBALANCE_OPPOSED)
        if inputs.signal_action == SignalAction.SELL and inputs.book_imbalance >= threshold:
            reasons.append(EntryReason.BOOK_IMBALANCE_OPPOSED)

    # ── Bus-fed confluence vetoes (Task 1) ──────────────────────────────────
    # probability_lab: a BUY needs the RSI-derived P(bull) above the floor; a
    # SELL needs it below the mirrored ceiling. Neutral 0.5 clears both.
    if params.probability_veto:
        floor = params.min_prob_bull
        if inputs.signal_action == SignalAction.BUY and inputs.prob_bull < floor:
            reasons.append(EntryReason.PROBABILITY_OPPOSED)
        if inputs.signal_action == SignalAction.SELL and inputs.prob_bull > Decimal("1") - floor:
            reasons.append(EntryReason.PROBABILITY_OPPOSED)

    # division chiefs: a BUY is vetoed when the swarm's net consensus is strongly
    # bearish (≤ min_swarm_bias); a SELL when it is strongly bullish (≥ −min).
    if params.swarm_veto:
        bias_floor = params.min_swarm_bias
        if inputs.signal_action == SignalAction.BUY and inputs.swarm_bias <= bias_floor:
            reasons.append(EntryReason.SWARM_CONSENSUS_OPPOSED)
        if inputs.signal_action == SignalAction.SELL and inputs.swarm_bias >= -bias_floor:
            reasons.append(EntryReason.SWARM_CONSENSUS_OPPOSED)

    # research_dept: don't chase a BUY when price sits in the very top of its
    # rolling range. price_pctl < 0 means "no read yet" → never vetoes.
    if params.research_veto and inputs.price_pctl >= 0:
        if inputs.signal_action == SignalAction.BUY and inputs.price_pctl > params.max_entry_pctl:
            reasons.append(EntryReason.PRICE_OVEREXTENDED)
        if inputs.signal_action == SignalAction.SELL and inputs.price_pctl < (
            Decimal("1") - params.max_entry_pctl
        ):
            reasons.append(EntryReason.PRICE_OVEREXTENDED)

    # execution_agent (Sim): a chronically losing rolling backtest mutes new
    # entries. sim_win_rate < 0 means "no window completed yet" → never vetoes.
    if params.sim_veto and inputs.sim_win_rate >= 0 and inputs.sim_win_rate < params.min_sim_win_rate:
        reasons.append(EntryReason.SIM_WIN_RATE_LOW)

    # Win-probability floor — the headline "only fire at ≥X%" rule. Requires a
    # trustworthy sample first (never fire on a number measured from too little).
    if inputs.p_win_samples < params.min_samples:
        reasons.append(EntryReason.SAMPLE_TOO_SMALL)
    elif inputs.p_win < params.min_p_win:
        reasons.append(EntryReason.P_WIN_BELOW_MIN)

    return EntryDecision(
        approved=not reasons, reasons=tuple(reasons), p_win=inputs.p_win
    )
