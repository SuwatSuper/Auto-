# Tests — pure-numpy win-probability model (U2)
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from domain.analytics.ml_winprob import (
    FEATURE_NAMES,
    N_FEATURES,
    StandardScaler,
    ValidationResult,
    WinProbModel,
    cold_start_ok,
    entry_features,
    fit_logistic,
    walk_forward_validate,
)

D = Decimal


def _ramp(n: int, start: float = 100.0, step: float = 1.0) -> list[Decimal]:
    return [Decimal(str(start + i * step)) for i in range(n)]


# ── feature extraction ───────────────────────────────────────────────
def test_feature_vector_has_expected_arity() -> None:
    feats = entry_features(_ramp(60), 59, regime="TREND_UP")
    assert len(feats) == N_FEATURES == len(FEATURE_NAMES)


def test_warmup_window_returns_neutral_defaults() -> None:
    feats = entry_features(_ramp(3), 2, imbalance=D("0.2"), sentiment=D("-0.3"),
                           regime="RANGE", p_win_rule=D("0.7"))
    # rsi neutral 0.5, gap/mom/vol 0, passthroughs intact, regime 0
    assert feats[0] == 0.5
    assert feats[1] == 0.0 and feats[2] == 0.0 and feats[3] == 0.0
    assert feats[4] == pytest.approx(0.2)
    assert feats[5] == pytest.approx(-0.3)
    assert feats[6] == 0.0
    assert feats[7] == pytest.approx(0.7)


def test_regime_trend_encoding() -> None:
    assert entry_features(_ramp(60), 59, regime="TREND_UP")[6] == 1.0
    assert entry_features(_ramp(60), 59, regime="TREND_DOWN")[6] == -1.0
    assert entry_features(_ramp(60), 59, regime="HIGH_VOL")[6] == 0.0


def test_uptrend_features_are_bullish() -> None:
    feats = entry_features(_ramp(60), 59)
    assert feats[1] > 0      # ema_gap positive (fast above slow)
    assert feats[2] > 0      # momentum positive
    assert feats[0] > 0.5    # rsi elevated in a clean uptrend


def test_no_lookahead_future_bars_cannot_leak() -> None:
    """Tampering with bars AFTER the entry must not change the entry's features."""
    closes = _ramp(200)
    feats = entry_features(closes, 100, imbalance=D("0.1"), regime="TREND_UP", p_win_rule=D("0.6"))
    tampered = list(closes)
    for j in range(101, 200):
        tampered[j] = Decimal("9999999")  # absurd future spikes
    feats_tampered = entry_features(tampered, 100, imbalance=D("0.1"), regime="TREND_UP", p_win_rule=D("0.6"))
    assert feats == feats_tampered


def test_different_entry_index_changes_features() -> None:
    closes = _ramp(200)
    assert entry_features(closes, 60) != entry_features(closes, 150)


# ── scaler ───────────────────────────────────────────────────────────
def test_scaler_centres_and_handles_constant_column() -> None:
    x = np.array([[1.0, 5.0], [3.0, 5.0], [5.0, 5.0]], dtype=np.float64)
    sc = StandardScaler.fit(x)
    out = sc.transform(x)
    assert out[:, 0].mean() == pytest.approx(0.0)
    assert np.allclose(out[:, 1], 0.0)  # constant column → 0, never NaN/inf


# ── model fit / predict / determinism / persistence ──────────────────
def _separable() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    x = rng.normal(size=(200, N_FEATURES))
    y = (x[:, 0] + 0.5 * x[:, 1] > 0).astype(np.float64)
    return x, y


def test_fit_is_deterministic() -> None:
    x, y = _separable()
    m1 = fit_logistic(x, y)
    m2 = fit_logistic(x, y)
    assert np.array_equal(m1.weights, m2.weights)


def test_model_learns_separable_pattern() -> None:
    x, y = _separable()
    model = fit_logistic(x, y, epochs=800)
    preds = (model.predict_proba(x) >= 0.5).astype(np.float64)
    assert (preds == y).mean() > 0.9


def test_predict_one_and_proba_range() -> None:
    x, y = _separable()
    model = fit_logistic(x, y)
    p = model.predict_one(x[0])
    assert 0.0 < p < 1.0
    probs = model.predict_proba(x)
    assert probs.shape == (200,)
    assert ((probs > 0.0) & (probs < 1.0)).all()


def test_to_from_dict_roundtrip() -> None:
    x, y = _separable()
    model = fit_logistic(x, y)
    restored = WinProbModel.from_dict(model.to_dict())
    assert np.allclose(model.predict_proba(x), restored.predict_proba(x))


# ── cold start ───────────────────────────────────────────────────────
def test_cold_start_guard() -> None:
    assert not cold_start_ok(50, min_samples=100)
    assert cold_start_ok(100, min_samples=100)
    assert cold_start_ok(1, min_samples=0)  # floor keeps min_samples >= 1


# ── walk-forward validation + A/B ────────────────────────────────────
def _signal_dataset(n: int = 400) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(n, N_FEATURES))
    true_w = np.array([2.0, -1.5, 1.0, 0, 0, 0, 0, 0], dtype=np.float64)
    p = 1.0 / (1.0 + np.exp(-(x @ true_w)))
    y = (rng.uniform(size=n) < p).astype(np.float64)
    pnl = np.where(y == 1.0, 1.0, -1.0) + rng.normal(scale=0.1, size=n)
    rule_scores = np.full(n, 0.5)  # the baseline rule takes every setup
    return x, y, pnl, rule_scores


def test_walk_forward_model_beats_take_everything_rule() -> None:
    x, y, pnl, rule = _signal_dataset()
    res = walk_forward_validate(x, y, pnl, rule, n_splits=4, threshold=0.5)
    assert isinstance(res, ValidationResult)
    assert res.n_test > 0
    assert res.model_accuracy > 0.6
    # The learned model selectively skips losers → higher OOS expectancy.
    assert res.model_expectancy > res.rule_expectancy
    assert res.use_model is True
    assert res.model_take_rate < 1.0      # it really does skip some trades
    assert "USE MODEL" in res.summary


def test_walk_forward_skips_single_class_folds() -> None:
    n = 20
    rng = np.random.default_rng(1)
    x = rng.normal(size=(n, N_FEATURES))
    # fold size = 20 // 3 = 6. Fold-1 train y[:6] is all-zero → skipped.
    y = np.array([0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 0, 1], dtype=np.float64)
    pnl = np.where(y == 1.0, 1.0, -1.0)
    rule = np.full(n, 0.5)
    res = walk_forward_validate(x, y, pnl, rule, n_splits=2)
    assert res.n_test == 8  # only fold-2's unseen tail was graded


def test_walk_forward_all_one_class_uses_no_model() -> None:
    n = 30
    x = np.random.default_rng(2).normal(size=(n, N_FEATURES))
    y = np.zeros(n, dtype=np.float64)  # every fold degenerate
    pnl = np.full(n, -1.0)
    rule = np.full(n, 0.5)
    res = walk_forward_validate(x, y, pnl, rule, n_splits=3)
    assert res.n_test == 0
    assert res.use_model is False
    assert res.model_expectancy == 0.0
    assert "KEEP RULE" in res.summary


def test_walk_forward_rejects_too_few_samples() -> None:
    x = np.zeros((3, N_FEATURES), dtype=np.float64)
    y = np.array([0.0, 1.0, 0.0])
    with pytest.raises(ValueError, match="need at least"):
        walk_forward_validate(x, y, y, y, n_splits=4)
