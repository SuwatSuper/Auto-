# Layer 3 — Infrastructure (gateway/news_rss)
"""Fetch crypto news headlines from public RSS feeds (no API key required).

Parses standard RSS 2.0 / Atom <item>/<entry> titles using the stdlib XML
parser — no third-party feed library, so there is nothing extra to install.
The headlines are scored by the pure domain function elsewhere.
"""
from __future__ import annotations

import contextlib
from xml.etree import ElementTree as ET

import httpx
import structlog

# Free, no-auth crypto RSS feeds.
DEFAULT_RSS_FEEDS: tuple[str, ...] = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://bitcoinmagazine.com/.rss/full/",
)


def parse_rss_titles(xml_text: str) -> list[str]:
    """Extract item/entry titles from RSS 2.0 or Atom XML. Never raises."""
    titles: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return titles
    # RSS 2.0: .//item/title ; Atom: .//{ns}entry/{ns}title
    for item in root.iter():
        tag = item.tag.rsplit("}", 1)[-1]  # strip namespace
        if tag in ("item", "entry"):
            for child in item:
                ctag = child.tag.rsplit("}", 1)[-1]
                if ctag == "title" and child.text:
                    titles.append(child.text.strip())
                    break
    return titles


class NewsRssFeed:
    """Polls a set of RSS feeds and returns recent headlines."""

    def __init__(
        self,
        feeds: tuple[str, ...] = DEFAULT_RSS_FEEDS,
        client: httpx.AsyncClient | None = None,
        max_per_feed: int = 15,
    ) -> None:
        self._feeds = feeds
        self._client = client
        self._max = max_per_feed
        self._log = structlog.get_logger(__name__)

    async def fetch_headlines(self) -> list[str]:
        """Return a de-duplicated list of recent headlines across all feeds.

        Network failures on individual feeds are swallowed (logged) so one bad
        feed never blocks the others.
        """
        client = self._client or httpx.AsyncClient(
            timeout=10.0, headers={"User-Agent": "KingdomPrime/1.0"}
        )
        owns = self._client is None
        seen: set[str] = set()
        out: list[str] = []
        try:
            for url in self._feeds:
                try:
                    resp = await client.get(url, follow_redirects=True)
                    resp.raise_for_status()
                    for title in parse_rss_titles(resp.text)[: self._max]:
                        key = title.lower()
                        if title and key not in seen:
                            seen.add(key)
                            out.append(title)
                except Exception as exc:
                    self._log.warning("news_rss.feed_failed", url=url, error=str(exc))
        finally:
            if owns:
                with contextlib.suppress(Exception):
                    await client.aclose()
        return out
