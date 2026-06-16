# Layer 1 — Domain (analytics/ml_winprob)
"""Self-improving win-probability model — pure-numpy logistic regression.

The rule-based gate asks "did ≥X% of comparable historical setups win?". This
module lets the agent learn the *shape* of a winning setup from its own track
record: it maps the features present at entry (TA + regime + order-book
imbalance + sentiment + the rule's own estimate) to the probability that the
trade closes net-positive after fees.

It is honest by construction and respects every Phase-10 guard:

  • **Pure & deterministic** — numpy only (no sklearn, no I/O, no randomness:
    full-batch gradient descent from a zero start → identical model every run).
    This keeps it inside Layer 1 (domain may import numpy) and reproducible.
  • **Cold-start fallback** — :func:`cold_start_ok` refuses the model until the
    track record is large enough; below that the caller uses the rule.
  • **Walk-forward validation** — :func:`walk_forward_validate` trains on the
    past and scores the *unseen* future, reporting out-of-sample accuracy and
    expectancy so a model is only ever trusted on evidence.
  • **A/B vs the rule** — the validation only sets ``use_model`` when the model's
    out-of-sample expectancy beats the baseline rule's. A pretty model that
    loses on unseen data is rejected.
  • **No lookahead** — :func:`entry_features` consumes only the window up to the
    entry bar; a dedicated test proves future bars cannot leak in.

The model outputs a *probability*, never a promise — it still flows through the
existing entry gate and the immutable risk fence unchanged.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from numpy.typing import NDArray

from domain.analytics.indicators import ema, rsi_wilder

Array = NDArray[np.float64]

# Ordered feature vocabulary — index position is the contract between the
# feature builder and the trained model. Never reorder without retraining.
FEATURE_NAMES: tuple[str, ...] = (
    "rsi",          # Wilder RSI / 100, neutral 0.5
    "ema_gap",      # (ema_fast - ema_slow) / ema_slow
    "momentum",     # rate of change over `mom_n` bars
    "volatility",   # stdev/mean of the recent window
    "imbalance",    # order-book imbalance [-1, +1]
    "sentiment",    # news sentiment [-1, +1]
    "regime_trend", # +1 TREND_UP / -1 TREND_DOWN / 0 otherwise
    "p_win_rule",   # the rule-based win-probability estimate [0, 1]
)
N_FEATURES = len(FEATURE_NAMES)

_REGIME_TREND = {"TREND_UP": 1.0, "TREND_DOWN": -1.0}


# ── feature extraction (no lookahead) ────────────────────────────────
def entry_features(
    closes: Sequence[Decimal],
    idx: int,
    *,
    imbalance: Decimal = Decimal("0"),
    sentiment: Decimal = Decimal("0"),
    regime: str = "RANGE",
    p_win_rule: Decimal = Decimal("0"),
    fast: int = 12,
    slow: int = 26,
    mom_n: int = 10,
    vol_n: int = 20,
) -> list[float]:
    """Build the feature vector for an entry at bar ``idx``.

    Uses ONLY ``closes[: idx + 1]`` — bars after the entry are never read, so a
    feature can never encode the future it is meant to predict (the no-lookahead
    test tampers with future bars and asserts the vector is unchanged).
    """
    window = list(closes[: idx + 1])
    f_rsi = 0.5
    if len(window) >= 15:
        r = rsi_wilder(window, 14)[-1]
        if not r.is_nan():
            f_rsi = float(r) / 100.0

    f_gap = 0.0
    if len(window) >= slow + 1:
        ef = ema(window, fast)[-1]
        es = ema(window, slow)[-1]
        if es != 0:
            f_gap = float((ef - es) / es)

    f_mom = 0.0
    if len(window) >= mom_n + 1:
        base = window[-1 - mom_n]
        if base > 0:
            f_mom = float((window[-1] - base) / base)

    f_vol = 0.0
    if len(window) >= vol_n:
        w = window[-vol_n:]
        mean = sum(w, Decimal("0")) / Decimal(len(w))
        if mean > 0:
            var = sum(((x - mean) ** 2 for x in w), Decimal("0")) / Decimal(len(w))
            f_vol = float(var.sqrt() / mean)

    return [
        f_rsi,
        f_gap,
        f_mom,
        f_vol,
        float(imbalance),
        float(sentiment),
        _REGIME_TREND.get(regime, 0.0),
        float(p_win_rule),
    ]


# ── standardization + model ──────────────────────────────────────────
@dataclass(frozen=True)
class StandardScaler:
    """Per-feature mean/std for zero-centring inputs (std=1 floor avoids /0)."""

    mean: Array
    std: Array

    @classmethod
    def fit(cls, x: Array) -> StandardScaler:
        mean = x.mean(axis=0)
        std = x.std(axis=0)
        std = np.where(std < 1e-12, 1.0, std)
        return cls(mean=mean.astype(np.float64), std=std.astype(np.float64))

    def transform(self, x: Array) -> Array:
        return ((x - self.mean) / self.std).astype(np.float64)


def _sigmoid(z: Array) -> Array:
    return (1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))).astype(np.float64)


@dataclass(frozen=True)
class WinProbModel:
    """A trained logistic-regression win-probability model.

    ``weights`` has length ``N_FEATURES + 1`` — index 0 is the bias, the rest map
    to :data:`FEATURE_NAMES` in order. Inputs are standardized by ``scaler``.
    """

    weights: Array
    scaler: StandardScaler

    def predict_proba(self, x: Array) -> Array:
        """P(net-profit) in (0, 1) for each row of ``x`` (raw, unscaled)."""
        xs = self.scaler.transform(np.atleast_2d(x).astype(np.float64))
        z = self.weights[0] + xs @ self.weights[1:]
        return _sigmoid(z)

    def predict_one(self, features: Sequence[float]) -> float:
        """Convenience: probability for a single feature vector."""
        arr = np.asarray(features, dtype=np.float64).reshape(1, -1)
        return float(self.predict_proba(arr)[0])

    def to_dict(self) -> dict[str, list[float]]:
        """Serialize to JSON-friendly lists (Layer 2 persists to data/models/)."""
        return {
            "weights": [float(w) for w in self.weights],
            "scaler_mean": [float(m) for m in self.scaler.mean],
            "scaler_std": [float(s) for s in self.scaler.std],
        }

    @classmethod
    def from_dict(cls, data: dict[str, list[float]]) -> WinProbModel:
        return cls(
            weights=np.asarray(data["weights"], dtype=np.float64),
            scaler=StandardScaler(
                mean=np.asarray(data["scaler_mean"], dtype=np.float64),
                std=np.asarray(data["scaler_std"], dtype=np.float64),
            ),
        )


def fit_logistic(
    x: Array,
    y: Array,
    *,
    l2: float = 1.0,
    lr: float = 0.1,
    epochs: int = 500,
) -> WinProbModel:
    """Fit logistic regression by deterministic full-batch gradient descent.

    Zero-initialized weights + a fixed schedule → the same model every run (no
    seed, no shuffling). L2 regularization (not applied to the bias) curbs the
    overfitting the Phase-10 honesty rules warn about.
    """
    x = np.atleast_2d(x).astype(np.float64)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    n, k = x.shape
    scaler = StandardScaler.fit(x)
    xs = scaler.transform(x)
    xb = np.hstack([np.ones((n, 1)), xs])  # bias column
    w: Array = np.zeros(k + 1, dtype=np.float64)
    reg = np.ones(k + 1, dtype=np.float64)
    reg[0] = 0.0  # never regularize the bias
    for _ in range(max(1, epochs)):
        p = _sigmoid(xb @ w)
        grad = xb.T @ (p - y) / n + l2 * reg * w / n
        w = w - lr * grad
    return WinProbModel(weights=w.astype(np.float64), scaler=scaler)


# ── cold-start guard ─────────────────────────────────────────────────
def cold_start_ok(n_samples: int, min_samples: int = 100) -> bool:
    """True only when there is enough track record to trust a learned model.

    Below this the caller MUST fall back to the rule — a model fit on too little
    data is more confident than it has any right to be.
    """
    return n_samples >= max(1, min_samples)


# ── walk-forward validation + A/B selection ──────────────────────────
@dataclass(frozen=True)
class ValidationResult:
    """Out-of-sample evidence for whether to trust the model over the rule."""

    n_train: int
    n_test: int
    model_accuracy: float
    model_expectancy: float
    rule_expectancy: float
    model_take_rate: float
    rule_take_rate: float
    use_model: bool

    @property
    def summary(self) -> str:
        verdict = "USE MODEL" if self.use_model else "KEEP RULE"
        return (
            f"OOS n={self.n_test} (train {self.n_train}) · "
            f"model acc {self.model_accuracy * 100:.1f}% · "
            f"model E[pnl] {self.model_expectancy:+.4f} (take {self.model_take_rate * 100:.0f}%) "
            f"vs rule E[pnl] {self.rule_expectancy:+.4f} (take {self.rule_take_rate * 100:.0f}%) "
            f"→ {verdict}"
        )


def _mean_pnl(pnls: list[float]) -> float:
    """Mean realized pnl of the taken trades (0.0 when none were taken)."""
    return float(np.mean(pnls)) if pnls else 0.0


def walk_forward_validate(
    x: Array,
    y: Array,
    pnl: Array,
    rule_scores: Array,
    *,
    n_splits: int = 4,
    threshold: float = 0.5,
    l2: float = 1.0,
    lr: float = 0.1,
    epochs: int = 500,
) -> ValidationResult:
    """Expanding-window walk-forward: train on the past, score the unseen future.

    Data must already be in chronological order. For each fold the model is fit
    on everything before the fold and used to decide which of the fold's trades
    to *take* (proba ≥ ``threshold``); the rule takes trades where
    ``rule_scores ≥ threshold``. Out-of-sample expectancy is the mean realized
    pnl of the trades each policy would have taken. ``use_model`` is set only
    when the model's OOS expectancy is at least the rule's — never on backtest
    optimism alone.
    """
    x = np.atleast_2d(x).astype(np.float64)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    pnl = np.asarray(pnl, dtype=np.float64).reshape(-1)
    rule_scores = np.asarray(rule_scores, dtype=np.float64).reshape(-1)
    n = x.shape[0]
    splits = max(2, n_splits)
    fold = n // (splits + 1)
    if fold < 1:
        raise ValueError(f"need at least {splits + 1} samples for {splits} folds, got {n}")

    correct = 0
    graded = 0
    model_pnls: list[float] = []
    rule_pnls: list[float] = []
    n_train_last = 0
    for k in range(1, splits + 1):
        train_end = fold * k
        test_end = fold * (k + 1) if k < splits else n
        xt, yt = x[:train_end], y[:train_end]
        xv, yv, pv, rv = x[train_end:test_end], y[train_end:test_end], pnl[train_end:test_end], rule_scores[train_end:test_end]
        if len(xv) == 0 or len(np.unique(yt)) < 2:
            continue  # a degenerate fold (one class) teaches nothing — skip
        model = fit_logistic(xt, yt, l2=l2, lr=lr, epochs=epochs)
        proba = model.predict_proba(xv)
        preds = (proba >= 0.5).astype(np.float64)
        correct += int((preds == yv).sum())
        graded += len(yv)
        model_pnls.extend(pv[proba >= threshold].tolist())
        rule_pnls.extend(pv[rv >= threshold].tolist())
        n_train_last = train_end

    accuracy = correct / graded if graded else 0.0
    model_e = _mean_pnl(model_pnls)
    rule_e = _mean_pnl(rule_pnls)
    # Take-rate is "of all graded OOS setups, what fraction did this policy act
    # on" — the denominator is the graded count, not the taken count.
    model_take = len(model_pnls) / graded if graded else 0.0
    rule_take = len(rule_pnls) / graded if graded else 0.0
    return ValidationResult(
        n_train=n_train_last,
        n_test=graded,
        model_accuracy=accuracy,
        model_expectancy=model_e,
        rule_expectancy=rule_e,
        model_take_rate=model_take,
        rule_take_rate=rule_take,
        use_model=graded > 0 and model_e >= rule_e,
    )
