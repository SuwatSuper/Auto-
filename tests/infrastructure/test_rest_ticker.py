# Tests — REST ticker price feed parsing + polling
from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal

import httpx
import pytest

from infrastructure.gateway.bitkub_rest_ticker import (
    BitkubRestTickerFeed,
    extract_last_price,
)

# ── robust parsing across Bitkub response shapes ─────────────────────

def test_extract_map_shape() -> None:
    assert extract_last_price({"THB_BTC": {"last": 2883194.85}}) == Decimal("2883194.85")


def test_extract_list_shape() -> None:
    data = [{"symbol": "THB_BTC", "last": 2900000}, {"symbol": "THB_ETH", "last": 90000}]
    assert extract_last_price(data) == Decimal("2900000")


def test_extract_enveloped() -> None:
    assert extract_last_price({"error": 0, "result": {"THB_BTC": {"last": 2_700_000}}}) == Decimal("2700000")


def test_extract_flat() -> None:
    assert extract_last_price({"last": "2750000.5"}) == Decimal("2750000.5")


def test_extract_single_item_list() -> None:
    assert extract_last_price([{"last": 2650000}]) == Decimal("2650000")


def test_extract_missing_returns_none() -> None:
    assert extract_last_price({"nope": 1}) is None
    assert extract_last_price({"last": -5}) is None  # non-positive rejected
    assert extract_last_price("garbage") is None


@pytest.mark.parametrize("bad", ["NaN", "nan", "Infinity", "-Infinity", "inf", "-inf"])
def test_extract_non_finite_returns_none(bad: str) -> None:
    """Regression: a non-finite quote must return None per the contract. Before
    the fix, 'NaN' raised InvalidOperation on the ``> 0`` check and 'Infinity'
    leaked a Decimal('Infinity') downstream."""
    assert extract_last_price({"THB_BTC": {"last": bad}}) is None


# ── version-proof: Bitkub ships the pair as THB_BTC OR BTC_THB ────────

def test_extract_reversed_pair_map() -> None:
    # Newer v3 responses can key the pair as BTC_THB.
    assert extract_last_price({"BTC_THB": {"last": 2_900_000}}) == Decimal("2900000")


def test_extract_reversed_pair_list() -> None:
    data = [{"symbol": "BTC_THB", "last": 2_910_000}, {"symbol": "ETH_THB", "last": 90000}]
    assert extract_last_price(data) == Decimal("2910000")


@pytest.mark.asyncio
async def test_feed_emits_from_reversed_full_ticker() -> None:
    # Symbol-scoped queries return nothing usable; the full-ticker fallback
    # (a list keyed BTC_THB) must still yield a price.
    class _T(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):  # type: ignore[no-untyped-def]
            if request.url.params.get("sym"):
                return httpx.Response(200, json=[])  # 200 but empty
            return httpx.Response(200, json=[{"symbol": "BTC_THB", "last": 2_950_000}])

    client = httpx.AsyncClient(transport=_T())
    feed = BitkubRestTickerFeed(interval_s=0.5, client=client)
    seen: list[dict] = []
    task = asyncio.create_task(feed.run(seen.append))  # type: ignore[arg-type]
    await asyncio.sleep(0.2)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await client.aclose()
    assert feed.last_price == Decimal("2950000")
    assert seen and seen[0]["last"] == "2950000"


# ── polling delivers prices to the on_raw callback ───────────────────

class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, payload) -> None:  # type: ignore[no-untyped-def]
        self._payload = payload

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self._payload)


@pytest.mark.asyncio
async def test_feed_polls_and_emits() -> None:
    client = httpx.AsyncClient(transport=_MockTransport({"THB_BTC": {"last": 2880000}}))
    feed = BitkubRestTickerFeed(interval_s=0.5, client=client)
    seen: list[dict] = []

    async def on_raw(d):  # type: ignore[no-untyped-def]
        seen.append(d)

    task = asyncio.create_task(feed.run(on_raw))
    await asyncio.sleep(0.2)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await client.aclose()

    assert seen and seen[0]["last"] == "2880000"
    assert seen[0]["symbol"] == "THB_BTC"
    assert feed.last_price == Decimal("2880000")


@pytest.mark.asyncio
async def test_feed_survives_http_error() -> None:
    class _ErrTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):  # type: ignore[no-untyped-def]
            return httpx.Response(503, text="down")

    client = httpx.AsyncClient(transport=_ErrTransport())
    feed = BitkubRestTickerFeed(interval_s=0.5, client=client)
    # should not raise; just retries with backoff
    task = asyncio.create_task(feed.run(lambda d: asyncio.sleep(0)))
    await asyncio.sleep(0.1)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await client.aclose()
    assert feed.last_price is None
