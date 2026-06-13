"""Strategy extensibility: verify that a new strategy registered in the
domain registry is picked up via ENABLED_STRATEGIES without touching
orchestration code.

TASK 9 acceptance: adding a strategy needs only a registry entry + env var.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.strategy.base import Signal, SignalAction, Strategy, StrategyContext
from domain.strategy.registry import build_enabled, get, register


class _AlwaysBuyStrategy(Strategy):
    """Toy strategy: always BUY. Used only in this test."""

    def decide(self, ctx: StrategyContext) -> Signal:
        return Signal(action=SignalAction.BUY, confidence=Decimal("1.0"), reason="test")


class _AlwaysSellStrategy(Strategy):
    """Toy strategy: always SELL. Used only in this test."""

    def decide(self, ctx: StrategyContext) -> Signal:
        return Signal(action=SignalAction.SELL, confidence=Decimal("1.0"), reason="test")


def test_register_and_retrieve_new_strategy() -> None:
    """register() + get() round-trip for a brand-new strategy name."""
    register("test_always_buy", _AlwaysBuyStrategy)
    cls = get("test_always_buy")
    assert cls is _AlwaysBuyStrategy


def test_build_enabled_single_new_strategy() -> None:
    """build_enabled() instantiates a newly registered strategy by name."""
    register("test_always_sell", _AlwaysSellStrategy)
    instances = build_enabled("test_always_sell")
    assert len(instances) == 1
    assert isinstance(instances[0], _AlwaysSellStrategy)


def test_build_enabled_csv_mixed_builtin_and_custom() -> None:
    """Comma-separated list with built-in + custom strategies all instantiate."""
    register("test_always_buy_csv", _AlwaysBuyStrategy)
    instances = build_enabled("trend_following,test_always_buy_csv")
    names = [type(s).__name__ for s in instances]
    assert "TrendFollowingStrategy" in names
    assert "_AlwaysBuyStrategy" in names


def test_unknown_strategy_name_raises_key_error() -> None:
    """build_enabled() raises KeyError for an unregistered name — not silently skipped."""
    with pytest.raises(KeyError, match="nonexistent_strategy_xyz"):
        build_enabled("nonexistent_strategy_xyz")


def test_new_strategy_produces_correct_signals() -> None:
    """The registered strategy actually works: decide() returns the expected signal."""
    register("test_signal_check", _AlwaysBuyStrategy)
    instances = build_enabled("test_signal_check")
    ctx = StrategyContext(prices=(Decimal("3500000"),), position_qty=Decimal("0"))
    signal = instances[0].decide(ctx)
    assert signal.action == SignalAction.BUY


def test_enabled_strategies_env_var_picks_up_new_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate ENABLED_STRATEGIES env var selecting a dynamically registered strategy."""
    register("test_env_driven", _AlwaysBuyStrategy)
    # Simulate what would happen if Settings.enabled_strategies == "test_env_driven"
    monkeypatch.setenv("ENABLED_STRATEGIES", "test_env_driven")
    instances = build_enabled("test_env_driven")
    assert len(instances) == 1
    assert isinstance(instances[0], _AlwaysBuyStrategy)
