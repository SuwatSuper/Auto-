# Layer 1 — Domain (analytics/regime_weights)
"""Adaptive regime → strategy-weight switching.

The same strategy that prints money in a trend bleeds in a range. This module
turns the detected regime into a weight per strategy family — trend-following and
momentum are amplified in trends, mean-reversion in ranges, everything throttled
in high volatility — so the swarm automatically leans on the right playbook for
the conditions.

It composes with the U3 meta-learner: :func:`adaptive_weights` multiplies the
regime base weight by each family's MEASURED reliability in that regime, so the
final weight reflects both "what usually works here" and "what has actually been
working here for us". Pure & deterministic: Decimal math, no I/O.
"""
from __future__ import annotations

from decimal import Decimal

from domain.analytics.swarm_meta import NEUTRAL_WEIGHT, SwarmMetaLearner

STRATEGY_FAMILIES: tuple[str, ...] = (
    "trend_following",
    "mean_reversion",
    "breakout",
    "momentum",
)

_NEUTRAL = Decimal("1.0")
# Final weights are clamped to this band so no single regime adjustment can
# silence a family entirely or let it run away.
_MIN_WEIGHT = Decimal("0.2")
_MAX_WEIGHT = Decimal("3.0")

# Base regime playbook. Keys are canonical regimes; rows are per-family weights.
_REGIME_WEIGHTS: dict[str, dict[str, Decimal]] = {
    "TREND_UP": {
        "trend_following": Decimal("1.5"), "momentum": Decimal("1.3"),
        "breakout": Decimal("1.0"), "mean_reversion": Decimal("0.5"),
    },
    "TREND_DOWN": {
        "trend_following": Decimal("1.5"), "momentum": Decimal("1.3"),
        "breakout": Decimal("1.0"), "mean_reversion": Decimal("0.5"),
    },
    "RANGE": {
        "trend_following": Decimal("0.5"), "momentum": Decimal("0.7"),
        "breakout": Decimal("0.7"), "mean_reversion": Decimal("1.5"),
    },
    "BREAKOUT": {
        "trend_following": Decimal("1.0"), "momentum": Decimal("1.2"),
        "breakout": Decimal("1.5"), "mean_reversion": Decimal("0.6"),
    },
    "HIGH_VOL": {
        "trend_following": Decimal("0.5"), "momentum": Decimal("0.5"),
        "breakout": Decimal("0.8"), "mean_reversion": Decimal("0.5"),
    },
}


def canonical_regime(regime: str) -> str:
    """Map any regime spelling (MarketRegime or MarketMode) to a canonical key."""
    r = regime.upper()
    if r in ("TREND_UP", "TRENDING_UP"):
        return "TREND_UP"
    if r in ("TREND_DOWN", "TRENDING_DOWN"):
        return "TREND_DOWN"
    if r == "HIGH_VOL":
        return "HIGH_VOL"
    if r == "BREAKOUT":
        return "BREAKOUT"
    if r in ("RANGE", "RANGING"):
        return "RANGE"
    return "UNKNOWN"


def regime_strategy_weights(regime: str) -> dict[str, Decimal]:
    """Base weight per strategy family for ``regime`` (all 1.0 if unknown)."""
    key = canonical_regime(regime)
    base = _REGIME_WEIGHTS.get(key)
    if base is None:
        return dict.fromkeys(STRATEGY_FAMILIES, _NEUTRAL)
    return {fam: base.get(fam, _NEUTRAL) for fam in STRATEGY_FAMILIES}


def _clamp(w: Decimal) -> Decimal:
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, w))


def adaptive_weights(
    regime: str, meta: SwarmMetaLearner | None = None
) -> dict[str, Decimal]:
    """Regime base weights scaled by each family's measured reliability (U3).

    With no meta-learner (or no history) this is just the regime playbook. As
    real outcomes accrue, a family that has actually been reliable in this regime
    is boosted and an unreliable one is throttled — bounded to a sane band.
    """
    key = canonical_regime(regime)
    base = regime_strategy_weights(regime)
    if meta is None:
        return base
    out: dict[str, Decimal] = {}
    for fam, w in base.items():
        # meta.weight is 1.0 at neutral; >1 proven, <1 unproven in this regime.
        scaled = w * (meta.weight(fam, key) / NEUTRAL_WEIGHT)
        out[fam] = _clamp(scaled)
    return out
