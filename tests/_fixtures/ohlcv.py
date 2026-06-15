# tests/_fixtures/ohlcv.py
"""Deterministic synthetic OHLCV fixture using a seeded random walk."""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Build a deterministic n-row OHLCV DataFrame using a fixed numpy RandomState.

    Starting price: 50_000 THB. Returns are i.i.d. ~N(0, 0.01).
    No CSV files or un-seeded randomness — same seed → identical output.
    """
    rng = np.random.RandomState(seed)
    returns = rng.randn(n) * 0.01
    close = np.cumprod(1.0 + returns) * 50_000.0
    high = close * (1.0 + np.abs(rng.randn(n)) * 0.005)
    low = close * (1.0 - np.abs(rng.randn(n)) * 0.005)
    open_ = close * (1.0 + rng.randn(n) * 0.003)
    volume = np.abs(rng.randn(n)) * 1_000.0 + 100.0
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )
