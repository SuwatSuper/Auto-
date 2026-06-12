# Layer 1 — Domain (portfolio/engine)
"""Pure portfolio arithmetic functions — no floats, no I/O."""
from __future__ import annotations

from decimal import Decimal

from domain.portfolio.models import Account, Position, Trade
from domain.shared.money import Money


def apply_fill(
    account: Account,
    positions: dict[str, Position],
    trade: Trade,
) -> tuple[Account, dict[str, Position]]:
    """Apply a fill to the account and positions, returning updated state.

    Rules:
    - BUY increases position qty; weighted-average entry price on add-to-long.
    - SELL reduces position qty; computes realized PnL on reducing fills.
    - Position crosses zero (flip) when sell qty > current long qty.
    - Fee always deducted from cash.
    - Cost basis = qty * avg_entry_price (not cash spent).
    """
    symbol = trade.symbol
    side = trade.side.upper()
    qty = trade.qty
    price = trade.price
    currency = account.cash.currency

    current = positions.get(symbol, Position(symbol=symbol, qty=Decimal(0), avg_entry_price=Decimal(0)))
    old_qty = current.qty
    old_entry = current.avg_entry_price

    # --- Compute realized PnL and new position ---
    realized = Decimal(0)

    if side == "BUY":
        if old_qty >= 0:
            # Adding to long (or opening)
            total_qty = old_qty + qty
            if total_qty == 0:
                new_entry = Decimal(0)
            else:
                new_entry = (old_qty * old_entry + qty * price) / total_qty
            new_qty = total_qty
        else:
            # Covering short
            close_qty = min(qty, -old_qty)
            open_qty = qty - close_qty
            # PnL on covered portion (shorted at old_entry, covered at price)
            realized = close_qty * (old_entry - price)
            remaining_short = old_qty + close_qty  # still negative or zero
            if open_qty > 0:
                new_qty = open_qty
                new_entry = price
            else:
                new_qty = remaining_short
                new_entry = old_entry if remaining_short < 0 else Decimal(0)
    else:  # SELL
        if old_qty <= 0:
            # Adding to short (or opening short)
            total_qty = old_qty - qty
            if total_qty == 0:
                new_entry = Decimal(0)
            else:
                new_entry = ((-old_qty) * old_entry + qty * price) / (-total_qty)
            new_qty = total_qty
        else:
            # Reducing long
            close_qty = min(qty, old_qty)
            open_qty = qty - close_qty
            # PnL on closed portion
            realized = close_qty * (price - old_entry)
            remaining_long = old_qty - close_qty
            if open_qty > 0:
                # Flip to short
                new_qty = -open_qty
                new_entry = price
            else:
                new_qty = remaining_long
                new_entry = old_entry if remaining_long > 0 else Decimal(0)

    # Build updated position
    new_positions = dict(positions)
    if new_qty == 0:
        new_positions.pop(symbol, None)
    else:
        new_positions[symbol] = Position(
            symbol=symbol, qty=new_qty, avg_entry_price=new_entry
        )

    # Update account: deduct fee, add realized PnL
    new_cash = account.cash - trade.fee + Money(amount=realized, currency=currency)
    new_realized_pnl = account.realized_pnl + Money(amount=realized, currency=currency)

    new_account = Account(
        account_id=account.account_id,
        cash=new_cash,
        realized_pnl=new_realized_pnl,
    )
    return new_account, new_positions


def unrealized_pnl(position: Position, mark_price: Decimal) -> Money:
    """Compute unrealized PnL for a position at the given mark price.

    Long: (mark - entry) * qty
    Short: (entry - mark) * abs(qty)
    """
    if position.qty == 0:
        return Money(amount=Decimal(0), currency="THB")
    if position.qty > 0:
        pnl = (mark_price - position.avg_entry_price) * position.qty
    else:
        pnl = (position.avg_entry_price - mark_price) * (-position.qty)
    return Money(amount=pnl, currency="THB")


def equity(
    account: Account,
    positions: dict[str, Position],
    marks: dict[str, Decimal],
) -> Money:
    """Compute total equity: cash + sum of unrealized PnL for all positions."""
    total_upnl = Decimal(0)
    for symbol, pos in positions.items():
        mark = marks.get(symbol)
        if mark is not None:
            total_upnl += unrealized_pnl(pos, mark).amount
    return Money(amount=account.cash.amount + total_upnl, currency=account.cash.currency)
