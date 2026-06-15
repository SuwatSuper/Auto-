# Layer 1 — Domain (portfolio/models)
"""Portfolio domain models: Position, Trade, Account."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from domain.shared.money import Money


class Position(BaseModel, frozen=True):
    """Open position in a symbol. qty is signed (positive = long, negative = short)."""

    symbol: str
    qty: Decimal
    avg_entry_price: Decimal


class Trade(BaseModel, frozen=True):
    """Executed fill that changes portfolio state."""

    trade_id: str
    order_id: str
    symbol: str
    side: str
    qty: Decimal
    price: Decimal
    fee: Money
    ts_ms: int


class Account(BaseModel, frozen=True):
    """Account cash and realized PnL."""

    account_id: str
    cash: Money
    realized_pnl: Money
