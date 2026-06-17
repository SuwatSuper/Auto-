# Layer 3 — Infrastructure (tests/infrastructure/test_data_recording)
"""Phase 5: trade CSV carries fee/slippage/gross/net + provenance columns, and
data/daily_summary.csv is computed from the real ledger (net of fees)."""
from __future__ import annotations

import csv
from decimal import Decimal

import structlog

from domain.trading.paper import ClosedTrade, ExitReason
from infrastructure.config import Settings
from infrastructure.logging.daily_summary import build_summary_row, upsert_daily_summary
from infrastructure.logging.trade_csv import _FIELDS, TradeCsvLogger
from orchestration.runtime import PipelineRuntime


class _FakeBus:
    def subscribe(self, topic, maxsize=10_000):  # type: ignore[no-untyped-def]
        import asyncio
        return asyncio.Queue()

    def unsubscribe(self, topic, queue):  # type: ignore[no-untyped-def]
        pass

    async def publish(self, topic, key, value):  # type: ignore[no-untyped-def]
        pass


def test_trade_csv_has_phase5_columns(tmp_path) -> None:  # type: ignore[no-untyped-def]
    for col in ("fee_paid", "slippage_cost", "pnl_gross", "pnl_net",
                "strategy_id", "regime", "win_prob_est"):
        assert col in _FIELDS

    logger = TradeCsvLogger(bus=_FakeBus(), events_topic="x", log_dir=tmp_path)  # type: ignore[arg-type]
    logger._last_fill = {
        "qty": "0.001", "entry_price": "1000000", "symbol": "THB_BTC",
        "strategy_id": "trend_follower", "regime": "TREND_UP", "win_prob_est": "0.62",
    }
    logger._append({
        "ts_ms": 0, "exit": "1010000", "reason": "TAKE_PROFIT",
        "pnl": "5", "cash": "1005", "fee_paid": "5",
        "pnl_gross": "10", "pnl_net": "5", "slippage_bps": "5",
    })
    files = list(tmp_path.glob("trades_*.csv"))
    assert len(files) == 1
    row = next(csv.DictReader(files[0].open(encoding="utf-8")))
    assert row["fee_paid"] == "5" and row["pnl_gross"] == "10" and row["pnl_net"] == "5"
    assert row["strategy_id"] == "trend_follower" and row["regime"] == "TREND_UP"
    assert row["win_prob_est"] == "0.62"
    # slippage_cost = (qty*entry + qty*exit) * bps/10000
    expected = (Decimal("0.001") * Decimal("1000000") + Decimal("0.001") * Decimal("1010000")) \
        * Decimal("5") / Decimal("10000")
    assert Decimal(row["slippage_cost"]) == expected


def test_build_summary_row_math() -> None:
    row = build_summary_row(
        date="2026-06-15", start_equity=Decimal("1000"), end_equity=Decimal("1060"),
        pnl_net=Decimal("60"), fees_total=Decimal("5"), wins=3, losses=1,
        target_pct=Decimal("5"),
    )
    assert row["num_trades"] == 4
    assert row["win_rate"] == "75.00"
    assert row["pct_return_net"] == "6.0000"
    assert row["target_reached"] is True


def test_daily_summary_upsert_is_idempotent_by_date(tmp_path) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "daily_summary.csv"
    base = dict(start_equity=Decimal("1000"), end_equity=Decimal("1030"),
                fees_total=Decimal("2"), wins=1, losses=0, target_pct=Decimal("5"))
    upsert_daily_summary(p, build_summary_row(date="2026-06-15", pnl_net=Decimal("30"), **base))
    upsert_daily_summary(p, build_summary_row(date="2026-06-15", pnl_net=Decimal("60"), **base))
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    assert len(rows) == 1                 # same date replaced, not duplicated
    assert rows[0]["pnl_net"] == "60"


def test_runtime_daily_summary_reconciles_with_ledger(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, initial_capital="1000"),
        logger=structlog.get_logger("t"),
    )
    rt.agents = rt._make_agents()
    assert rt._treasury is not None
    for _ in range(2):
        rt._treasury.settle_close(ClosedTrade(
            symbol="thb_btc", qty=Decimal("0.001"),
            entry_price=Decimal("1000000"), exit_price=Decimal("1030000"),
            entry_fee=Decimal("2.5"), exit_fee=Decimal("2.5"), pnl=Decimal("30"),
            reason=ExitReason.TAKE_PROFIT, opened_ms=0, closed_ms=1,
        ))
    row = rt.write_daily_summary()
    # PROVENANCE: summary pnl_net + fees == the treasury ledger exactly.
    assert Decimal(str(row["pnl_net"])) == rt._treasury.realized_today == Decimal("60")
    assert Decimal(str(row["fees_total"])) == rt._treasury.fees_today == Decimal("10")
    assert row["wins"] == 2 and row["target_reached"] is True   # 60/1000 = 6% >= 5%
    assert (tmp_path / "data" / "daily_summary.csv").exists()
