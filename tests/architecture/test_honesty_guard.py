# Architecture + unit guard — HONESTY ("the system must never lie to the owner")
"""Phase 7: every number the dashboard shows must come from the real ledger
(TreasuryAgent), net of fees — never hardcoded, random, or faked. Two layers:

  1. static scan of production paths for fabricated-data patterns;
  2. unit reconciliation: reported equity/cash/PnL == the ledger, and the daily
     % is the REAL realized-net return, not the target.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import structlog

from domain.shared.money import quantize_price
from domain.trading.paper import ClosedTrade, ExitReason
from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime

SRC = Path(__file__).resolve().parents[2] / "src"


# ── 1. Static: no fabricated data in production paths ────────────────
def test_no_random_or_fabricated_numbers_in_production_js() -> None:
    """Dashboard JS must not synthesise equity/pnl/metrics. (simulateAgentMetrics
    survives only as an empty post-migration stub — a *fabricating* body is
    forbidden.)"""
    text = (SRC / "infrastructure/web/static/kingdom.html").read_text(encoding="utf-8")
    forbidden = (
        "Math.random()",                       # no random data anywhere
        "startDemoSimulator",                  # no demo simulator
        "function simulateAgentMetrics() {\n  const",  # no fabricating body
    )
    offenders = [p for p in forbidden if p in text]
    assert not offenders, f"fabricated-data pattern in dashboard: {offenders}"


def test_status_metrics_are_not_hardcoded_in_runtime() -> None:
    """The runtime status builder must derive money metrics from the treasury,
    not from literals. Guard against a fixed equity/pnl sneaking back in."""
    status_src = (SRC / "orchestration/runtime_status.py").read_text(encoding="utf-8")
    # equity/cash/pnl must reference the treasury ledger / trader, never a constant.
    assert "self._treasury" in status_src
    assert "realized_today" in status_src
    # no suspicious hardcoded balances (the old fake was 1284567.89)
    assert not re.search(r"\b1284567\.89\b", status_src)


# ── 2. Unit: reported numbers reconcile with the ledger ──────────────
def _runtime(capital: str = "1000") -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, initial_capital=capital),
        logger=structlog.get_logger("t"),
    )
    rt.agents = rt._make_agents()
    return rt


def test_status_equity_cash_reconcile_with_treasury_ledger() -> None:
    rt = _runtime("1000")
    assert rt._treasury is not None
    s = rt.status()
    # Exact reconcile channel: *_str carries the full-precision Decimal verbatim.
    assert Decimal(str(s["cash_str"])) == rt._treasury.cash == Decimal("1000")
    assert Decimal(str(s["equity_str"])) == rt._treasury.cash  # no open position yet
    # Display channel: numeric fields are satang-quantized (2dp), still numeric.
    assert Decimal(str(s["cash"])) == rt._treasury.cash == Decimal("1000")
    assert Decimal(str(s["equity"])) == rt._treasury.cash
    assert s["initial_capital"] == "1000"


def test_pnl_today_equals_realized_net_from_ledger() -> None:
    rt = _runtime("1000")
    assert rt._treasury is not None
    # Settle a REAL closed trade through the ledger (pnl is net of both fees).
    trade = ClosedTrade(
        symbol="thb_btc", qty=Decimal("0.001"),
        entry_price=Decimal("1000000"), exit_price=Decimal("1010000"),
        entry_fee=Decimal("2.5"), exit_fee=Decimal("2.5"),
        pnl=Decimal("5"),  # net result the treasury will book
        reason=ExitReason.TAKE_PROFIT, opened_ms=0, closed_ms=1,
    )
    rt._treasury.settle_close(trade)
    s = rt.status()
    # pnl_today on the dashboard must equal the ledger's realized_today (net) +
    # unrealized (0 here) — never a fabricated or target value.
    assert Decimal(str(s["pnl_today"])) == rt._treasury.realized_today == Decimal("5")
    assert Decimal(str(s["realized_today"])) == Decimal("5")


def test_daily_pct_shows_real_loss_not_target() -> None:
    """A losing day must show the real negative %, not the 5% target."""
    rt = _runtime("1000")
    assert rt._treasury is not None
    losing = ClosedTrade(
        symbol="thb_btc", qty=Decimal("0.001"),
        entry_price=Decimal("1000000"), exit_price=Decimal("980000"),
        entry_fee=Decimal("2.5"), exit_fee=Decimal("2.5"),
        pnl=Decimal("-25"), reason=ExitReason.STOP_LOSS, opened_ms=0, closed_ms=1,
    )
    rt._treasury.settle_close(losing)
    daily = rt.status()["daily"]
    assert isinstance(daily, dict)
    # realized -25 on 1000 capital = -2.5%; target is 5 — must report the real -2.5.
    assert Decimal(str(daily["profit_pct_today"])) == Decimal("-2.5")
    assert Decimal(str(daily["target_profit_pct"])) == Decimal("5")
    assert daily["target_reached"] is False


def test_fees_are_deducted_on_both_legs() -> None:
    """close_position must net BOTH the entry and exit fee (target is net)."""
    from domain.trading.paper import close_position, open_position

    pos = open_position(
        "thb_btc", Decimal("0.01"), Decimal("1000000"),
        stop_pct=Decimal("1"), take_profit_pct=Decimal("2"),
        fee_bps=Decimal("25"), slippage_bps=Decimal("0"), now_ms=0,
    )
    trade = close_position(pos, Decimal("1000000"), ExitReason.MANUAL,
                           fee_bps=Decimal("25"), slippage_bps=Decimal("0"), now_ms=1)
    gross = (trade.exit_price - trade.entry_price) * trade.qty
    assert trade.pnl == gross - trade.entry_fee - trade.exit_fee
    assert trade.entry_fee > 0 and trade.exit_fee > 0  # both legs charged


def test_money_serialization_is_exact_and_satang_quantized() -> None:
    """S3 regression: the dashboard must not lie *or* leak float noise.

    *_str carries the FULL-precision Decimal verbatim (exact reconcile channel);
    the numeric field is cleanly satang-quantized (2dp) for display, with no
    sub-satang float tail. Constructed with a deliberately non-round ledger cash
    so the assertions are non-vacuous.
    """
    rt = _runtime("1000")
    assert rt._treasury is not None
    # proceeds = qty*exit_price - exit_fee = 1234.567 - 0.123456789 -> long decimal
    trade = ClosedTrade(
        symbol="thb_btc", qty=Decimal("0.001"),
        entry_price=Decimal("1000000"), exit_price=Decimal("1234567"),
        entry_fee=Decimal("0"), exit_fee=Decimal("0.123456789"),
        pnl=Decimal("234.443543211"),
        reason=ExitReason.TAKE_PROFIT, opened_ms=0, closed_ms=1,
    )
    rt._treasury.settle_close(trade)
    ledger_cash = rt._treasury.cash
    # guard: ledger cash is genuinely non-round (otherwise this test proves nothing)
    assert ledger_cash != ledger_cash.quantize(Decimal("0.01"))

    s = rt.status()
    # 1) exact channel — full precision, zero loss vs the ledger
    assert Decimal(str(s["cash_str"])) == ledger_cash
    assert Decimal(str(s["equity_str"])) == ledger_cash  # no open position
    # 2) display channel — satang-quantized, clean, still numeric (no float tail)
    assert Decimal(str(s["cash"])) == quantize_price(ledger_cash)
    assert Decimal(str(s["equity"])) == quantize_price(ledger_cash)
