# Layer 1 — Domain (trading/orders)
"""Order domain model and pure state machine transitions."""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel


class Side(StrEnum):
    """Order side: buy or sell."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    """Order lifecycle states."""

    NEW = "NEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


# Legal transitions: from_status → set of allowed to_statuses
_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.APPROVED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.APPROVED: {OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.REJECTED: set(),
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
}


class IllegalOrderTransition(ValueError):
    """Raised when an illegal order status transition is attempted."""


class Order(BaseModel, frozen=True):
    """Immutable order snapshot."""

    order_id: str
    symbol: str
    side: Side
    qty: Decimal
    limit_price: Decimal | None
    status: OrderStatus
    created_ms: int
    version: int = 1


def transition(order: Order, new_status: OrderStatus) -> Order:
    """Return a new Order with status advanced to new_status.

    Raises IllegalOrderTransition for illegal status changes.
    """
    allowed = _TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise IllegalOrderTransition(
            f"Cannot transition {order.status!r} → {new_status!r} "
            f"for order {order.order_id}"
        )
    return order.model_copy(update={"status": new_status, "version": order.version + 1})
