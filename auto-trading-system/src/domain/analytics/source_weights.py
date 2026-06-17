# Layer 1 — Domain (analytics/source_weights)
"""Dynamic vote-weighting from REAL trade outcomes (Task 2 — no LLM).

The Supreme commander tallies a weighted multi-agent consensus. This module owns
the pure, deterministic rule that turns each signal source's MEASURED trade
win-rate (routed back from ``paper.events``) into a vote weight:

  • win-rate > 55%  → weight > 1.0 (heard louder, capped at MAX_WEIGHT)
  • win-rate < 45%  → weight 0.0 (muted: the source's vote is ignored)
  • 45%–55%, or too few graded trades → weight 1.0 (neutral)

Honest by construction: weights move only on graded Win/Loss outcomes and a thin
record stays neutral until ``MIN_SAMPLES`` trades have been attributed. Pure
Python, no I/O — the orchestration layer feeds outcomes and reads weights.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Win-rate thresholds (the Task-2 contract).
WIN_RATE_BOOST = 0.55   # above → increased weight
WIN_RATE_MUTE = 0.45    # below → muted (0.0)

MUTED_WEIGHT = 0.0
NEUTRAL_WEIGHT = 1.0
MAX_WEIGHT = 2.0

# Trades attributed to a source before its win-rate is trusted (else neutral).
MIN_SAMPLES = 5


def weight_for_win_rate(win_rate: float, samples: int, *, min_samples: int = MIN_SAMPLES) -> float:
    """Map a measured win-rate (0..1) over ``samples`` graded trades to a weight.

    Returns NEUTRAL_WEIGHT until ``min_samples`` outcomes exist, then boosts a
    >55% source toward MAX_WEIGHT and mutes a <45% source to 0.0.
    """
    if samples < min_samples:
        return NEUTRAL_WEIGHT
    if win_rate < WIN_RATE_MUTE:
        return MUTED_WEIGHT
    if win_rate > WIN_RATE_BOOST:
        # Linear ramp: 0.55 → 1.0, 1.0 → MAX_WEIGHT.
        span = 1.0 - WIN_RATE_BOOST
        boosted = NEUTRAL_WEIGHT + (win_rate - WIN_RATE_BOOST) / span * (MAX_WEIGHT - NEUTRAL_WEIGHT)
        return min(MAX_WEIGHT, boosted)
    return NEUTRAL_WEIGHT


@dataclass
class _SourceRecord:
    wins: int = 0
    total: int = 0

    def win_rate(self) -> float:
        return self.wins / self.total if self.total else 0.0


@dataclass
class SourcePerformance:
    """Per-source Win/Loss ledger + the derived vote weights.

    The runtime records each attributed trade outcome (``record``) and reads the
    resulting weight map (``weights``) to push into the Supreme commander.
    """

    min_samples: int = MIN_SAMPLES
    _records: dict[str, _SourceRecord] = field(default_factory=dict)

    def record(self, source: str, won: bool) -> None:
        """Grade one real trade outcome for ``source`` (won = pnl_net > 0)."""
        if not source:
            return
        rec = self._records.setdefault(source, _SourceRecord())
        rec.total += 1
        if won:
            rec.wins += 1

    def record_many(self, sources: list[str], won: bool) -> None:
        """Attribute one trade's outcome to every source that voted for it."""
        for s in sources:
            self.record(s, won)

    def win_rate(self, source: str) -> float | None:
        rec = self._records.get(source)
        return rec.win_rate() if rec is not None and rec.total else None

    def samples(self, source: str) -> int:
        rec = self._records.get(source)
        return rec.total if rec is not None else 0

    def weight(self, source: str) -> float:
        rec = self._records.get(source)
        if rec is None:
            return NEUTRAL_WEIGHT
        return weight_for_win_rate(rec.win_rate(), rec.total, min_samples=self.min_samples)

    def weights(self) -> dict[str, float]:
        """Current weight for every tracked source (for bulk push to Supreme)."""
        return {src: self.weight(src) for src in self._records}

    def summary(self) -> dict[str, dict[str, float | int]]:
        """Per-source {win_rate, samples, weight} for the dashboard / status."""
        out: dict[str, dict[str, float | int]] = {}
        for src, rec in self._records.items():
            out[src] = {
                "win_rate": round(rec.win_rate(), 4),
                "samples": rec.total,
                "weight": round(self.weight(src), 4),
            }
        return out

    # ── persistence (so learned weights survive a restart) ────────────
    def to_dict(self) -> dict[str, dict[str, int]]:
        return {src: {"wins": r.wins, "total": r.total} for src, r in self._records.items()}

    def load_dict(self, data: dict[str, dict[str, int]]) -> None:
        for src, rec in data.items():
            if isinstance(rec, dict):
                self._records[src] = _SourceRecord(
                    wins=int(rec.get("wins", 0)), total=int(rec.get("total", 0))
                )
