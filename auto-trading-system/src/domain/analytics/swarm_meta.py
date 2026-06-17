# Layer 1 — Domain (analytics/swarm_meta)
"""Regime-aware meta-learner for the analysis swarm.

The swarm runs many methods (EMA cross, RSI, MACD, …) across timeframes. Voting
them equally wastes the fact that some methods are reliable in trends and useless
in chop — and vice-versa. This meta-learner keeps each method's MEASURED hit rate
*per market regime* and weights its vote by that reliability, so the swarm leans
on whoever has actually been right in the conditions at hand.

Honest by construction:
  • weights come only from graded real outcomes (Laplace-smoothed so a thin
    record stays near neutral, never overconfident);
  • a method with no history in a regime gets the neutral weight 1.0;
  • every weight is bounded — one lucky streak can't let a method dominate.

Pure & deterministic: Decimal math, no I/O. Layer 2 records outcomes and
persists the table via :meth:`to_dict` / :meth:`from_dict`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from domain.analytics.swarm_methods import BEAR, BULL, NEUTRAL, AnalysisRead

_ZERO = Decimal("0")
# Reliability→weight bounds. Neutral (0.5 hit rate) maps to 1.0; a perfect record
# tops out at MAX_WEIGHT, a hopeless one floors at MIN_WEIGHT — never 0 (so a
# method is muted, never erased, and can recover).
MIN_WEIGHT = Decimal("0.25")
MAX_WEIGHT = Decimal("2.0")
NEUTRAL_WEIGHT = Decimal("1.0")


@dataclass
class MethodRegimeStats:
    """Graded outcomes for one (method, regime) pair."""

    wins: int = 0
    total: int = 0

    def reliability(self) -> Decimal:
        """Laplace-smoothed hit rate in (0, 1); 0.5 with no data."""
        return Decimal(self.wins + 1) / Decimal(self.total + 2)


@dataclass(frozen=True)
class WeightedVote:
    """Outcome of a reliability-weighted swarm vote."""

    direction: str          # BULL / BEAR / NEUTRAL
    score: Decimal          # signed net conviction in [-1, +1] (+ bull / − bear)
    bull_weight: Decimal
    bear_weight: Decimal
    contributions: tuple[tuple[str, Decimal], ...]  # (method, signed contribution)


@dataclass
class SwarmMetaLearner:
    """Per-(method, regime) reliability table + a weighted voter."""

    stats: dict[tuple[str, str], MethodRegimeStats] = field(default_factory=dict)
    # Net |score| must clear this for a directional verdict (else NEUTRAL).
    decision_threshold: Decimal = Decimal("0.15")

    def record(self, method: str, regime: str, won: bool) -> None:
        """Grade one real outcome of ``method`` in ``regime``."""
        s = self.stats.setdefault((method, regime), MethodRegimeStats())
        s.total += 1
        if won:
            s.wins += 1

    def reliability(self, method: str, regime: str) -> Decimal:
        s = self.stats.get((method, regime))
        return s.reliability() if s is not None else Decimal("0.5")

    def weight(self, method: str, regime: str) -> Decimal:
        """Map measured reliability to a bounded vote weight.

        ``weight = 2 * reliability`` so 0.5→1.0 (neutral), 1.0→2.0, 0→0, then
        clamped to [MIN_WEIGHT, MAX_WEIGHT]. A method proven in this regime is
        heard more loudly than one that is merely loud.
        """
        w = self.reliability(method, regime) * Decimal(2)
        return max(MIN_WEIGHT, min(MAX_WEIGHT, w))

    def weighted_vote(
        self, reads: Mapping[str, AnalysisRead], regime: str
    ) -> WeightedVote:
        """Combine method reads into one reliability-weighted verdict for ``regime``."""
        bull = _ZERO
        bear = _ZERO
        contributions: list[tuple[str, Decimal]] = []
        for name, read in reads.items():
            w = self.weight(name, regime)
            contribution = read.strength * w
            if read.direction == BULL:
                bull += contribution
                signed = contribution
            elif read.direction == BEAR:
                bear += contribution
                signed = -contribution
            else:
                signed = _ZERO
            contributions.append((name, signed))
        total = bull + bear
        score = ((bull - bear) / total).quantize(Decimal("0.000001")) if total > 0 else _ZERO
        if score >= self.decision_threshold:
            direction = BULL
        elif score <= -self.decision_threshold:
            direction = BEAR
        else:
            direction = NEUTRAL
        return WeightedVote(
            direction=direction,
            score=score,
            bull_weight=bull,
            bear_weight=bear,
            contributions=tuple(contributions),
        )

    # ── persistence (Layer 2 saves/restores the learned table) ────────
    def to_dict(self) -> dict[str, dict[str, int]]:
        return {
            f"{method}|{regime}": {"wins": s.wins, "total": s.total}
            for (method, regime), s in self.stats.items()
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Mapping[str, int]]) -> SwarmMetaLearner:
        stats: dict[tuple[str, str], MethodRegimeStats] = {}
        for key, rec in data.items():
            method, _, regime = key.partition("|")
            stats[(method, regime)] = MethodRegimeStats(
                wins=int(rec.get("wins", 0)), total=int(rec.get("total", 0))
            )
        return cls(stats=stats)
