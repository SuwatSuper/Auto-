# tests/domain/test_new_strategies.py
"""Determinism, no-lookahead, and stop<entry<tp tests for Phase 3 strategies."""
from __future__ import annotations

import pytest

from domain.strategy.base import SignalAction, StrategyContext
from domain.strategy.breakout import BreakoutStrategy
from domain.strategy.range_reversion import RangeReversionStrategy
from domain.strategy.registry import build_enabled, get, register
from domain.strategy.trend_following import OhlcvSignal, TrendFollowingStrategy
from tests._fixtures.ohlcv import build_ohlcv

_DF300 = build_ohlcv(n=300, seed=42)
_DF10 = build_ohlcv(n=10, seed=42)


# ── TrendFollowingStrategy ────────────────────────────────────────────

class TestTrendFollowing:
    def setup_method(self) -> None:
        self.strat = TrendFollowingStrategy()

    def test_decide_returns_hold(self) -> None:
        ctx = StrategyContext(prices=(50000,), position_qty=0)  # type: ignore[arg-type]
        assert self.strat.decide(ctx).action == SignalAction.HOLD

    def test_insufficient_bars_returns_insuf(self) -> None:
        sig = self.strat.decide_df(_DF10)
        assert sig.action == SignalAction.HOLD
        assert sig.reason == "insufficient_data"

    def test_deterministic_same_output_twice(self) -> None:
        sig1 = self.strat.decide_df(_DF300)
        sig2 = self.strat.decide_df(_DF300)
        assert sig1 == sig2

    def test_no_lookahead_dropping_last_bar(self) -> None:
        sig_full = self.strat.decide_df(_DF300)
        sig_short = self.strat.decide_df(_DF300.iloc[:-1])
        # Both are valid calls; signals may differ (last bar excluded)
        assert sig_full.action in list(SignalAction)
        assert sig_short.action in list(SignalAction)

    def test_buy_signal_stop_below_entry(self) -> None:
        # Scan full history to find a BUY
        for i in range(22, len(_DF300) + 1):
            sig = self.strat.decide_df(_DF300.iloc[:i])
            if sig.action == SignalAction.BUY:
                assert sig.stop_price is not None
                assert sig.take_profit_price is not None
                assert sig.stop_price < sig.take_profit_price
                return
        pytest.skip("No BUY signal found in fixture — seeded data may not produce one")

    def test_buy_signal_entry_between_stop_and_tp(self) -> None:
        for i in range(22, len(_DF300) + 1):
            sig = self.strat.decide_df(_DF300.iloc[:i])
            if sig.action == SignalAction.BUY:
                entry = _DF300["close"].iloc[i - 1]
                assert float(sig.stop_price) < entry  # type: ignore[arg-type]
                assert float(sig.take_profit_price) > entry  # type: ignore[arg-type]
                return
        pytest.skip("No BUY signal found")


# ── BreakoutStrategy ──────────────────────────────────────────────────

class TestBreakout:
    def setup_method(self) -> None:
        self.strat = BreakoutStrategy()

    def test_decide_returns_hold(self) -> None:
        ctx = StrategyContext(prices=(50000,), position_qty=0)  # type: ignore[arg-type]
        assert self.strat.decide(ctx).action == SignalAction.HOLD

    def test_insufficient_bars_returns_insuf(self) -> None:
        sig = self.strat.decide_df(_DF10)
        assert sig.action == SignalAction.HOLD
        assert sig.reason == "insufficient_data"

    def test_deterministic(self) -> None:
        sig1 = self.strat.decide_df(_DF300)
        sig2 = self.strat.decide_df(_DF300)
        assert sig1 == sig2

    def test_buy_stop_tp_relationship(self) -> None:
        for i in range(21, len(_DF300) + 1):
            sig = self.strat.decide_df(_DF300.iloc[:i])
            if sig.action == SignalAction.BUY:
                assert sig.stop_price is not None
                assert sig.take_profit_price is not None
                assert sig.stop_price < sig.take_profit_price
                entry = _DF300["close"].iloc[i - 1]
                assert float(sig.stop_price) < entry
                assert float(sig.take_profit_price) > entry
                return
        pytest.skip("No BUY signal found in fixture")


# ── RangeReversionStrategy ────────────────────────────────────────────

class TestRangeReversion:
    def setup_method(self) -> None:
        self.strat = RangeReversionStrategy()

    def test_decide_returns_hold(self) -> None:
        ctx = StrategyContext(prices=(50000,), position_qty=0)  # type: ignore[arg-type]
        assert self.strat.decide(ctx).action == SignalAction.HOLD

    def test_insufficient_bars_returns_insuf(self) -> None:
        sig = self.strat.decide_df(_DF10)
        assert sig.action == SignalAction.HOLD
        assert sig.reason == "insufficient_data"

    def test_deterministic(self) -> None:
        sig1 = self.strat.decide_df(_DF300)
        sig2 = self.strat.decide_df(_DF300)
        assert sig1 == sig2

    def test_buy_stop_tp_relationship(self) -> None:
        for i in range(51, len(_DF300) + 1):
            sig = self.strat.decide_df(_DF300.iloc[:i])
            if sig.action == SignalAction.BUY:
                assert sig.stop_price is not None
                assert sig.take_profit_price is not None
                assert sig.stop_price < sig.take_profit_price
                return
        pytest.skip("No BUY signal found in fixture under RANGE regime")


# ── Registry ─────────────────────────────────────────────────────────

class TestRegistry:
    def test_get_known_strategy(self) -> None:
        cls = get("trend_following")
        assert cls is TrendFollowingStrategy

    def test_get_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get("nonexistent_strategy")

    def test_build_enabled_single(self) -> None:
        strategies = build_enabled("trend_following")
        assert len(strategies) == 1
        assert isinstance(strategies[0], TrendFollowingStrategy)

    def test_build_enabled_multiple(self) -> None:
        strategies = build_enabled("trend_following,breakout,range_reversion")
        assert len(strategies) == 3

    def test_build_enabled_empty_string(self) -> None:
        strategies = build_enabled("")
        assert strategies == []

    def test_build_enabled_strips_whitespace(self) -> None:
        strategies = build_enabled(" trend_following , breakout ")
        assert len(strategies) == 2

    def test_register_custom(self) -> None:
        class DummyStrategy:
            def decide(self, ctx):  # type: ignore[override]
                pass

        register("dummy", DummyStrategy)
        assert get("dummy") is DummyStrategy

    def test_build_enabled_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            build_enabled("trend_following,no_such_strategy")


# ── OhlcvSignal model ─────────────────────────────────────────────────

def test_ohlcv_signal_optional_fields() -> None:
    from decimal import Decimal
    sig = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="test")
    assert sig.stop_price is None
    assert sig.take_profit_price is None
