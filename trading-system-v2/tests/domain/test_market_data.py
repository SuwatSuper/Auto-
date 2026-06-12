# Layer 1 — Domain (tests/domain/test_market_data)
"""Tests for market_data normalize_bitkub_ticker."""
from __future__ import annotations

from decimal import Decimal

from domain.trading.market_data import PriceUpdate, normalize_bitkub_ticker


def _valid_raw(**kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "stream": "market.ticker.thb_btc",
        "last": "1500000.00",
        "ts": 1_700_000_000,
    }
    base.update(kwargs)
    return base


def test_valid_payload_returns_price_update() -> None:
    result = normalize_bitkub_ticker(_valid_raw())
    assert isinstance(result, PriceUpdate)
    assert result.price == Decimal("1500000.00")
    assert result.symbol == "THB_BTC"
    assert result.source == "bitkub"
    assert result.version == 1


def test_not_a_dict_returns_none() -> None:
    assert normalize_bitkub_ticker("not a dict") is None  # type: ignore[arg-type]


def test_missing_last_returns_none() -> None:
    raw = _valid_raw()
    del raw["last"]
    assert normalize_bitkub_ticker(raw) is None


def test_bad_price_returns_none() -> None:
    assert normalize_bitkub_ticker(_valid_raw(last="not-a-number")) is None


def test_non_positive_price_returns_none() -> None:
    assert normalize_bitkub_ticker(_valid_raw(last="0")) is None
    assert normalize_bitkub_ticker(_valid_raw(last="-100")) is None


def test_missing_timestamp_returns_none() -> None:
    raw = _valid_raw()
    del raw["ts"]
    assert normalize_bitkub_ticker(raw) is None


def test_ts_in_seconds_converted_to_ms() -> None:
    result = normalize_bitkub_ticker(_valid_raw(ts=1_700_000_000))
    assert result is not None
    assert result.ts_ms == 1_700_000_000_000


def test_ts_already_in_ms() -> None:
    result = normalize_bitkub_ticker(_valid_raw(ts_ms=1_700_000_000_000, ts=None))
    assert result is not None
    assert result.ts_ms == 1_700_000_000_000


def test_symbol_extracted_from_stream() -> None:
    result = normalize_bitkub_ticker(_valid_raw(stream="market.ticker.thb_eth"))
    assert result is not None
    assert result.symbol == "THB_ETH"


def test_event_id_is_unique() -> None:
    r1 = normalize_bitkub_ticker(_valid_raw())
    r2 = normalize_bitkub_ticker(_valid_raw())
    assert r1 is not None and r2 is not None
    assert r1.event_id != r2.event_id
