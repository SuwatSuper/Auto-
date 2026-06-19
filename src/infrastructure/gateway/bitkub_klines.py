# Layer 3 — Infrastructure (gateway/bitkub_klines)
"""Bitkub OHLC (klines) fetcher + offline CSV loader for backtests.

Read-only TradingView UDF history endpoint (PUBLIC, UNSIGNED — no API key, never
an order path):

    GET {base}/tradingview/history?symbol=BTC_THB&resolution=15&from=<s>&to=<s>

UDF response shape::

    {"s": "ok", "t": [...], "o": [...], "h": [...], "l": [...], "c": [...], "v": [...]}

``parse_udf_ohlc`` is the pure parser (fully unit-tested); ``fetch_klines`` is
the thin HTTP shell around it; ``load_csv`` / ``write_csv`` let the same backtest
run fully offline. Network/HTTP errors propagate to the caller — no silent retry.
"""
from __future__ import annotations

import csv
import time
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

_DEFAULT_BASE = "https://api.bitkub.com"
_TIMEOUT = 15.0
_MS_THRESHOLD = 1_000_000_000_000  # epoch values >= this are already milliseconds

# Human resolution -> seconds per bar.
RESOLUTION_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}

# Human resolution -> Bitkub UDF resolution token.
_UDF_RESOLUTION: dict[str, str] = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "1D",
    "1w": "1W",
}

_CSV_FIELDS = ("ts_ms", "open", "high", "low", "close", "volume")


class OhlcBar(BaseModel, frozen=True):
    """A single OHLC candle. Timestamp in epoch milliseconds, prices as Decimal."""

    ts_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def _dec(value: Any) -> Decimal:
    """Coerce a JSON/CSV scalar to Decimal via its string form (no float noise)."""
    return Decimal(str(value))


def resolution_seconds(resolution: str) -> int:
    """Seconds per bar for a human resolution (e.g. ``"15m"`` -> 900)."""
    try:
        return RESOLUTION_SECONDS[resolution]
    except KeyError:
        raise ValueError(
            f"unsupported resolution {resolution!r}; choose from {sorted(RESOLUTION_SECONDS)}"
        ) from None


def udf_resolution(resolution: str) -> str:
    """Bitkub UDF resolution token for a human resolution (e.g. ``"1h"`` -> ``"60"``)."""
    try:
        return _UDF_RESOLUTION[resolution]
    except KeyError:
        raise ValueError(
            f"unsupported resolution {resolution!r}; choose from {sorted(_UDF_RESOLUTION)}"
        ) from None


def parse_udf_ohlc(payload: dict[str, Any]) -> list[OhlcBar]:
    """Parse a Bitkub UDF history payload into a list of OhlcBar (pure).

    ``s == "no_data"`` yields an empty list; any non-``"ok"`` status, a missing
    OHLC array, or a length mismatch raises ValueError.
    """
    status = payload.get("s")
    if status == "no_data":
        return []
    if status != "ok":
        raise ValueError(f"Bitkub UDF status {status!r}: {payload.get('errmsg') or payload}")

    try:
        t_arr = payload["t"]
        o_arr = payload["o"]
        h_arr = payload["h"]
        l_arr = payload["l"]
        c_arr = payload["c"]
    except KeyError as exc:
        raise ValueError(f"Bitkub UDF payload missing field {exc}") from exc

    v_arr = payload.get("v") or [0] * len(t_arr)
    lengths = {len(t_arr), len(o_arr), len(h_arr), len(l_arr), len(c_arr), len(v_arr)}
    if len(lengths) != 1:
        raise ValueError(
            "Bitkub UDF arrays length mismatch: "
            f"{[len(t_arr), len(o_arr), len(h_arr), len(l_arr), len(c_arr), len(v_arr)]}"
        )

    return [
        OhlcBar(
            ts_ms=int(t_arr[i]) * 1000,
            open=_dec(o_arr[i]),
            high=_dec(h_arr[i]),
            low=_dec(l_arr[i]),
            close=_dec(c_arr[i]),
            volume=_dec(v_arr[i]),
        )
        for i in range(len(t_arr))
    ]


def fetch_klines(
    symbol: str,
    resolution: str,
    *,
    bars: int,
    to_ts: int | None = None,
    base_url: str = _DEFAULT_BASE,
    client: httpx.Client | None = None,
) -> list[OhlcBar]:
    """Fetch up to ``bars`` recent OHLC bars from Bitkub's UDF history endpoint.

    ``to_ts`` (epoch seconds) defaults to now. The ``from`` bound is padded by
    20% so gaps/holidays still return enough rows; the result is trimmed to the
    last ``bars`` candles. A caller may inject an ``httpx.Client`` (used in tests
    via a mock transport); otherwise a short-lived client is created and closed.
    """
    res_secs = resolution_seconds(resolution)
    udf_res = udf_resolution(resolution)
    if to_ts is None:
        to_ts = int(time.time())
    span = int(res_secs * bars * 1.2) + res_secs
    params: dict[str, str | int] = {
        "symbol": symbol,
        "resolution": udf_res,
        "from": to_ts - span,
        "to": to_ts,
    }
    url = f"{base_url.rstrip('/')}/tradingview/history"

    owns_client = client is None
    active = client if client is not None else httpx.Client(timeout=_TIMEOUT)
    try:
        resp = active.get(url, params=params)
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
    finally:
        if owns_client:
            active.close()

    parsed = parse_udf_ohlc(payload)
    return parsed[-bars:] if bars > 0 else parsed


def write_csv(bars: Iterable[OhlcBar], path: str | Path) -> None:
    """Write OHLC bars to a CSV with a header row (round-trips with load_csv)."""
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(_CSV_FIELDS)
        for bar in bars:
            writer.writerow([bar.ts_ms, bar.open, bar.high, bar.low, bar.close, bar.volume])


def load_csv(path: str | Path) -> list[OhlcBar]:
    """Load OHLC bars from a CSV with a header row.

    Recognised timestamp columns (case-insensitive): ts_ms / timestamp / time /
    ts / date — a value below 10^12 is treated as epoch SECONDS and scaled to ms.
    Required price columns: open / high / low / close; volume is optional.
    """
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        cols = {name.lower(): name for name in reader.fieldnames}
        ts_key = next(
            (cols[c] for c in ("ts_ms", "timestamp", "time", "ts", "date") if c in cols),
            None,
        )
        missing = [c for c in ("open", "high", "low", "close") if c not in cols]
        if ts_key is None or missing:
            raise ValueError(
                f"CSV must have a timestamp and open/high/low/close columns; got {reader.fieldnames}"
            )
        v_key = cols.get("volume")

        bars: list[OhlcBar] = []
        for row in reader:
            ts_raw = int(_dec(row[ts_key]))
            ts_ms = ts_raw if ts_raw >= _MS_THRESHOLD else ts_raw * 1000
            volume = _dec(row[v_key]) if v_key and row[v_key] != "" else Decimal(0)
            bars.append(
                OhlcBar(
                    ts_ms=ts_ms,
                    open=_dec(row[cols["open"]]),
                    high=_dec(row[cols["high"]]),
                    low=_dec(row[cols["low"]]),
                    close=_dec(row[cols["close"]]),
                    volume=volume,
                )
            )
        return bars
