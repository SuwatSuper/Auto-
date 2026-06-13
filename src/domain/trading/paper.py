# Layer 1 — Domain (trading/paper)
"""Pure paper-trading engine: sizing, brackets, fills. No I/O, Decimal only.

Honesty rules honored here:
- H1: a position cannot exist without stop-loss AND take-profit (validated at model level).
- Fees + slippage are applied on BOTH sides of every fill (backtest fidelity).
- LONG only. There is no code path that sends a real order anywhere.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from pydantic import BaseModel, model_validator

_QTY_STEP = Decimal("0.00000001")  # 8 dp, Bitkub-style
_HUNDRED = Decimal("100")


class ExitReason(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    OPPOSITE_SIGNAL = "OPPOSITE_SIGNAL"
    EMERGENCY = "EMERGENCY"
    MANUAL = "MANUAL"


class PaperPosition(BaseModel, frozen=True):
    """Open long position with a mandatory bracket (H1)."""

    symbol: str
    qty: Decimal
    entry_price: Decimal
    stop_price: Decimal
    take_profit_price: Decimal
    entry_fee: Decimal
    opened_ms: int

    @model_validator(mode="after")
    def _bracket_is_mandatory_and_sane(self) -> PaperPosition:
        if self.qty <= 0:
            raise ValueError("qty must be > 0")
        if self.entry_price <= 0:
            raise ValueError("entry_price must be > 0")
        if not self.stop_price < self.entry_price:
            raise ValueError("H1: stop_price must be below entry_price (long)")
        if not self.take_profit_price > self.entry_price:
            raise ValueError("H1: take_profit_price must be above entry_price (long)")
        return self

    def notional(self) -> Decimal:
        return self.qty * self.entry_price

    def market_value(self, mark_price: Decimal) -> Decimal:
        return self.qty * mark_price

    def unrealized_pnl(self, mark_price: Decimal) -> Decimal:
        return self.qty * (mark_price - self.entry_price)


class ClosedTrade(BaseModel, frozen=True):
    """Realized result of a closed paper position. PnL is net of both fees."""

    symbol: str
    qty: Decimal
    entry_price: Decimal
    exit_price: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    pnl: Decimal
    reason: ExitReason
    opened_ms: int
    closed_ms: int


def fee_for(notional: Decimal, fee_bps: Decimal) -> Decimal:
    """Taker fee on a notional amount (bps = basis points, 25 = 0.25%)."""
    return notional * fee_bps / Decimal("10000")


def slip_buy(price: Decimal, slippage_bps: Decimal) -> Decimal:
    """Effective fill price when buying (pay up by slippage)."""
    return price * (Decimal("1") + slippage_bps / Decimal("10000"))


def slip_sell(price: Decimal, slippage_bps: Decimal) -> Decimal:
    """Effective fill price when selling (give up slippage)."""
    return price * (Decimal("1") - slippage_bps / Decimal("10000"))


def size_order(
    cash: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    risk_per_trade_pct: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
) -> Decimal:
    """Risk-based position size, capped so the order is affordable with cash.

    qty_risk = (cash × risk%) / (entry − stop)
    Then cap so qty × fill_price + entry_fee ≤ 95% of cash (no leverage,
    5% buffer kept for the exit fee). Quantized DOWN to 8 dp.
    Returns 0 when sizing is impossible.
    """
    if cash <= 0 or entry_price <= 0:
        return Decimal("0")
    distance = entry_price - stop_price
    if distance <= 0:
        return Decimal("0")
    risk_amount = cash * risk_per_trade_pct / _HUNDRED
    qty = risk_amount / distance

    fill = slip_buy(entry_price, slippage_bps)
    cost_per_unit = fill * (Decimal("1") + fee_bps / Decimal("10000"))
    affordable = (cash * Decimal("0.95")) / cost_per_unit
    qty = min(qty, affordable)
    qty = qty.quantize(_QTY_STEP, rounding=ROUND_DOWN)
    return qty if qty > 0 else Decimal("0")


def open_position(
    symbol: str,
    qty: Decimal,
    signal_price: Decimal,
    stop_pct: Decimal,
    take_profit_pct: Decimal,
    fee_bps: Decimal,
    slippage_bps: Decimal,
    now_ms: int,
) -> PaperPosition:
    """Open a long with bracket attached atomically (H1). Entry includes slippage."""
    entry = slip_buy(signal_price, slippage_bps)
    stop = entry * (Decimal("1") - stop_pct / _HUNDRED)
    take = entry * (Decimal("1") + take_profit_pct / _HUNDRED)
    return PaperPosition(
        symbol=symbol,
        qty=qty,
        entry_price=entry,
        stop_price=stop,
        take_profit_price=take,
        entry_fee=fee_for(qty * entry, fee_bps),
        opened_ms=now_ms,
    )


def check_exit(position: PaperPosition, mark_price: Decimal) -> ExitReason | None:
    """Bracket check on every tick. Stop wins ties (conservative)."""
    if mark_price <= position.stop_price:
        return ExitReason.STOP_LOSS
    if mark_price >= position.take_profit_price:
        return ExitReason.TAKE_PROFIT
    return None


def close_position(
    position: PaperPosition,
    mark_price: Decimal,
    reason: ExitReason,
    fee_bps: Decimal,
    slippage_bps: Decimal,
    now_ms: int,
) -> ClosedTrade:
    """Close at mark with sell-side slippage; PnL net of BOTH fees (H2: losses real)."""
    exit_price = slip_sell(mark_price, slippage_bps)
    exit_fee = fee_for(position.qty * exit_price, fee_bps)
    gross = position.qty * (exit_price - position.entry_price)
    pnl = gross - position.entry_fee - exit_fee
    return ClosedTrade(
        symbol=position.symbol,
        qty=position.qty,
        entry_price=position.entry_price,
        exit_price=exit_price,
        entry_fee=position.entry_fee,
        exit_fee=exit_fee,
        pnl=pnl,
        reason=reason,
        opened_ms=position.opened_ms,
        closed_ms=now_ms,
    )
