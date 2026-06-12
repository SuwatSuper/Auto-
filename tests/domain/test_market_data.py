# Layer 1 — Domain (tests/domain/test_market_data)
"""Tests for market_data normalize_bitkub_ticker (P1: pure function with now_ms)."""
from __future__ import annotations

from decimal import Decimal

from domain.trading.market_data import (
    NormalizationFailure,
    NormalizationReason,
    PriceUpdate,
    normalize_bitkub_ticker,
)

_NOW_MS = 1_700_000_000_000  # fixed "now" for tests


def _valid_raw(**kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "stream": "market.ticker.thb_btc",
        "last": "1500000.00",
        "ts": 1_700_000_000,  # seconds → 1_700_000_000_000 ms
    }
    base.update(kwargs)
    return base


def _norm(**kwargs: object) -> PriceUpdate | NormalizationFailure:
    return normalize_bitkub_ticker(_valid_raw(**kwargs), now_ms=_NOW_MS)


def test_valid_payload_returns_price_update() -> None:
    result = _norm()
    assert isinstance(result, PriceUpdate)
    assert result.price == Decimal("1500000.00")
    assert result.symbol == "THB_BTC"
    assert result.source == "bitkub"
    assert result.version == 1


def test_not_a_dict_returns_failure() -> None:
    result = normalize_bitkub_ticker("not a dict", now_ms=_NOW_MS)  # type: ignore[arg-type]
    assert isinstance(result, NormalizationFailure)
    assert result.reason == NormalizationReason.NOT_A_DICT


def test_missing_last_returns_failure() -> None:
    raw = _valid_raw()
    del raw["last"]
    result = normalize_bitkub_ticker(raw, now_ms=_NOW_MS)
    assert isinstance(result, NormalizationFailure)
    assert result.reason == NormalizationReason.MISSING_LAST


def test_bad_price_returns_failure() -> None:
    result = _norm(last="not-a-number")
    assert isinstance(result, NormalizationFailure)
    assert result.reason == NormalizationReason.BAD_PRICE


def test_non_positive_price_returns_failure() -> None:
    r1 = _norm(last="0")
    assert isinstance(r1, NormalizationFailure)
    assert r1.reason == NormalizationReason.NON_POSITIVE_PRICE

    r2 = _norm(last="-100")
    assert isinstance(r2, NormalizationFailure)
    assert r2.reason == NormalizationReason.NON_POSITIVE_PRICE


def test_missing_timestamp_returns_failure() -> None:
    raw = _valid_raw()
    del raw["ts"]
    result = normalize_bitkub_ticker(raw, now_ms=_NOW_MS)
    assert isinstance(result, NormalizationFailure)
    assert result.reason == NormalizationReason.BAD_TIMESTAMP


def test_ts_in_seconds_converted_to_ms() -> None:
    result = _norm(ts=1_700_000_000)
    assert isinstance(result, PriceUpdate)
    assert result.ts_ms == 1_700_000_000_000


def test_ts_already_in_ms() -> None:
    # Remove 'ts' and set ts_ms directly
    raw: dict[str, object] = {
        "stream": "market.ticker.thb_btc",
        "last": "1500000.00",
        "ts_ms": 1_700_000_000_000,
    }
    result = normalize_bitkub_ticker(raw, now_ms=_NOW_MS)
    assert isinstance(result, PriceUpdate)
    assert result.ts_ms == 1_700_000_000_000


def test_symbol_extracted_from_stream() -> None:
    result = _norm(stream="market.ticker.thb_eth")
    assert isinstance(result, PriceUpdate)
    assert result.symbol == "THB_ETH"


def test_event_id_is_unique() -> None:
    r1 = _norm()
    r2 = _norm()
    assert isinstance(r1, PriceUpdate) and isinstance(r2, PriceUpdate)
    assert r1.event_id != r2.event_id


def test_stale_timestamp_returns_failure() -> None:
    """Timestamps older than max_age_ms should be rejected."""
    stale_ts_ms = _NOW_MS - 120_000  # 2 minutes ago (default max 60s)
    raw: dict[str, object] = {
        "stream": "market.ticker.thb_btc",
        "last": "1500000.00",
        "ts_ms": stale_ts_ms,
    }
    result = normalize_bitkub_ticker(raw, now_ms=_NOW_MS)
    assert isinstance(result, NormalizationFailure)
    assert result.reason == NormalizationReason.STALE


def test_future_skew_returns_failure() -> None:
    """Timestamps far in the future should be rejected."""
    future_ts_ms = _NOW_MS + 10_000  # 10s in future (default max_skew 5s)
    raw: dict[str, object] = {
        "stream": "market.ticker.thb_btc",
        "last": "1500000.00",
        "ts_ms": future_ts_ms,
    }
    result = normalize_bitkub_ticker(raw, now_ms=_NOW_MS)
    assert isinstance(result, NormalizationFailure)
    assert result.reason == NormalizationReason.FUTURE_SKEW


def test_bad_timestamp_value_returns_failure() -> None:
    """A timestamp that can't be parsed as int returns BAD_TIMESTAMP."""
    raw: dict[str, object] = {
        "stream": "market.ticker.thb_btc",
        "last": "1500000.00",
        "ts": "not-a-timestamp",
    }
    result = normalize_bitkub_ticker(raw, now_ms=_NOW_MS)
    assert isinstance(result, NormalizationFailure)
    assert result.reason == NormalizationReason.BAD_TIMESTAMP
