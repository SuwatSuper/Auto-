# Layer 3 — Infrastructure (logging/daily_summary)
"""Daily summary ledger — one row per day in data/daily_summary.csv.

Every field is derived from the real treasury ledger (net of fees). The row is
UPSERTED by date so an in-progress day is kept current without duplicating.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

SUMMARY_FIELDS = (
    "date",
    "start_equity",
    "end_equity",
    "pnl_net",
    "fees_total",
    "num_trades",
    "wins",
    "losses",
    "win_rate",
    "pct_return_net",
    "target_pct",
    "target_reached",
)


def build_summary_row(
    *,
    date: str,
    start_equity: Decimal,
    end_equity: Decimal,
    pnl_net: Decimal,
    fees_total: Decimal,
    wins: int,
    losses: int,
    target_pct: Decimal,
) -> dict[str, object]:
    """Compute a daily-summary row from real ledger values (net of fees)."""
    num_trades = wins + losses
    win_rate = (Decimal(wins) / Decimal(num_trades) * 100) if num_trades else Decimal("0")
    pct_return = (pnl_net / start_equity * 100) if start_equity > 0 else Decimal("0")
    return {
        "date": date,
        "start_equity": str(start_equity),
        "end_equity": str(end_equity),
        "pnl_net": str(pnl_net),
        "fees_total": str(fees_total),
        "num_trades": num_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": str(win_rate.quantize(Decimal("0.01"))),
        "pct_return_net": str(pct_return.quantize(Decimal("0.0001"))),
        "target_pct": str(target_pct),
        "target_reached": bool(target_pct > 0 and pct_return >= target_pct),
    }


def upsert_daily_summary(path: Path, row: dict[str, object]) -> None:
    """Insert or replace the row for ``row['date']`` in the daily-summary CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, object]] = {}
    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as fh:
            for existing in csv.DictReader(fh):
                rows[str(existing.get("date", ""))] = dict(existing)
    rows[str(row["date"])] = row
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for date in sorted(rows):
            writer.writerow({k: rows[date].get(k, "") for k in SUMMARY_FIELDS})
