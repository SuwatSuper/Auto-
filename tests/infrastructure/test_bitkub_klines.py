# Layer 3 — Infrastructure (tests/infrastructure/test_bitkub_klines)
"""Unit tests for the Bitkub klines parser, CSV loader, and HTTP shell."""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from infrastructure.gateway.bitkub_klines import (
    OhlcBar,
    fetch_klines,
    load_csv,
    parse_udf_ohlc,
    resolution_seconds,
    udf_resolution,
    write_csv,
)


def test_parse_udf_ohlc_parses_ok_payload() -> None:
    """A well-formed UDF payload parses to OhlcBars with ms timestamps + Decimals."""
    payload = {
        "s": "ok",
        "t": [1700000000, 1700000900],
        "o": ["100", "101"],
        "h": ["102", "103"],
        "l": ["99", "100"],
        "c": ["101", "102"],
        "v": ["10", "20"],
    }
    bars = parse_udf_ohlc(payload)
    assert len(bars) == 2
    assert bars[0].ts_ms == 1700000000 * 1000
    assert bars[0].open == Decimal("100")
    assert bars[1].close == Decimal("102")
    assert bars[1].volume == Decimal("20")


def test_parse_udf_ohlc_no_data_returns_empty() -> None:
    assert parse_udf_ohlc({"s": "no_data"}) == []


def test_parse_udf_ohlc_rejects_bad_payloads() -> None:
    """Non-ok status, a missing OHLC array, and a length mismatch all raise."""
    with pytest.raises(ValueError, match="status"):
        parse_udf_ohlc({"s": "error", "errmsg": "boom"})
    with pytest.raises(ValueError, match="missing field"):
        parse_udf_ohlc({"s": "ok", "t": [1], "o": [1]})  # h/l/c absent
    with pytest.raises(ValueError, match="length mismatch"):
        parse_udf_ohlc({"s": "ok", "t": [1, 2], "o": [1], "h": [1], "l": [1], "c": [1]})


def test_resolution_helpers_map_and_reject() -> None:
    assert resolution_seconds("5m") == 300
    assert resolution_seconds("15m") == 900
    assert resolution_seconds("1h") == 3600
    assert udf_resolution("15m") == "15"
    assert udf_resolution("1h") == "60"
    assert udf_resolution("1d") == "1D"
    with pytest.raises(ValueError, match="unsupported resolution"):
        resolution_seconds("7m")
    with pytest.raises(ValueError, match="unsupported resolution"):
        udf_resolution("7m")


def test_load_csv_round_trip_and_validation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """write_csv → load_csv round-trips; seconds timestamps scale; bad CSV raises."""
    bars = [
        OhlcBar(
            ts_ms=1700000000000,
            open=Decimal("100"), high=Decimal("102"), low=Decimal("99"),
            close=Decimal("101"), volume=Decimal("10"),
        ),
        OhlcBar(
            ts_ms=1700000900000,
            open=Decimal("101"), high=Decimal("103"), low=Decimal("100"),
            close=Decimal("102"), volume=Decimal("20"),
        ),
    ]
    p = tmp_path / "candles.csv"
    write_csv(bars, p)
    assert load_csv(p) == bars

    # A CSV with an epoch-SECONDS column is scaled to milliseconds.
    secs = tmp_path / "secs.csv"
    secs.write_text("time,open,high,low,close\n1700000000,1,2,0.5,1.5\n", encoding="utf-8")
    loaded = load_csv(secs)
    assert loaded[0].ts_ms == 1700000000 * 1000
    assert loaded[0].volume == Decimal("0")  # no volume column → 0

    bad = tmp_path / "bad.csv"
    bad.write_text("time,open,high,low\n1,1,2,0.5\n", encoding="utf-8")  # close missing
    with pytest.raises(ValueError, match="open/high/low/close"):
        load_csv(bad)


def test_fetch_klines_trims_to_requested_bars() -> None:
    """fetch_klines hits /tradingview/history and returns the last N bars."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["resolution"] = request.url.params["resolution"]
        return httpx.Response(
            200,
            json={
                "s": "ok",
                "t": [1, 2, 3, 4, 5],
                "o": [1, 1, 1, 1, 1],
                "h": [2, 2, 2, 2, 2],
                "l": [1, 1, 1, 1, 1],
                "c": [1, 1, 1, 1, 1],
                "v": [9, 9, 9, 9, 9],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bars = fetch_klines("BTC_THB", "15m", bars=3, client=client)
    assert captured["path"] == "/tradingview/history"
    assert captured["resolution"] == "15"
    assert [b.ts_ms for b in bars] == [3000, 4000, 5000]  # last 3, scaled to ms
