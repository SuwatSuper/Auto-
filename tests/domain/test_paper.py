# Layer 1 — Domain (tests/domain/test_paper)
"""Hand-computed tests for the pure paper-trading engine."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.trading.paper import (
    ExitReason,
    PaperPosition,
    check_exit,
    close_position,
    fee_for,
    open_position,
    size_order,
    slip_buy,
    slip_sell,
)

D = Decimal


def test_fee_and_slippage_hand_math() -> None:
    # 25 bps fee on 1000 THB = 2.5 THB
    assert fee_for(D("1000"), D("25")) == D("2.5")
    # 5 bps slippage on 1,500,000: buy 1,500,750 / sell 1,499,250
    assert slip_buy(D("1500000"), D("5")) == D("1500750.0")
    assert slip_sell(D("1500000"), D("5")) == D("1499250.0")


def test_size_order_risk_based_hand_math() -> None:
    # cash 1000, risk 1% = 10 THB; entry 1,500,000 stop 1,485,000 (distance 15,000)
    # qty_risk = 10/15000 = 0.000666... ; affordability cap:
    # fill = 1,500,750; cost/unit = 1500750*1.0025 = 1,504,501.875
    # affordable = 950 / 1,504,501.875 = 0.000631438... → cap wins, floored 8dp
    qty = size_order(D("1000"), D("1500000"), D("1485000"), D("1"), D("25"), D("5"))
    assert qty == D("0.00063143")


def test_size_order_risk_smaller_than_cap() -> None:
    # wide stop (10%) → risk-based wins: 100000*1% / 150000 = 0.00666666 (floor 8dp)
    # affordability cap here is 0.0631... so the risk number is the binding one
    qty = size_order(D("100000"), D("1500000"), D("1350000"), D("1"), D("25"), D("5"))
    assert qty == D("0.00666666")


def test_size_order_zero_paths() -> None:
    assert size_order(D("0"), D("1500000"), D("1485000"), D("1"), D("25"), D("5")) == 0
    assert size_order(D("1000"), D("1500000"), D("1500000"), D("1"), D("25"), D("5")) == 0
    assert size_order(D("1000"), D("1500000"), D("1600000"), D("1"), D("25"), D("5")) == 0


def test_open_position_attaches_bracket_atomically() -> None:
    pos = open_position("THB_BTC", D("0.001"), D("1500000"), D("1"), D("1.5"), D("25"), D("5"), 111)
    # entry = 1,500,750; stop = entry*0.99 = 1,485,742.5; tp = entry*1.015 = 1,523,261.25
    assert pos.entry_price == D("1500750.0")
    assert pos.stop_price == D("1485742.50")
    assert pos.take_profit_price == D("1523261.250")
    # entry fee = 0.001*1500750*0.0025 = 3.7518750
    assert pos.entry_fee == D("3.75187500")
    assert pos.opened_ms == 111


def test_h1_position_without_stop_is_impossible() -> None:
    with pytest.raises(ValueError):
        PaperPosition(
            symbol="THB_BTC", qty=D("0.001"), entry_price=D("100"),
            stop_price=D("100"), take_profit_price=D("101"),
            entry_fee=D("0"), opened_ms=0,
        )
    with pytest.raises(ValueError):
        PaperPosition(
            symbol="THB_BTC", qty=D("0.001"), entry_price=D("100"),
            stop_price=D("99"), take_profit_price=D("100"),
            entry_fee=D("0"), opened_ms=0,
        )
    with pytest.raises(ValueError):
        PaperPosition(
            symbol="THB_BTC", qty=D("0"), entry_price=D("100"),
            stop_price=D("99"), take_profit_price=D("101"),
            entry_fee=D("0"), opened_ms=0,
        )


def _pos() -> PaperPosition:
    return PaperPosition(
        symbol="THB_BTC", qty=D("0.001"), entry_price=D("1500000"),
        stop_price=D("1485000"), take_profit_price=D("1522500"),
        entry_fee=D("3.75"), opened_ms=0,
    )


def test_check_exit_boundaries() -> None:
    p = _pos()
    assert check_exit(p, D("1485000.01")) is None
    assert check_exit(p, D("1485000")) == ExitReason.STOP_LOSS
    assert check_exit(p, D("1522499.99")) is None
    assert check_exit(p, D("1522500")) == ExitReason.TAKE_PROFIT


def test_close_position_pnl_net_of_both_fees() -> None:
    # close at mark 1,522,500 → exit (5bps sell slip) = 1,521,738.75
    # exit fee = 0.001*1521738.75*0.0025 = 3.8043468750...
    # gross = 0.001*(1521738.75-1500000) = 21.73875
    # pnl = 21.73875 - 3.75 - 3.80434687500 = 14.184403125
    t = close_position(_pos(), D("1522500"), ExitReason.TAKE_PROFIT, D("25"), D("5"), 999)
    assert t.exit_price == D("1521738.7500")
    assert t.exit_fee == D("3.804346875000")
    assert t.pnl == D("14.184403125000")
    assert t.reason == ExitReason.TAKE_PROFIT
    assert t.closed_ms == 999


def test_close_at_stop_realizes_the_loss_fully() -> None:
    # mark 1,485,000 → exit = 1,484,257.5 ; gross = -15.7425
    # exit fee = 0.001*1484257.5*0.0025 = 3.71064375
    # pnl = -15.7425 - 3.75 - 3.71064375 = -23.20314375 (loss counted in full — H2)
    t = close_position(_pos(), D("1485000"), ExitReason.STOP_LOSS, D("25"), D("5"), 1)
    assert t.pnl == D("-23.203143750000")


def test_unrealized_and_market_value() -> None:
    p = _pos()
    assert p.market_value(D("1510000")) == D("1510.000")
    assert p.unrealized_pnl(D("1510000")) == D("10.000")
