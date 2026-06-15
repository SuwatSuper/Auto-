# Tests — READ-ONLY public order-book (depth) gateway (U1)
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from infrastructure.gateway.bitkub_orderbook import BitkubOrderBookFeed
from infrastructure.gateway.rate_limiter import TokenBucket

_DEPTH = {
    "bids": [["100", "8"], ["99", "1"]],
    "asks": [["101", "1"]],
}


class _Transport(httpx.AsyncBaseTransport):
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self._status = status
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        assert request.method == "GET", "depth gateway must be READ-ONLY (GET only)"
        assert "depth" in str(request.url)
        if self._status != 200:
            return httpx.Response(self._status, text="down")
        return httpx.Response(200, json=self._payload)


@pytest.mark.asyncio
async def test_snapshot_fetches_and_parses() -> None:
    t = _Transport(_DEPTH)
    feed = BitkubOrderBookFeed(client=httpx.AsyncClient(transport=t))
    book = await feed.snapshot()
    assert book.best_bid == Decimal("100") and book.best_ask == Decimal("101")
    assert feed.imbalance() == Decimal("0.8")
    assert feed.last_error is None


@pytest.mark.asyncio
async def test_cache_avoids_refetch_within_ttl() -> None:
    t = _Transport(_DEPTH)
    ticks = iter([0.0, 0.0, 0.5, 2.0, 2.0])  # deterministic monotonic clock
    feed = BitkubOrderBookFeed(
        client=httpx.AsyncClient(transport=t), cache_ttl_s=1.0, clock=lambda: next(ticks)
    )
    await feed.snapshot()   # fetch (now=0)
    await feed.snapshot()   # cached (now=0.5 < ttl)
    assert t.calls == 1
    await feed.snapshot()   # stale (now=2.0) → refetch
    assert t.calls == 2


@pytest.mark.asyncio
async def test_http_error_keeps_last_book_and_records_error() -> None:
    ok = _Transport(_DEPTH)
    feed = BitkubOrderBookFeed(client=httpx.AsyncClient(transport=ok), cache_ttl_s=0.0)
    await feed.snapshot()
    good = feed.book
    feed._client = httpx.AsyncClient(transport=_Transport(None, status=503))
    book = await feed.snapshot()
    assert book == good                      # last good book preserved
    assert feed.last_error is not None and "503" in feed.last_error


@pytest.mark.asyncio
async def test_empty_payload_does_not_clobber_last_book() -> None:
    feed = BitkubOrderBookFeed(client=httpx.AsyncClient(transport=_Transport(_DEPTH)), cache_ttl_s=0.0)
    await feed.snapshot()
    good = feed.book
    feed._client = httpx.AsyncClient(transport=_Transport({"bids": [], "asks": []}))
    assert (await feed.snapshot()) == good


@pytest.mark.asyncio
async def test_rate_limiter_is_consulted() -> None:
    bucket = TokenBucket(capacity=1, refill_per_sec=1000.0)
    feed = BitkubOrderBookFeed(
        client=httpx.AsyncClient(transport=_Transport(_DEPTH)),
        rate_limiter=bucket,
        cache_ttl_s=0.0,
    )
    await feed.snapshot()
    await feed.snapshot()  # second poll must also pass the limiter without error
    assert feed.book.best_bid == Decimal("100")


def test_gateway_has_no_order_placement_markers() -> None:
    """Defense in depth alongside the execution cage: this file must never gain
    signing or order-placement code."""
    src = Path(__file__).resolve().parents[2] / "src/infrastructure/gateway/bitkub_orderbook.py"
    text = src.read_text(encoding="utf-8")
    for marker in ("place-bid", "place-ask", "X-BTK-APIKEY", "cancel-order", "/api/v3/market/place"):
        assert marker not in text, f"order-placement marker {marker!r} leaked into the depth gateway"
