# Tests — expanded (9-line) multi-indicator confluence
from __future__ import annotations

from decimal import Decimal

from domain.strategy.base import SignalAction
from domain.strategy.multi_indicator import expanded_confluence_signal


def _series(start: int, step: int, n: int) -> list[Decimal]:
    return [Decimal(start) + Decimal(step) * Decimal(i) for i in range(n)]


def test_total_is_nine_lines() -> None:
    res = expanded_confluence_signal(_series(1_000_000, 1_000, 120))
    assert res.total == 9


def test_strong_uptrend_is_buy() -> None:
    res = expanded_confluence_signal(_series(1_000_000, 1_000, 120))
    assert res.action == SignalAction.BUY
    assert res.buy_votes >= 3 and res.buy_votes > res.sell_votes
    assert Decimal(0) < res.confidence <= Decimal(1)


def test_strong_downtrend_is_sell() -> None:
    res = expanded_confluence_signal(_series(3_000_000, -1_000, 120))
    assert res.action == SignalAction.SELL
    assert res.sell_votes >= 3 and res.sell_votes > res.buy_votes


def test_insufficient_history_holds_and_says_warming_up() -> None:
    res = expanded_confluence_signal(_series(1_000_000, 100, 20))
    assert res.action == SignalAction.HOLD
    assert "อุ่นเครื่อง" in res.detail


def test_flat_market_holds_with_no_directional_votes() -> None:
    res = expanded_confluence_signal([Decimal(1_500_000)] * 120)
    assert res.action == SignalAction.HOLD
    # A dead-flat tape leaves every line undecided.
    assert res.buy_votes == 0 and res.sell_votes == 0


def test_confidence_is_agreeing_votes_over_total() -> None:
    res = expanded_confluence_signal(_series(1_000_000, 1_000, 120))
    assert res.confidence == Decimal(res.buy_votes) / Decimal(9)


def test_choppy_incline_casts_rsi_mid_zone_buy_votes() -> None:
    # A climbing-but-noisy tape keeps RSI in the 50–70 mid-zone (not pegged
    # overbought), so the RSI and RSI-based-MA lines both vote BUY.
    prices = [
        Decimal(1_000_000) + Decimal(200) * Decimal(i) - (Decimal(600) if i % 2 == 0 else Decimal(0))
        for i in range(120)
    ]
    res = expanded_confluence_signal(prices)
    assert res.action == SignalAction.BUY
    assert "RSI↑" in res.detail and "RSIma↑" in res.detail


def test_choppy_decline_casts_rsi_mid_zone_sell_votes() -> None:
    # A draining-but-noisy tape keeps RSI in the 30–50 mid-zone (not pegged
    # oversold), so the RSI and RSI-based-MA lines both vote SELL.
    prices = [
        Decimal(2_000_000) - Decimal(200) * Decimal(i) + (Decimal(600) if i % 2 == 0 else Decimal(0))
        for i in range(120)
    ]
    res = expanded_confluence_signal(prices)
    assert res.action == SignalAction.SELL
    assert "RSI↓" in res.detail and "RSIma↓" in res.detail


def test_high_min_votes_can_block_thin_agreement() -> None:
    # Demanding all nine lines agree: a monotonic rise pegs RSI overbought (no
    # vote), so fewer than nine agree → HOLD.
    res = expanded_confluence_signal(_series(1_000_000, 1_000, 120), min_votes=9)
    assert res.action == SignalAction.HOLD
