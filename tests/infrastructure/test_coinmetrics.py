# Layer 3 — Infrastructure (tests/infrastructure/test_coinmetrics)
"""Unit tests for the Coin Metrics BTC history parser + fetcher."""
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from infrastructure.gateway.coinmetrics import fetch_btc_history, parse_coinmetrics_csv

_CSV = (
    "time,AdrActCnt,PriceUSD\n"
    "2009-01-03,0,\n"  # pre-market: no price -> skipped
    "2010-07-18,5,0.08584\n"
    "2021-11-08,9,67566.83\n"
)


def test_parse_skips_empty_price_and_builds_close_only_bars() -> None:
    bars = parse_coinmetrics_csv(_CSV)
    assert len(bars) == 2  # the empty-price 2009 row is skipped
    first = bars[0]
    assert first.close == Decimal("0.08584")
    # close-only: open == high == low == close
    assert first.open == first.high == first.low == first.close
    assert first.volume == Decimal(0)
    # 2010-07-18 UTC midnight in ms
    assert first.ts_ms == 1279411200 * 1000
    assert bars[1].close == Decimal("67566.83")


def test_parse_requires_time_and_price_columns() -> None:
    with pytest.raises(ValueError, match="time"):
        parse_coinmetrics_csv("foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="PriceUSD"):
        parse_coinmetrics_csv("time,other\n2020-01-01,5\n")


def test_parse_custom_price_column() -> None:
    bars = parse_coinmetrics_csv("time,ref\n2020-01-01,9000.5\n", price_col="ref")
    assert bars[0].close == Decimal("9000.5")


def test_fetch_btc_history_via_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("btc.csv")
        return httpx.Response(200, text=_CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bars = fetch_btc_history(client=client)
    assert len(bars) == 2
    assert bars[-1].close == Decimal("67566.83")
