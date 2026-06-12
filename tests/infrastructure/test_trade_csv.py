# tests/infrastructure/test_trade_csv.py
"""Tests for TradeCsvLogger — no real files unless using tmp_path."""
from __future__ import annotations

import asyncio
import contextlib
import csv
import time
from pathlib import Path

import orjson
import pytest

from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.logging.trade_csv import TradeCsvLogger


def _make_fill(qty: str = "0.001", entry: str = "50000") -> bytes:
    return orjson.dumps(
        {
            "type": "FILL",
            "ts_ms": int(time.time() * 1000),
            "qty": qty,
            "entry": entry,
            "stop": "49000",
            "take_profit": "52000",
            "symbol": "THB_BTC",
        }
    )


def _make_close(pnl: str = "15.50", exit_price: str = "51000", reason: str = "TAKE_PROFIT") -> bytes:
    return orjson.dumps(
        {
            "type": "CLOSE",
            "ts_ms": int(time.time() * 1000),
            "reason": reason,
            "pnl": pnl,
            "exit": exit_price,
            "cash": "1015.50",
        }
    )


async def _run_logger(
    logger: TradeCsvLogger,
    publish_fn: asyncio.coroutines.CoroutineType | None = None,
    settle: float = 0.2,
) -> None:
    """Start logger, publish events, wait, stop."""
    task = asyncio.create_task(logger.start())
    await asyncio.sleep(0.05)
    try:
        if publish_fn is not None:
            await publish_fn
        await asyncio.sleep(settle)
    finally:
        await logger.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_close_event_writes_csv_row(tmp_path: Path) -> None:
    """A FILL followed by CLOSE writes one CSV row."""
    bus = InMemoryEventBus()
    topic = "paper.events.v1"
    logger = TradeCsvLogger(bus, topic, log_dir=tmp_path)

    async def _pub() -> None:
        await bus.publish(topic, b"p", _make_fill())
        await bus.publish(topic, b"p", _make_close())

    await _run_logger(logger, _pub())

    csv_files = list(tmp_path.glob("trades_*.csv"))
    assert len(csv_files) == 1
    rows = list(csv.DictReader(csv_files[0].open(encoding="utf-8")))
    assert len(rows) == 1
    row = rows[0]
    assert row["qty"] == "0.001"
    assert row["entry_price"] == "50000"
    assert row["exit_price"] == "51000"
    assert row["reason"] == "TAKE_PROFIT"
    assert row["pnl"] == "15.50"
    assert row["cash"] == "1015.50"


@pytest.mark.asyncio
async def test_multiple_trades_append_rows(tmp_path: Path) -> None:
    """Two FILL+CLOSE pairs produce two rows in the same file."""
    bus = InMemoryEventBus()
    topic = "paper.events.v1"
    logger = TradeCsvLogger(bus, topic, log_dir=tmp_path)

    async def _pub() -> None:
        await bus.publish(topic, b"p", _make_fill("0.001", "50000"))
        await bus.publish(topic, b"p", _make_close("15.50", "51000", "TAKE_PROFIT"))
        await bus.publish(topic, b"p", _make_fill("0.002", "48000"))
        await bus.publish(topic, b"p", _make_close("-10.00", "47000", "STOP"))

    await _run_logger(logger, _pub())

    csv_files = list(tmp_path.glob("trades_*.csv"))
    rows = list(csv.DictReader(csv_files[0].open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["reason"] == "TAKE_PROFIT"
    assert rows[1]["reason"] == "STOP"


@pytest.mark.asyncio
async def test_close_without_fill_writes_empty_entry(tmp_path: Path) -> None:
    """A CLOSE event without a preceding FILL writes empty qty/entry_price."""
    bus = InMemoryEventBus()
    topic = "paper.events.v1"
    logger = TradeCsvLogger(bus, topic, log_dir=tmp_path)

    await _run_logger(logger, bus.publish(topic, b"p", _make_close()))

    csv_files = list(tmp_path.glob("trades_*.csv"))
    assert len(csv_files) == 1
    rows = list(csv.DictReader(csv_files[0].open(encoding="utf-8")))
    assert rows[0]["qty"] == ""
    assert rows[0]["entry_price"] == ""


@pytest.mark.asyncio
async def test_non_close_events_ignored(tmp_path: Path) -> None:
    """Events that are not CLOSE produce no CSV rows."""
    bus = InMemoryEventBus()
    topic = "paper.events.v1"
    logger = TradeCsvLogger(bus, topic, log_dir=tmp_path)

    other = orjson.dumps({"type": "FILL", "qty": "0.1", "entry": "50000"})
    await _run_logger(logger, bus.publish(topic, b"p", other))

    csv_files = list(tmp_path.glob("trades_*.csv"))
    assert len(csv_files) == 0


@pytest.mark.asyncio
async def test_csv_header_written_once(tmp_path: Path) -> None:
    """CSV header is only written once even with multiple rows."""
    bus = InMemoryEventBus()
    topic = "paper.events.v1"
    logger = TradeCsvLogger(bus, topic, log_dir=tmp_path)

    async def _pub() -> None:
        for _ in range(3):
            await bus.publish(topic, b"p", _make_fill())
            await bus.publish(topic, b"p", _make_close())

    await _run_logger(logger, _pub())

    csv_files = list(tmp_path.glob("trades_*.csv"))
    content = csv_files[0].read_text(encoding="utf-8")
    # Count header lines (lines containing 'ts_ms')
    header_lines = [l for l in content.splitlines() if "ts_ms" in l]
    assert len(header_lines) == 1


@pytest.mark.asyncio
async def test_trades_written_counter(tmp_path: Path) -> None:
    """trades_written increments for each CLOSE event written."""
    bus = InMemoryEventBus()
    topic = "paper.events.v1"
    logger = TradeCsvLogger(bus, topic, log_dir=tmp_path)

    async def _pub() -> None:
        for _ in range(4):
            await bus.publish(topic, b"p", _make_fill())
            await bus.publish(topic, b"p", _make_close())

    await _run_logger(logger, _pub())
    assert logger.trades_written == 4


@pytest.mark.asyncio
async def test_bad_json_ignored(tmp_path: Path) -> None:
    """Invalid JSON frames are silently skipped."""
    bus = InMemoryEventBus()
    topic = "paper.events.v1"
    logger = TradeCsvLogger(bus, topic, log_dir=tmp_path)

    async def _pub() -> None:
        await bus.publish(topic, b"p", b"not-json{{{")
        await bus.publish(topic, b"p", _make_fill())
        await bus.publish(topic, b"p", _make_close())

    await _run_logger(logger, _pub())
    assert logger.trades_written == 1
