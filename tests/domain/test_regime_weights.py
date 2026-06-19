# Tests — adaptive regime → strategy-weight switching (U5)
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pandas as pd

from domain.analytics.regime import MarketRegime, classify_with_confidence
from domain.analytics.regime_weights import (
    STRATEGY_FAMILIES,
    adaptive_weights,
    canonical_regime,
    regime_strategy_weights,
)
from domain.analytics.swarm_meta import SwarmMetaLearner

D = Decimal


# ── canonicalization across both regime vocabularies ─────────────────
def test_canonical_regime_maps_both_spellings() -> None:
    assert canonical_regime("TRENDING_UP") == "TREND_UP"
    assert canonical_regime("trend_down") == "TREND_DOWN"
    assert canonical_regime("RANGING") == "RANGE"
    assert canonical_regime("RANGE") == "RANGE"
    assert canonical_regime("HIGH_VOL") == "HIGH_VOL"
    assert canonical_regime("BREAKOUT") == "BREAKOUT"
    assert canonical_regime("whatever") == "UNKNOWN"


# ── base regime playbook ─────────────────────────────────────────────
def test_trend_favours_trend_following_over_mean_reversion() -> None:
    w = regime_strategy_weights("TREND_UP")
    assert w["trend_following"] > w["mean_reversion"]


def test_range_favours_mean_reversion_over_trend_following() -> None:
    w = regime_strategy_weights("RANGE")
    assert w["mean_reversion"] > w["trend_following"]


def test_high_vol_throttles_everything() -> None:
    w = regime_strategy_weights("HIGH_VOL")
    assert all(v <= D("0.8") for v in w.values())


def test_unknown_regime_is_neutral() -> None:
    w = regime_strategy_weights("nonsense")
    assert set(w) == set(STRATEGY_FAMILIES)
    assert all(v == D("1.0") for v in w.values())


# ── composition with the U3 meta-learner ─────────────────────────────
def test_adaptive_weights_no_meta_is_base() -> None:
    assert adaptive_weights("TREND_UP") == regime_strategy_weights("TREND_UP")


def test_reliability_boosts_proven_family_in_regime() -> None:
    meta = SwarmMetaLearner()
    for _ in range(50):
        meta.record("trend_following", "TREND_UP", won=True)   # proven here
        meta.record("breakout", "TREND_UP", won=False)         # unreliable here
    base = regime_strategy_weights("TREND_UP")
    adapted = adaptive_weights("TREND_UP", meta)
    assert adapted["trend_following"] > base["trend_following"]
    assert adapted["breakout"] < base["breakout"]


def test_adaptive_weights_are_bounded() -> None:
    meta = SwarmMetaLearner()
    for _ in range(500):
        meta.record("momentum", "BREAKOUT", won=True)
    adapted = adaptive_weights("BREAKOUT", meta)
    assert all(D("0.2") <= v <= D("3.0") for v in adapted.values())


# ── confidence-aware classifier (additive; classify() unchanged) ─────
def _trend_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.RandomState(0)
    close = np.linspace(10000.0, 80000.0, n) + rng.randn(n) * 50
    return pd.DataFrame({
        "open": close, "high": close * 1.001, "low": close * 0.999,
        "close": close, "volume": np.abs(rng.randn(n)) * 1000 + 100,
    })


def test_classify_with_confidence_trend() -> None:
    read = classify_with_confidence(_trend_df(), adx_trend_threshold=10.0, atr_pct_highvol_threshold=5.0)
    assert read.regime == MarketRegime.TREND_UP
    assert 0.0 < read.confidence <= 1.0
    assert read.adx > 10.0


def test_classify_with_confidence_insufficient_bars() -> None:
    read = classify_with_confidence(_trend_df(n=30))
    assert read.regime == MarketRegime.RANGE and read.confidence == 0.0


def test_classify_with_confidence_high_vol() -> None:
    df = _trend_df().copy()
    df["high"] = df["close"] * 1.5
    df["low"] = df["close"] * 0.5
    read = classify_with_confidence(df, atr_pct_highvol_threshold=3.0)
    assert read.regime == MarketRegime.HIGH_VOL
    assert read.confidence > 0.0


def test_classify_with_confidence_range() -> None:
    rng = np.random.RandomState(7)
    n = 200
    close = np.ones(n) * 50000.0 + rng.randn(n) * 10
    df = pd.DataFrame({
        "open": close, "high": close + 5, "low": close - 5,
        "close": close, "volume": np.abs(rng.randn(n)) * 1000 + 100,
    })
    read = classify_with_confidence(df, adx_trend_threshold=50.0, atr_pct_highvol_threshold=5.0)
    assert read.regime == MarketRegime.RANGE
