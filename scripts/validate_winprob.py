#!/usr/bin/env python3
# Phase-10 U2 — honest out-of-sample validation of the ML win-probability model.
"""Walk-forward validate the learned win-probability model against the baseline
rule, on REAL track record when it exists, otherwise on a clearly-labeled
synthetic demo.

Usage:
    PYTHONPATH=src python scripts/validate_winprob.py [data_dir]

Honesty: with real ``data/trades_*.csv`` this prints the model's *out-of-sample*
expectancy vs the rule's — the only number that justifies trusting the model.
With no track record yet it prints a SYNTHETIC demonstration so the methodology
can be inspected; that synthetic line is not a claim about live performance.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

from domain.analytics.ml_winprob import (
    N_FEATURES,
    cold_start_ok,
    walk_forward_validate,
)

_REGIME_TREND = {"TREND_UP": 1.0, "TREND_DOWN": -1.0}


def _load_real(data_dir: Path) -> tuple[np.ndarray, ...] | None:
    """Build (X, y, pnl, rule_scores) from real closed-trade CSVs, or None.

    Only the columns recorded AT ENTRY are used as features (regime,
    win_prob_est) plus realized net pnl as the label — no lookahead.
    """
    rows: list[dict[str, str]] = []
    for csv_path in sorted(data_dir.glob("trades_*.csv")):
        with csv_path.open(encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    rows = [r for r in rows if r.get("pnl_net") or r.get("pnl")]
    if len(rows) < 30:
        return None
    rows.sort(key=lambda r: int(r.get("ts_ms", "0") or "0"))
    feats: list[list[float]] = []
    y: list[float] = []
    pnl: list[float] = []
    rule: list[float] = []
    for r in rows:
        net = float(r.get("pnl_net") or r.get("pnl") or 0.0)
        p_rule = float(r.get("win_prob_est") or 0.0)
        regime = r.get("regime", "RANGE")
        # Minimal honest feature set from what's logged at entry. The richer
        # entry_features() set is used live; offline we use what the ledger kept.
        row = [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, _REGIME_TREND.get(regime, 0.0), p_rule]
        assert len(row) == N_FEATURES
        feats.append(row)
        y.append(1.0 if net > 0 else 0.0)
        pnl.append(net)
        rule.append(p_rule if p_rule > 0 else 0.5)
    return (
        np.asarray(feats, dtype=np.float64),
        np.asarray(y, dtype=np.float64),
        np.asarray(pnl, dtype=np.float64),
        np.asarray(rule, dtype=np.float64),
    )


def _synthetic(n: int = 400) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(n, N_FEATURES))
    true_w = np.array([2.0, -1.5, 1.0, 0, 0, 0, 0, 0], dtype=np.float64)
    p = 1.0 / (1.0 + np.exp(-(x @ true_w)))
    y = (rng.uniform(size=n) < p).astype(np.float64)
    pnl = np.where(y == 1.0, 1.0, -1.0) + rng.normal(scale=0.1, size=n)
    rule = np.full(n, 0.5)  # baseline rule: take every setup
    return x, y, pnl, rule


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    real = _load_real(data_dir)
    if real is not None:
        x, y, pnl, rule = real
        source = f"REAL track record ({len(y)} closed trades from {data_dir}/trades_*.csv)"
    else:
        x, y, pnl, rule = _synthetic()
        source = "SYNTHETIC demonstration (no real track record yet — NOT a live-performance claim)"

    print(f"source : {source}")
    print(f"samples: {len(y)} · cold-start ok (>=100): {cold_start_ok(len(y))}")
    res = walk_forward_validate(x, y, pnl, rule, n_splits=4)
    print(res.summary)
    print(f"verdict: {'use the learned model' if res.use_model else 'keep the rule'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
