# Layer 3 — Infrastructure (gateway/coinmetrics)
"""Fetch REAL long-history daily BTC prices from the public Coin Metrics dataset.

Coin Metrics community data (github.com/coinmetrics/data) publishes a daily
reference rate (``PriceUSD``) for BTC going back to 2010 — the longest honest,
free, public history available. Read-only, unsigned, never an order path.

``parse_coinmetrics_csv`` is the pure parser. Coin Metrics has no intraday OHLC,
so each day becomes a close-only bar (open = high = low = close = the reference
price); that is correct for daily close-to-close backtests and bracket checks.
"""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from infrastructure.gateway.bitkub_klines import OhlcBar

BTC_CSV_URL = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv"
_TIMEOUT = 90.0


def _date_to_ms(day: str) -> int:
    """'YYYY-MM-DD' → epoch milliseconds (UTC midnight)."""
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp()) * 1000


def parse_coinmetrics_csv(text: str, *, price_col: str = "PriceUSD") -> list[OhlcBar]:
    """Parse a Coin Metrics CSV into daily close-only OhlcBars (pure).

    Rows with no price (early pre-market days) are skipped. Missing ``time`` or
    ``price_col`` columns raise ValueError.
    """
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "time" not in reader.fieldnames or price_col not in reader.fieldnames:
        raise ValueError(f"Coin Metrics CSV must have 'time' and {price_col!r}; got {reader.fieldnames}")
    bars: list[OhlcBar] = []
    for row in reader:
        raw = row.get(price_col) or ""
        day = row.get("time") or ""
        if not raw or not day:
            continue
        price = Decimal(raw)
        bars.append(
            OhlcBar(ts_ms=_date_to_ms(day), open=price, high=price, low=price, close=price, volume=Decimal(0))
        )
    return bars


def fetch_btc_history(
    *, url: str = BTC_CSV_URL, client: httpx.Client | None = None
) -> list[OhlcBar]:
    """Fetch the full daily BTC/USD reference-price history (Coin Metrics)."""
    owns = client is None
    active = client if client is not None else httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
    try:
        resp = active.get(url)
        resp.raise_for_status()
        text = resp.text
    finally:
        if owns:
            active.close()
    return parse_coinmetrics_csv(text)
