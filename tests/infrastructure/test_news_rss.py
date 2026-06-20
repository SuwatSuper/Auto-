# Tests — RSS parsing + fetcher
from __future__ import annotations

import httpx
import pytest

from infrastructure.gateway.news_rss import NewsRssFeed, parse_rss_titles

_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Bitcoin surges past resistance</title></item>
<item><title>Ethereum upgrade approved</title></item>
</channel></rss>"""

_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Crypto rally continues</title></entry>
</feed>"""


def test_parse_rss():
    assert parse_rss_titles(_RSS) == ["Bitcoin surges past resistance", "Ethereum upgrade approved"]


def test_parse_atom():
    assert parse_rss_titles(_ATOM) == ["Crypto rally continues"]


def test_parse_garbage_safe():
    assert parse_rss_titles("not xml at all") == []


@pytest.mark.asyncio
async def test_fetch_dedupes_and_survives_bad_feed():
    class _T(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if "bad" in str(request.url):
                return httpx.Response(503, text="down")
            return httpx.Response(200, text=_RSS)

    client = httpx.AsyncClient(transport=_T())
    feed = NewsRssFeed(feeds=("http://good/feed", "http://bad/feed", "http://good2/feed"), client=client)
    titles = await feed.fetch_headlines()
    await client.aclose()
    # both good feeds return the same 2 items -> deduped to 2; bad feed ignored
    assert titles == ["Bitcoin surges past resistance", "Ethereum upgrade approved"]
