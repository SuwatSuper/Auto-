# Layer 3 — Infrastructure (gateway/bitkub_orderbook)
"""READ-ONLY public order-book (depth) gateway for Bitkub.

Polls ``GET /api/v3/market/depth`` — Bitkub's *public* market endpoint that
needs no API key — and exposes the latest normalized :class:`OrderBook` plus a
short cache so many readers in one tick share a single fetch. This module places
NO orders: it never signs a request, never sends an API key, and only ever reads
via GET. The execution-cage guard (``test_execution_guard.py``) verifies that no
order-placement markers ever appear here.

Rate limiting is enforced through the shared :class:`TokenBucket` so depth polls
can never starve the price feed or trip Bitkub's limits.
"""
from __future__ import annotations

import contextlib
import time
from decimal import Decimal

import httpx

from domain.analytics.microstructure import OrderBook, order_book_imbalance, parse_depth
from infrastructure.gateway.rate_limiter import TokenBucket


class BitkubOrderBookFeed:
    """Fetches public depth on demand with a short freshness cache.

    Read-only by construction — the only HTTP verb used is GET against the public
    depth endpoint. Callers ``await snapshot()`` to get the freshest book within
    the cache TTL; a network/parse failure returns the last good book (or an
    empty one) and is surfaced via :attr:`last_error` rather than raised.
    """

    def __init__(
        self,
        base_url: str = "https://api.bitkub.com",
        symbol: str = "THB_BTC",
        *,
        limit: int = 20,
        cache_ttl_s: float = 1.0,
        rate_limiter: TokenBucket | None = None,
        client: httpx.AsyncClient | None = None,
        clock: object | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._symbol = symbol
        self._limit = max(1, limit)
        self._cache_ttl = max(0.0, cache_ttl_s)
        self._rate_limiter = rate_limiter
        self._client = client
        self._clock = clock if callable(clock) else time.monotonic
        self._book = OrderBook()
        self._fetched_at: float = -1.0
        self.last_error: str | None = None

    @property
    def book(self) -> OrderBook:
        """The last successfully fetched book (empty until the first poll)."""
        return self._book

    def imbalance(self, levels: int = 10) -> Decimal:
        """Convenience: top-of-book imbalance of the cached snapshot."""
        return order_book_imbalance(self._book, levels)

    async def snapshot(self) -> OrderBook:
        """Return a book no older than ``cache_ttl_s``; fetch fresh otherwise."""
        now = float(self._clock())
        if self._fetched_at >= 0 and (now - self._fetched_at) < self._cache_ttl:
            return self._book
        await self._fetch()
        return self._book

    async def _fetch(self) -> None:
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owns = self._client is None
        url = f"{self._base_url}/api/v3/market/depth"
        params = {"sym": self._symbol, "lmt": str(self._limit)}
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            book = parse_depth(resp.json(), max_levels=self._limit)
            # Keep the last good book if a poll returns an empty/garbage payload.
            if book.bids or book.asks:
                self._book = book
            self._fetched_at = float(self._clock())
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            if owns:
                with contextlib.suppress(Exception):
                    await client.aclose()
