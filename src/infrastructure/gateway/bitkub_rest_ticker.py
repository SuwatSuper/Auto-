# Layer 3 — Infrastructure (gateway/bitkub_rest_ticker)
"""REST-polling price feed for Bitkub.

Implements the PriceFeed port by polling GET /api/v3/market/ticker on an
interval, instead of holding a WebSocket. REST is firewall-friendly and the v3
ticker endpoint is not deprecated, which makes it far more reliable than the
public WS streams (some of which Bitkub is phasing out).

Each poll extracts the last price and hands a {"last": price, "symbol": ...}
dict to the same normalizer the WS path uses, so the rest of the pipeline is
unchanged.
"""
from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import structlog


def extract_last_price(data: object, symbol: str = "THB_BTC") -> Decimal | None:
    """Pull the last price for ``symbol`` from any common Bitkub ticker shape.

    Handles:
      - {"THB_BTC": {"last": 2883194.85, ...}}            (classic / v3 map)
      - [{"symbol": "THB_BTC", "last": ...}, ...]         (list of tickers)
      - {"error": 0, "result": <one of the above>}        (enveloped)
      - {"last": 2883194.85}                               (already flat)
    Returns a positive Decimal, or None if nothing usable was found.
    """
    # Unwrap a Bitkub error/result envelope.
    if isinstance(data, dict) and "result" in data and "last" not in data:
        data = data["result"]

    candidate: Any = None
    if isinstance(data, dict):
        if symbol in data and isinstance(data[symbol], dict):
            candidate = data[symbol].get("last")
        elif symbol.upper() in data and isinstance(data[symbol.upper()], dict):
            candidate = data[symbol.upper()].get("last")
        elif "last" in data:
            candidate = data.get("last")
    elif isinstance(data, list):
        # Find the matching symbol; fall back to a single-item list.
        for item in data:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol") or item.get("sym") or "").upper()
            if sym == symbol.upper():
                candidate = item.get("last")
                break
        if candidate is None and len(data) == 1 and isinstance(data[0], dict):
            candidate = data[0].get("last")

    if candidate is None:
        return None
    try:
        price = Decimal(str(candidate))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return price if price > 0 else None


class BitkubRestTickerFeed:
    """Polls the Bitkub v3 ticker and feeds normalized price dicts."""

    _BACKOFF_BASE: float = 1.0
    _BACKOFF_CAP: float = 30.0

    def __init__(
        self,
        base_url: str = "https://api.bitkub.com",
        symbol: str = "THB_BTC",
        interval_s: float = 3.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._symbol = symbol
        self._interval = max(0.5, interval_s)
        self._client = client
        self._log = structlog.get_logger(__name__)
        self.last_price: Decimal | None = None

    async def run(self, on_raw: Callable[[dict[str, object]], Awaitable[None]]) -> None:
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owns = self._client is None
        attempt = 0
        self._log.info("bitkub_rest_ticker.started", url=self._base_url, symbol=self._symbol)
        try:
            while True:
                try:
                    price = await self._poll_once(client)
                    if price is not None:
                        self.last_price = price
                        await on_raw({"last": str(price), "symbol": self._symbol})
                    attempt = 0
                    await asyncio.sleep(self._interval)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    delay = self._backoff(attempt)
                    self._log.warning(
                        "bitkub_rest_ticker.error", error=str(exc), retry_s=round(delay, 2)
                    )
                    attempt += 1
                    await asyncio.sleep(delay)
        finally:
            if owns:
                with contextlib.suppress(Exception):
                    await client.aclose()

    async def _poll_once(self, client: httpx.AsyncClient) -> Decimal | None:
        url = f"{self._base_url}/api/v3/market/ticker"
        resp = await client.get(url, params={"sym": self._symbol})
        resp.raise_for_status()
        return extract_last_price(resp.json(), self._symbol)

    def _backoff(self, attempt: int) -> float:
        base = min(self._BACKOFF_BASE * float(2**attempt), self._BACKOFF_CAP)
        jitter = base * 0.2 * (random.random() * 2.0 - 1.0)
        return float(max(0.0, base + jitter))
