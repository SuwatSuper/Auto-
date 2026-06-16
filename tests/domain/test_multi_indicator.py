# Tests — multi-indicator confluence entry signal
from __future__ import annotations

from decimal import Decimal

from domain.strategy.base import SignalAction
from domain.strategy.multi_indicator import multi_indicator_signal


def _series(start: int, step: int, n: int) -> list[Decimal]:
    return [Decimal(start) + Decimal(step) * Decimal(i) for i in range(n)]


def test_strong_uptrend_is_buy() -> None:
    res = multi_indicator_signal(_series(1_000_000, 1_000, 80))   # steadily rising
    assert res.action == SignalAction.BUY
    assert res.buy_votes >= 2 and res.buy_votes > res.sell_votes
    assert Decimal(0) < res.confidence <= Decimal(1)


def test_strong_downtrend_is_sell() -> None:
    res = multi_indicator_signal(_series(2_000_000, -1_000, 80))  # steadily falling
    assert res.action == SignalAction.SELL
    assert res.sell_votes >= 2 and res.sell_votes > res.buy_votes


def test_insufficient_history_holds_and_says_warming_up() -> None:
    res = multi_indicator_signal(_series(1_000_000, 100, 10))
    assert res.action == SignalAction.HOLD
    assert "อุ่นเครื่อง" in res.detail


def test_flat_market_holds_no_votes() -> None:
    res = multi_indicator_signal([Decimal(1_500_000)] * 80)
    assert res.action == SignalAction.HOLD
    assert res.buy_votes == 0 and res.sell_votes == 0


def test_confidence_is_agreeing_votes_over_total() -> None:
    res = multi_indicator_signal(_series(1_000_000, 1_000, 80))
    assert res.total == 4
    assert res.confidence == Decimal(res.buy_votes) / Decimal(res.total)


def test_min_votes_threshold_blocks_thin_agreement() -> None:
    # Requiring all 4 lines to agree: a monotonic rise pegs RSI overbought (no
    # vote), so only 3 lines agree -> below a min_votes=4 threshold -> HOLD.
    res = multi_indicator_signal(_series(1_000_000, 1_000, 80), min_votes=4)
    assert res.action == SignalAction.HOLD
    assert res.buy_votes == 3
