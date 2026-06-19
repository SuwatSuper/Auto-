# Tests — regime-aware swarm meta-learner (U3)
from __future__ import annotations

from decimal import Decimal

from domain.analytics.swarm_meta import (
    MAX_WEIGHT,
    MIN_WEIGHT,
    NEUTRAL_WEIGHT,
    MethodRegimeStats,
    SwarmMetaLearner,
)
from domain.analytics.swarm_methods import BEAR, BULL, NEUTRAL, AnalysisRead

D = Decimal


def _read(direction: str, strength: str) -> AnalysisRead:
    return AnalysisRead(direction, D(strength), "t")


# ── reliability + weighting ──────────────────────────────────────────
def test_no_history_is_neutral_weight() -> None:
    m = SwarmMetaLearner()
    assert m.reliability("ema_cross", "TREND_UP") == D("0.5")
    assert m.weight("ema_cross", "TREND_UP") == NEUTRAL_WEIGHT


def test_accurate_method_gets_more_weight() -> None:
    m = SwarmMetaLearner()
    for _ in range(20):
        m.record("ema_cross", "TREND_UP", won=True)
    for _ in range(20):
        m.record("rsi", "TREND_UP", won=False)
    assert m.weight("ema_cross", "TREND_UP") > NEUTRAL_WEIGHT
    assert m.weight("rsi", "TREND_UP") < NEUTRAL_WEIGHT
    assert m.weight("ema_cross", "TREND_UP") > m.weight("rsi", "TREND_UP")


def test_weights_are_bounded() -> None:
    m = SwarmMetaLearner()
    for _ in range(500):
        m.record("perfect", "RANGE", won=True)
        m.record("hopeless", "RANGE", won=False)
    assert m.weight("perfect", "RANGE") <= MAX_WEIGHT
    assert m.weight("hopeless", "RANGE") >= MIN_WEIGHT


def test_reliability_is_regime_specific() -> None:
    m = SwarmMetaLearner()
    for _ in range(20):
        m.record("ema_cross", "TREND_UP", won=True)
        m.record("ema_cross", "RANGE", won=False)
    assert m.weight("ema_cross", "TREND_UP") > m.weight("ema_cross", "RANGE")


def test_stats_reliability_laplace() -> None:
    s = MethodRegimeStats(wins=1, total=2)
    assert s.reliability() == D("2") / D("4")  # (1+1)/(2+2)


# ── weighted voting ──────────────────────────────────────────────────
def test_equal_weight_vote_when_untrained() -> None:
    m = SwarmMetaLearner()
    reads = {"a": _read(BULL, "0.8"), "b": _read(BEAR, "0.2")}
    vote = m.weighted_vote(reads, "RANGE")
    assert vote.direction == BULL          # 0.8 bull vs 0.2 bear
    assert vote.score > 0


def test_track_record_flips_the_vote() -> None:
    """The SAME reads resolve differently once the bear method proves reliable
    in this regime and the bull method proves unreliable."""
    reads = {"bull_method": _read(BULL, "0.5"), "bear_method": _read(BEAR, "0.5")}

    untrained = SwarmMetaLearner()
    assert untrained.weighted_vote(reads, "TREND_DOWN").direction == NEUTRAL  # tie

    trained = SwarmMetaLearner()
    for _ in range(40):
        trained.record("bear_method", "TREND_DOWN", won=True)
        trained.record("bull_method", "TREND_DOWN", won=False)
    vote = trained.weighted_vote(reads, "TREND_DOWN")
    assert vote.direction == BEAR
    assert vote.score < 0
    assert vote.bear_weight > vote.bull_weight


def test_neutral_reads_do_not_move_score() -> None:
    m = SwarmMetaLearner()
    reads = {"a": _read(NEUTRAL, "0.9"), "b": _read(NEUTRAL, "0.9")}
    vote = m.weighted_vote(reads, "RANGE")
    assert vote.direction == NEUTRAL and vote.score == D("0")
    assert dict(vote.contributions)["a"] == D("0")


def test_below_threshold_is_neutral() -> None:
    m = SwarmMetaLearner(decision_threshold=D("0.5"))
    reads = {"a": _read(BULL, "0.55"), "b": _read(BEAR, "0.45")}
    # net score = (0.55-0.45)/1.0 = 0.1 < 0.5 → NEUTRAL
    assert m.weighted_vote(reads, "RANGE").direction == NEUTRAL


# ── persistence ──────────────────────────────────────────────────────
def test_to_from_dict_roundtrip() -> None:
    m = SwarmMetaLearner()
    m.record("ema_cross", "TREND_UP", won=True)
    m.record("ema_cross", "TREND_UP", won=False)
    m.record("rsi", "RANGE", won=True)
    restored = SwarmMetaLearner.from_dict(m.to_dict())
    assert restored.weight("ema_cross", "TREND_UP") == m.weight("ema_cross", "TREND_UP")
    assert restored.reliability("rsi", "RANGE") == m.reliability("rsi", "RANGE")
