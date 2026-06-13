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
)


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
        ts_ms = int(event.get("ts_ms", time.time() * 1000))  # type: ignore[arg-type]
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
        date_str = dt.strftime("%Y%m%d")

        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"trades_{date_str}.csv"
        write_header = not path.exists()

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
                }
            )
        self.trades_written += 1
        self._last_fill = {}
