# Layer 1 — Domain (analytics/microstructure)
"""Pure order-book microstructure features over Decimal price/size levels.

The agent's price-only view misses what the *book* reveals: how much size is
queued to buy vs sell, how tight the spread is, and how thick liquidity sits
near the touch. These features are derived from Bitkub's public depth endpoint
(``/api/v3/market/depth`` — no key, READ-ONLY) and fed into the entry gate as a
soft confirm: a BUY into a book that is overwhelmingly offered (heavy sell side)
is a worse bet, all else equal.

Everything here is pure and deterministic — no I/O, Decimal math only. The
infrastructure gateway fetches the raw JSON; :func:`parse_depth` normalizes it.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_ZERO = Decimal("0")

# One book level: (price, size). Oldest exchanges quote size in base units.
Level = tuple[Decimal, Decimal]


@dataclass(frozen=True)
class OrderBook:
    """A normalized snapshot of one symbol's resting liquidity.

    ``bids`` are sorted best (highest price) first; ``asks`` best (lowest price)
    first. An empty side is allowed (a one-sided or warming-up book) — the
    feature functions degrade to NEUTRAL rather than fabricating a signal.
    """

    bids: tuple[Level, ...] = ()
    asks: tuple[Level, ...] = ()

    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0][0] if self.asks else None

    @property
    def mid(self) -> Decimal | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / Decimal(2)


def _coerce(value: object) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return d if d.is_finite() else None


def _coerce_levels(raw: object, *, descending: bool) -> tuple[Level, ...]:
    """Parse a side of the book from a list of ``[price, size]`` (or
    ``[price, size, ...]``) rows. Drops malformed/non-positive rows and sorts so
    the best price is first (bids descending, asks ascending)."""
    if not isinstance(raw, (list, tuple)):
        return ()
    levels: list[Level] = []
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        price = _coerce(row[0])
        size = _coerce(row[1])
        if price is None or size is None or price <= 0 or size <= 0:
            continue
        levels.append((price, size))
    levels.sort(key=lambda lv: lv[0], reverse=descending)
    return tuple(levels)


def parse_depth(data: object, *, max_levels: int = 50) -> OrderBook:
    """Normalize a Bitkub public-depth response into an :class:`OrderBook`.

    Handles the common shapes:
      - ``{"bids": [[p, s], ...], "asks": [[p, s], ...]}``
      - ``{"error": 0, "result": {"bids": ..., "asks": ...}}`` (enveloped)
    Returns an empty book (no raise) when nothing usable is present, so a bad
    poll never crashes the pipeline or fakes liquidity.
    """
    if isinstance(data, dict) and "result" in data and "bids" not in data:
        data = data["result"]
    if not isinstance(data, dict):
        return OrderBook()
    bids = _coerce_levels(data.get("bids"), descending=True)[:max_levels]
    asks = _coerce_levels(data.get("asks"), descending=False)[:max_levels]
    return OrderBook(bids=bids, asks=asks)


def _sum_size(levels: Sequence[Level], n: int) -> Decimal:
    return sum((lv[1] for lv in levels[:n]), _ZERO)


def order_book_imbalance(book: OrderBook, levels: int = 10) -> Decimal:
    """Volume imbalance over the top ``levels`` of each side, in [-1, +1].

    ``(bid_size - ask_size) / (bid_size + ask_size)``. Positive → more resting
    bid (buy) pressure; negative → more offered (sell) pressure. Returns 0 when
    either side is empty (no honest read possible).
    """
    if levels <= 0 or not book.bids or not book.asks:
        return _ZERO
    bid = _sum_size(book.bids, levels)
    ask = _sum_size(book.asks, levels)
    total = bid + ask
    if total <= 0:
        return _ZERO
    return ((bid - ask) / total).quantize(Decimal("0.000001"))


def bid_ask_spread_bps(book: OrderBook) -> Decimal | None:
    """Best bid/ask spread in basis points of the mid price, or None if the book
    is one-sided. A wide spread means thin/illiquid conditions — costlier to
    enter and exit."""
    bid = book.best_bid
    ask = book.best_ask
    mid = book.mid
    if bid is None or ask is None or mid is None or mid <= 0 or ask < bid:
        return None
    return ((ask - bid) / mid * Decimal("10000")).quantize(Decimal("0.0001"))


def depth_near_price(book: OrderBook, pct: Decimal = Decimal("0.5")) -> tuple[Decimal, Decimal]:
    """Total resting size within ``pct`` percent of the mid price, per side.

    Returns ``(bid_depth, ask_depth)``. Liquidity concentrated near the touch is
    what actually absorbs/propels a move; far-away orders rarely matter intraday.
    Returns ``(0, 0)`` for an unusable book.
    """
    mid = book.mid
    if mid is None or mid <= 0 or pct <= 0:
        return (_ZERO, _ZERO)
    band = mid * pct / Decimal("100")
    lo, hi = mid - band, mid + band
    bid_depth = sum((s for p, s in book.bids if p >= lo), _ZERO)
    ask_depth = sum((s for p, s in book.asks if p <= hi), _ZERO)
    return (bid_depth, ask_depth)
