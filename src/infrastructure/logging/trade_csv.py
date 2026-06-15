# Layer 3 — Infrastructure (logging/trade_csv)
"""TradeCsvLogger — writes closed paper trades to date-rotating CSV files.

Subscribes to the paper events topic and appends one row per CLOSE event.
Tracks the preceding FILL event to recover entry_price and qty.
CSV rotates daily: data/trades_YYYYMMDD.csv.
"""
from __future__ import annotations

import asyncio
import csv
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import orjson

from orchestration.ports.event_bus import EventBus

_FIELDS = (
    "ts_ms",
    "date_utc",
    "symbol",
    "qty",
    "entry_price",
    "exit_price",
    "reason",
    "pnl",
    "cash",
    # Phase 5 — fee/slippage breakdown + provenance (all from the real trade).
    "fee_paid",
    "slippage_cost",
    "pnl_gross",
    "pnl_net",
    "strategy_id",
    "regime",
    "win_prob_est",
)


def _dec(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


class TradeCsvLogger:
    """Appends CLOSE trade events from the paper trader to rotating CSV files.

    Listens to both FILL (to cache qty/entry_price) and CLOSE events.
    Files are written to `log_dir/trades_YYYYMMDD.csv` (UTC date).
    """

    def __init__(
        self,
        bus: EventBus,
        events_topic: str,
        log_dir: Path = Path("data"),
    ) -> None:
        self._bus = bus
        self._topic = events_topic
        self._dir = log_dir

        self.running: bool = False
        self.trades_written: int = 0
        self.last_beat_ms: int = 0

        # Cache last FILL to attach qty/entry_price to the subsequent CLOSE
        self._last_fill: dict[str, str] = {}

    async def start(self) -> None:
        """Subscribe to paper events and write CLOSE rows to CSV."""
        self.running = True
        queue = self._bus.subscribe(self._topic)
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                try:
                    event: dict[str, object] = orjson.loads(raw)
                except (ValueError, TypeError):
                    continue
                kind = event.get("type")
                if kind == "FILL":
                    self._last_fill = {
                        "qty": str(event.get("qty", "")),
                        "entry_price": str(event.get("entry", "")),
                        "symbol": str(event.get("symbol", "THB_BTC")),
                        "strategy_id": str(event.get("strategy_id", "")),
                        "regime": str(event.get("regime", "")),
                        "win_prob_est": str(event.get("win_prob_est", "")),
                    }
                elif kind == "CLOSE":
                    self._append(event)
        finally:
            self._bus.unsubscribe(self._topic, queue)

    async def stop(self) -> None:
        """Signal the logger loop to exit."""
        self.running = False

    def _append(self, event: dict[str, object]) -> None:
        """Write one row to the appropriate daily CSV file."""
        ts_raw = event.get("ts_ms")
        ts_ms = int(ts_raw) if isinstance(ts_raw, int | float) else int(time.time() * 1000)
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        date_str = dt.strftime("%Y%m%d")

        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"trades_{date_str}.csv"
        write_header = not path.exists()

        # Modeled slippage cost actually applied (both legs), from the real bps.
        qty = _dec(self._last_fill.get("qty", "0"))
        entry_p = _dec(self._last_fill.get("entry_price", "0"))
        exit_p = _dec(event.get("exit", "0"))
        sbps = _dec(event.get("slippage_bps", "0")) / Decimal("10000")
        slippage_cost = (qty * entry_p + qty * exit_p) * sbps

        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(
                {
                    "ts_ms": ts_ms,
                    "date_utc": date_str,
                    "symbol": self._last_fill.get("symbol", ""),
                    "qty": self._last_fill.get("qty", ""),
                    "entry_price": self._last_fill.get("entry_price", ""),
                    "exit_price": str(event.get("exit", "")),
                    "reason": str(event.get("reason", "")),
                    "pnl": str(event.get("pnl", "")),
                    "cash": str(event.get("cash", "")),
                    "fee_paid": str(event.get("fee_paid", "")),
                    "slippage_cost": str(slippage_cost),
                    "pnl_gross": str(event.get("pnl_gross", "")),
                    "pnl_net": str(event.get("pnl_net", event.get("pnl", ""))),
                    "strategy_id": self._last_fill.get("strategy_id", ""),
                    "regime": self._last_fill.get("regime", ""),
                    "win_prob_est": self._last_fill.get("win_prob_est", ""),
                }
            )
        self.trades_written += 1
        self._last_fill = {}
