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


def _pair_aliases(symbol: str) -> set[str]:
    """All accepted spellings of a THB/BTC pair.

    Bitkub has shipped the pair in BOTH orientations across API versions:
      - classic / some v3 responses → ``THB_BTC``
      - newer v3 responses          → ``BTC_THB``
    Matching either (case-insensitively) makes the feed version-proof.
    """
    s = symbol.upper()
    out = {s}
    if "_" in s:
        a, b = s.split("_", 1)
        out.add(f"{b}_{a}")
    return out


def extract_last_price(data: object, symbol: str = "THB_BTC") -> Decimal | None:
    """Pull the last price for ``symbol`` from any common Bitkub ticker shape.

    Handles (and matches the pair in EITHER orientation, THB_BTC / BTC_THB):
      - {"THB_BTC": {"last": 2883194.85, ...}}            (classic / v3 map)
      - [{"symbol": "THB_BTC", "last": ...}, ...]         (list of tickers)
      - {"error": 0, "result": <one of the above>}        (enveloped)
      - {"last": 2883194.85}                               (already flat)
    Returns a positive Decimal, or None if nothing usable was found.
    """
    # Unwrap a Bitkub error/result envelope.
    if isinstance(data, dict) and "result" in data and "last" not in data:
        data = data["result"]

    aliases = _pair_aliases(symbol)
    candidate: Any = None
    if isinstance(data, dict):
        # Match any key spelling (THB_BTC or BTC_THB), case-insensitively.
        for key, value in data.items():
            if str(key).upper() in aliases and isinstance(value, dict):
                candidate = value.get("last")
                break
        if candidate is None and "last" in data:
            candidate = data.get("last")
    elif isinstance(data, list):
        # Find the matching symbol; fall back to a single-item list.
        for item in data:
            if not isinstance(item, dict):
                continue
            sym = str(item.get("symbol") or item.get("sym") or "").upper()
            if sym in aliases:
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
    # A non-finite quote (NaN / Infinity) parses as a Decimal but would crash
    # the ``price > 0`` comparison (NaN) or leak an Infinity downstream, so the
    # contract ("a positive Decimal, or None") is enforced with an explicit
    # finiteness check.
    if not price.is_finite():
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
        # Diagnostics surfaced to the dashboard so a missing price is explained.
        self.last_error: str | None = None

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
                        self.last_error = None
                        await on_raw({"last": str(price), "symbol": self._symbol})
                    else:
                        # 200 OK but the pair was not found in the response.
                        self.last_error = "ticker ok but pair not found in response"
                        self._log.warning("bitkub_rest_ticker.no_price", symbol=self._symbol)
                    attempt = 0
                    await asyncio.sleep(self._interval)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
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
        """Resilient poll: try the symbol-scoped query in both orientations,
        then fall back to the full ticker. Version-proof against Bitkub's
        THB_BTC ↔ BTC_THB symbol change."""
        url = f"{self._base_url}/api/v3/market/ticker"
        # 1) symbol-scoped queries (tolerate per-query HTTP errors, e.g. an
        #    "invalid symbol" 400 for the orientation this API version rejects).
        for sym in _pair_aliases(self._symbol):
            data = await self._get(client, url, {"sym": sym}, raise_on_error=False)
            if data is not None:
                price = extract_last_price(data, self._symbol)
                if price is not None:
                    return price
        # 2) full ticker (no sym filter) — most robust; pick our pair from the
        #    list/map. Let a hard failure here propagate so the loop backs off.
        data = await self._get(client, url, None, raise_on_error=True)
        return extract_last_price(data, self._symbol)

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, str] | None,
        *,
        raise_on_error: bool,
    ) -> object | None:
        """GET helper. Returns parsed JSON, or None on HTTP error when
        ``raise_on_error`` is False (so a fallback can still be tried)."""
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload: object = resp.json()
            return payload
        except Exception:
            if raise_on_error:
                raise
            return None

    def _backoff(self, attempt: int) -> float:
        base = min(self._BACKOFF_BASE * float(2**attempt), self._BACKOFF_CAP)
        jitter = base * 0.2 * (random.random() * 2.0 - 1.0)
        return float(max(0.0, base + jitter))
