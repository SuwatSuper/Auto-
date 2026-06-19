# Layer 1 — Domain (tests/domain/test_source_weights)
"""Task 2: dynamic vote-weighting from measured trade win-rate."""
from __future__ import annotations

from domain.analytics.source_weights import (
    MAX_WEIGHT,
    MUTED_WEIGHT,
    NEUTRAL_WEIGHT,
    SourcePerformance,
    weight_for_win_rate,
)


# ── weight_for_win_rate (the Task-2 contract) ────────────────────────
def test_unproven_source_is_neutral() -> None:
    # Below the sample floor, weight stays neutral regardless of win-rate.
    assert weight_for_win_rate(1.0, samples=2) == NEUTRAL_WEIGHT
    assert weight_for_win_rate(0.0, samples=4) == NEUTRAL_WEIGHT


def test_high_win_rate_is_boosted() -> None:
    w = weight_for_win_rate(0.70, samples=20)
    assert w > NEUTRAL_WEIGHT
    # A perfect record tops out at MAX_WEIGHT.
    assert weight_for_win_rate(1.0, samples=20) == MAX_WEIGHT


def test_low_win_rate_is_muted() -> None:
    assert weight_for_win_rate(0.44, samples=20) == MUTED_WEIGHT
    assert weight_for_win_rate(0.10, samples=20) == MUTED_WEIGHT


def test_neutral_band_stays_one() -> None:
    assert weight_for_win_rate(0.50, samples=20) == NEUTRAL_WEIGHT
    assert weight_for_win_rate(0.55, samples=20) == NEUTRAL_WEIGHT


# ── SourcePerformance ledger ─────────────────────────────────────────
def test_records_and_weights_per_source() -> None:
    perf = SourcePerformance(min_samples=5)
    # 6 wins, 0 losses → >55% → boosted
    for _ in range(6):
        perf.record("winner", won=True)
    # 1 win, 5 losses → <45% → muted
    perf.record("loser", won=True)
    for _ in range(5):
        perf.record("loser", won=False)

    assert perf.weight("winner") == MAX_WEIGHT
    assert perf.weight("loser") == MUTED_WEIGHT
    # an untracked source defaults to neutral
    assert perf.weight("unknown") == NEUTRAL_WEIGHT

    weights = perf.weights()
    assert weights["winner"] == MAX_WEIGHT and weights["loser"] == MUTED_WEIGHT
    assert perf.win_rate("winner") == 1.0
    assert perf.samples("loser") == 6


def test_record_many_credits_every_voter() -> None:
    perf = SourcePerformance(min_samples=1)
    perf.record_many(["a", "b", "c"], won=True)
    assert perf.win_rate("a") == 1.0 and perf.win_rate("b") == 1.0
    perf.record("", won=True)  # empty source ignored
    assert "" not in perf.weights()


def test_persistence_roundtrip() -> None:
    perf = SourcePerformance()
    perf.record_many(["x"], won=True)
    perf.record("x", won=False)
    blob = perf.to_dict()
    restored = SourcePerformance()
    restored.load_dict(blob)
    assert restored.samples("x") == 2
    assert restored.win_rate("x") == 0.5


def test_summary_shape() -> None:
    perf = SourcePerformance(min_samples=1)
    perf.record("s", won=True)
    s = perf.summary()["s"]
    assert set(s) == {"win_rate", "samples", "weight"}
