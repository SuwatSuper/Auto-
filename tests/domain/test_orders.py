# Layer 1 — Domain (tests/domain/test_orders)
"""Tests for Order state machine transitions."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.trading.orders import (
    IllegalOrderTransition,
    Order,
    OrderStatus,
    Side,
    transition,
)


def _make_order(status: OrderStatus = OrderStatus.NEW) -> Order:
    return Order(
        order_id="test-order-001",
        symbol="THB_BTC",
        side=Side.BUY,
        qty=Decimal("0.01"),
        limit_price=None,
        status=status,
        created_ms=1_700_000_000_000,
    )


# --- Legal transitions ---

def test_new_to_approved() -> None:
    o = _make_order(OrderStatus.NEW)
    result = transition(o, OrderStatus.APPROVED)
    assert result.status == OrderStatus.APPROVED
    assert result.version == 2


def test_new_to_rejected() -> None:
    o = _make_order(OrderStatus.NEW)
    result = transition(o, OrderStatus.REJECTED)
    assert result.status == OrderStatus.REJECTED


def test_new_to_cancelled() -> None:
    o = _make_order(OrderStatus.NEW)
    result = transition(o, OrderStatus.CANCELLED)
    assert result.status == OrderStatus.CANCELLED


def test_approved_to_filled() -> None:
    o = transition(_make_order(), OrderStatus.APPROVED)
    result = transition(o, OrderStatus.FILLED)
    assert result.status == OrderStatus.FILLED


def test_approved_to_cancelled() -> None:
    o = transition(_make_order(), OrderStatus.APPROVED)
    result = transition(o, OrderStatus.CANCELLED)
    assert result.status == OrderStatus.CANCELLED


# --- Illegal transitions ---

def test_new_to_filled_raises() -> None:
    with pytest.raises(IllegalOrderTransition):
        transition(_make_order(), OrderStatus.FILLED)


def test_rejected_to_anything_raises() -> None:
    o = transition(_make_order(), OrderStatus.REJECTED)
    for status in OrderStatus:
        with pytest.raises(IllegalOrderTransition):
            transition(o, status)


def test_filled_to_anything_raises() -> None:
    o = transition(transition(_make_order(), OrderStatus.APPROVED), OrderStatus.FILLED)
    for status in OrderStatus:
        with pytest.raises(IllegalOrderTransition):
            transition(o, status)


def test_cancelled_to_anything_raises() -> None:
    o = transition(_make_order(), OrderStatus.CANCELLED)
    for status in OrderStatus:
        with pytest.raises(IllegalOrderTransition):
            transition(o, status)


def test_approved_to_rejected_raises() -> None:
    o = transition(_make_order(), OrderStatus.APPROVED)
    with pytest.raises(IllegalOrderTransition):
        transition(o, OrderStatus.REJECTED)


def test_version_increments_on_transition() -> None:
    o = _make_order()
    assert o.version == 1
    o2 = transition(o, OrderStatus.APPROVED)
    assert o2.version == 2
    o3 = transition(o2, OrderStatus.FILLED)
    assert o3.version == 3
