# Layer 1 — Domain (strategy/registry)
"""Strategy registry: register, retrieve, and build strategy instances by name."""
from __future__ import annotations

from domain.strategy.base import Strategy
from domain.strategy.breakout import BreakoutStrategy
from domain.strategy.breakout_ls import BreakoutLongShortStrategy
from domain.strategy.momentum_ls import MomentumLongShortStrategy
from domain.strategy.range_reversion import RangeReversionStrategy
from domain.strategy.reversion_ls import ReversionLongShortStrategy
from domain.strategy.trend_following import TrendFollowingStrategy

_REGISTRY: dict[str, type] = {
    "trend_following": TrendFollowingStrategy,
    "breakout": BreakoutStrategy,
    "range_reversion": RangeReversionStrategy,
    "momentum_ls": MomentumLongShortStrategy,
    "reversion_ls": ReversionLongShortStrategy,
    "breakout_ls": BreakoutLongShortStrategy,
}


def register(name: str, cls: type) -> None:
    """Register a strategy class under the given name."""
    _REGISTRY[name] = cls


def get(name: str) -> type:
    """Return strategy class for name; raises KeyError if not found."""
    return _REGISTRY[name]


def build_enabled(settings_csv: str) -> list[Strategy]:
    """Build instances for comma-separated strategy names.

    Unknown names raise KeyError. Empty string returns an empty list.
    """
    names = [n.strip() for n in settings_csv.split(",") if n.strip()]
    return [_REGISTRY[n]() for n in names]
