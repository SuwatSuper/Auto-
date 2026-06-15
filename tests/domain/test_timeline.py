"""Timeline analysis — grade historical EMA-cross setups, summarize win rate."""
from __future__ import annotations

from decimal import Decimal

from domain.analytics.timeline import GradedSetup, ema_cross_setups, summarize
from domain.strategy.base import SignalAction

D = Decimal


def test_too_short_history_returns_no_setups() -> None:
    assert ema_cross_setups([D("100")] * 10) == []


def test_setups_are_graded_against_future_price() -> None:
    # oscillating series produces crossovers that can be graded
    import math
    prices = [D(str(round(1000 + math.sin(i / 5) * 50, 2))) for i in range(400)]
    setups = ema_cross_setups(prices, fast=5, slow=12, horizon=8)
    assert len(setups) > 0
    for s in setups:
        assert isinstance(s, GradedSetup)
        assert s.action in (SignalAction.BUY, SignalAction.SELL)
        assert isinstance(s.won, bool)


def test_summarize_splits_past_and_recent_and_computes_pwin() -> None:
    # craft 100 setups: first 50 all losses, last 50 all wins
    setups = (
        [GradedSetup(i, SignalAction.BUY, False, D("-0.01")) for i in range(50)]
        + [GradedSetup(i, SignalAction.BUY, True, D("0.01")) for i in range(50, 100)]
    )
    s = summarize(setups, past_n=50, recent_n=50)
    assert s["past_win_rate"] == "0.0000"
    assert s["recent_win_rate"] == "1.0000"
    assert s["p_win"] == "0.5000"   # 50 wins / 100
    assert s["sample"] == 100
    assert s["wins"] == 50 and s["losses"] == 50


def test_summarize_empty() -> None:
    s = summarize([])
    assert s["p_win"] is None and s["sample"] == 0
