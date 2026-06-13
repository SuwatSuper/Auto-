# Layer 1 — Domain (backtest/engine)
"""Event-driven backtester.

Decision at bar i uses prices[0..i] and fills at bar i+1's price.
No lookahead: the strategy never sees bar i+1 when deciding at bar i.
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel

from domain.analytics.indicators import expectancy, max_drawdown, win_rate
from domain.portfolio.engine import apply_fill
from domain.portfolio.engine import equity as calc_equity
from domain.portfolio.models import Account, Position, Trade
from domain.risk.rules import RiskDecision, RiskLimits, evaluate
from domain.shared.money import Money
from domain.strategy.base import Signal, SignalAction, Strategy, StrategyContext
from domain.trading.orders import Order, OrderStatus, Side


class FeeModel(BaseModel, frozen=True):
    """Taker-only fee model: taker_bps basis points on notional."""

    taker_bps: Decimal

    def fee_bps(self, *, is_taker: bool = True) -> Decimal:  # noqa: ARG002
        return self.taker_bps


class MakerTakerFeeModel(BaseModel, frozen=True):
    """Bitkub-realistic fee tiers: maker (limit) vs taker (market) fees.

    Bitkub standard: maker 0.15% (15 bps), taker 0.25% (25 bps).
    """

    maker_bps: Decimal
    taker_bps: Decimal

    def fee_bps(self, *, is_taker: bool = True) -> Decimal:
        return self.taker_bps if is_taker else self.maker_bps


class SlippageModel(BaseModel, frozen=True):
    """Slippage model: slip_bps basis points on fill price."""

    slip_bps: Decimal


class PartialFillModel(BaseModel, frozen=True):
    """Simple partial-fill model: fill_pct of each order (0-100)."""

    fill_pct: Decimal  # e.g. Decimal("70") = 70% fill

    @property
    def fraction(self) -> Decimal:
        return self.fill_pct / Decimal("100")


class BacktestReport(BaseModel, frozen=True):
    """Summary of a completed backtest run."""

    trades: tuple[Trade, ...]
    equity_curve: tuple[Decimal, ...]
    final_equity: Money
    max_drawdown: Decimal
    win_rate: Decimal
    expectancy: Decimal
    fees_paid: Money
    slippage_cost: Money
    bars: int


def run_backtest(
    prices: Sequence[tuple[int, Decimal]],
    strategy: Strategy,
    limits: RiskLimits,
    fees: FeeModel | MakerTakerFeeModel,
    slippage: SlippageModel,
    initial_cash: Money,
    order_qty: Decimal,
    partial_fill: PartialFillModel | None = None,
    is_taker: bool = True,
) -> BacktestReport:
    """Run event-driven backtest over a price series.

    prices: sequence of (ts_ms, price) tuples, one per bar.
    Decision at bar i uses prices[0..i] for context;
    fill executes at bar i+1's price (no lookahead).
    """
    account = Account(
        account_id="backtest",
        cash=initial_cash,
        realized_pnl=Money(amount=Decimal(0), currency=initial_cash.currency),
    )
    positions: dict[str, Position] = {}
    all_trades: list[Trade] = []
    equity_curve: list[Decimal] = [initial_cash.amount]
    total_fees = Decimal(0)
    total_slippage_cost = Decimal(0)
    peak_equity = initial_cash
    daily_pnl = Money(amount=Decimal(0), currency=initial_cash.currency)
    symbol = "THB_BTC"

    for i in range(len(prices) - 1):
        ts_ms, current_price = prices[i]
        next_ts_ms, next_price = prices[i + 1]

        # Build strategy context using prices up to and including bar i
        price_seq = tuple(p for _, p in prices[: i + 1])
        ctx = StrategyContext(prices=price_seq, position_qty=positions.get(symbol, Position(symbol=symbol, qty=Decimal(0), avg_entry_price=Decimal(0))).qty)
        signal: Signal = strategy.decide(ctx)

        if signal.action == SignalAction.HOLD:
            # Record equity at this bar
            marks = {symbol: current_price}
            eq = calc_equity(account, positions, marks)
            equity_curve.append(eq.amount)
            continue

        side = Side.BUY if signal.action == SignalAction.BUY else Side.SELL

        order = Order(
            order_id=f"bt-order-{i:06d}",
            symbol=symbol,
            side=side,
            qty=order_qty,
            limit_price=None,
            status=OrderStatus.NEW,
            created_ms=ts_ms,
        )

        current_marks = {symbol: current_price}
        current_equity = calc_equity(account, positions, current_marks)
        if current_equity > peak_equity:
            peak_equity = current_equity

        decision: RiskDecision = evaluate(
            order=order,
            account=account,
            positions=positions,
            limits=limits,
            daily_pnl=daily_pnl,
            peak_equity=peak_equity,
            current_equity=current_equity,
        )

        if not decision.approved:
            marks = {symbol: current_price}
            eq = calc_equity(account, positions, marks)
            equity_curve.append(eq.amount)
            continue

        # Fill at next bar price with slippage (no lookahead)
        if side == Side.BUY:
            fill_price = next_price * (Decimal(1) + slippage.slip_bps / Decimal(10000))
        else:
            fill_price = next_price * (Decimal(1) - slippage.slip_bps / Decimal(10000))

        # Apply partial fill fraction (default: full fill)
        actual_qty = order_qty
        if partial_fill is not None:
            actual_qty = (order_qty * partial_fill.fraction).quantize(Decimal("0.00000001"))
        if actual_qty <= 0:
            marks = {symbol: current_price}
            eq = calc_equity(account, positions, marks)
            equity_curve.append(eq.amount)
            continue

        fee_bps = fees.fee_bps(is_taker=is_taker)
        notional = fill_price * actual_qty
        fee_amount = notional * fee_bps / Decimal(10000)
        fee = Money(amount=fee_amount.quantize(Decimal("0.01")), currency=initial_cash.currency)

        # Slippage cost = difference from fill_price vs next_price
        raw_slippage = abs(fill_price - next_price) * actual_qty
        total_slippage_cost += raw_slippage

        trade = Trade(
            trade_id=f"bt-trade-{i:06d}",
            order_id=order.order_id,
            symbol=symbol,
            side=side,
            qty=actual_qty,
            price=fill_price,
            fee=fee,
            ts_ms=next_ts_ms,
        )

        account, positions = apply_fill(account, positions, trade)
        all_trades.append(trade)
        total_fees += fee_amount

        marks = {symbol: next_price}
        eq = calc_equity(account, positions, marks)
        equity_curve.append(eq.amount)

        daily_pnl = account.realized_pnl

    # Final equity at last bar
    if prices:
        _, last_price = prices[-1]
        marks = {symbol: last_price}
        final_eq = calc_equity(account, positions, marks)
    else:
        final_eq = initial_cash

    # Compute per-trade PnL from equity changes (for win_rate / expectancy)
    trade_pnls_real: list[Decimal] = []
    if len(equity_curve) >= 2:
        prev = equity_curve[0]
        for val in equity_curve[1:]:
            trade_pnls_real.append(val - prev)
            prev = val

    wr = win_rate([p for p in trade_pnls_real if p != 0] or [Decimal(0)])
    exp = expectancy([p for p in trade_pnls_real if p != 0] or [Decimal(0)])
    md = max_drawdown(equity_curve)

    return BacktestReport(
        trades=tuple(all_trades),
        equity_curve=tuple(equity_curve),
        final_equity=final_eq,
        max_drawdown=md,
        win_rate=wr,
        expectancy=exp,
        fees_paid=Money(amount=total_fees, currency=initial_cash.currency),
        slippage_cost=Money(amount=total_slippage_cost, currency=initial_cash.currency),
        bars=len(prices),
    )
