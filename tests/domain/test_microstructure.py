# Tests — order-book microstructure features (U1)
from __future__ import annotations

from decimal import Decimal

from domain.analytics.microstructure import (
    OrderBook,
    bid_ask_spread_bps,
    depth_near_price,
    order_book_imbalance,
    parse_depth,
)

D = Decimal


# ── parse_depth: robust across Bitkub shapes ─────────────────────────
def test_parse_plain_shape_sorts_best_first() -> None:
    raw = {
        "bids": [["100", "1"], ["101", "2"], ["99", "3"]],
        "asks": [["104", "1"], ["102", "2"], ["103", "1"]],
    }
    book = parse_depth(raw)
    assert book.best_bid == D("101")  # highest bid first
    assert book.best_ask == D("102")  # lowest ask first
    assert book.mid == D("101.5")


def test_parse_enveloped_result() -> None:
    raw = {"error": 0, "result": {"bids": [[100, 1]], "asks": [[101, 1]]}}
    book = parse_depth(raw)
    assert book.best_bid == D("100") and book.best_ask == D("101")


def test_parse_drops_malformed_and_nonpositive_rows() -> None:
    raw = {
        "bids": [["100", "1"], ["bad", "1"], ["50", "-1"], [10], "nope"],
        "asks": [["101", "2"]],
    }
    book = parse_depth(raw)
    assert book.bids == ((D("100"), D("1")),)
    assert book.asks == ((D("101"), D("2")),)


def test_parse_garbage_returns_empty_book() -> None:
    assert parse_depth("garbage").bids == ()
    assert parse_depth({"nope": 1}).asks == ()
    assert parse_depth(None) == OrderBook()


def test_parse_respects_max_levels() -> None:
    raw = {"bids": [[100 - i, 1] for i in range(10)], "asks": [[200 + i, 1] for i in range(10)]}
    book = parse_depth(raw, max_levels=3)
    assert len(book.bids) == 3 and len(book.asks) == 3


# ── order_book_imbalance ─────────────────────────────────────────────
def test_imbalance_balanced_is_zero() -> None:
    book = OrderBook(bids=((D("100"), D("5")),), asks=((D("101"), D("5")),))
    assert order_book_imbalance(book) == D("0")


def test_imbalance_buy_pressure_positive() -> None:
    book = OrderBook(bids=((D("100"), D("9")),), asks=((D("101"), D("1")),))
    assert order_book_imbalance(book) == D("0.8")  # (9-1)/10


def test_imbalance_sell_pressure_negative() -> None:
    book = OrderBook(bids=((D("100"), D("1")),), asks=((D("101"), D("9")),))
    assert order_book_imbalance(book) == D("-0.8")


def test_imbalance_sums_top_n_levels() -> None:
    book = OrderBook(
        bids=((D("100"), D("2")), (D("99"), D("2")), (D("98"), D("100"))),
        asks=((D("101"), D("2")), (D("102"), D("2")), (D("103"), D("100"))),
    )
    # top-2 levels each side are equal → balanced; deep level ignored.
    assert order_book_imbalance(book, levels=2) == D("0")


def test_imbalance_one_sided_or_empty_is_zero() -> None:
    assert order_book_imbalance(OrderBook(bids=((D("100"), D("1")),))) == D("0")
    assert order_book_imbalance(OrderBook()) == D("0")
    assert order_book_imbalance(OrderBook(bids=((D("100"), D("1")),),
                                          asks=((D("101"), D("1")),), ), levels=0) == D("0")


# ── bid_ask_spread_bps ───────────────────────────────────────────────
def test_spread_bps_basic() -> None:
    book = OrderBook(bids=((D("100"), D("1")),), asks=((D("102"), D("1")),))
    # spread 2 over mid 101 → ~198.0198 bps
    spread = bid_ask_spread_bps(book)
    assert spread is not None and spread.quantize(D("0.01")) == D("198.02")


def test_spread_none_when_one_sided() -> None:
    assert bid_ask_spread_bps(OrderBook(bids=((D("100"), D("1")),))) is None
    assert bid_ask_spread_bps(OrderBook()) is None


def test_spread_none_when_crossed_book() -> None:
    # ask below bid (crossed/garbage) → no honest spread
    book = OrderBook(bids=((D("100"), D("1")),), asks=((D("99"), D("1")),))
    assert bid_ask_spread_bps(book) is None


# ── depth_near_price ─────────────────────────────────────────────────
def test_depth_near_price_bands() -> None:
    book = OrderBook(
        bids=((D("100"), D("3")), (D("99.0"), D("5"))),   # mid≈100.5, 0.5%→band 0.5025
        asks=((D("101"), D("4")), (D("102"), D("7"))),
    )
    bid_depth, ask_depth = depth_near_price(book, pct=D("0.5"))
    assert bid_depth == D("3")   # 99.0 is just outside the 0.5% band
    assert ask_depth == D("4")   # 102 is outside; 101 inside


def test_depth_near_price_unusable_book() -> None:
    assert depth_near_price(OrderBook()) == (D("0"), D("0"))
    book = OrderBook(bids=((D("100"), D("1")),), asks=((D("101"), D("1")),))
    assert depth_near_price(book, pct=D("0")) == (D("0"), D("0"))
