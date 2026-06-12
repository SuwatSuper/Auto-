from decimal import Decimal

import pytest
from pydantic import ValidationError

from domain.trading.models import PriceUpdate, Symbol, Tick


def _make_tick(**kwargs: object) -> Tick:
    defaults: dict[str, object] = {
        "symbol": Symbol.THB_BTC,
        "price": Decimal("1500000"),
        "ts_ms": 1_733_000_000_000,
        "source": "bitkub",
    }
    defaults.update(kwargs)
    return Tick(**defaults)  # type: ignore[arg-type]


def test_tick_rejects_float_price() -> None:
    with pytest.raises(ValidationError):
        _make_tick(price=1500000.5)


def test_tick_rejects_negative_price() -> None:
    with pytest.raises(ValidationError):
        _make_tick(price=Decimal("-1"))


def test_tick_rejects_zero_price() -> None:
    with pytest.raises(ValidationError):
        _make_tick(price=Decimal("0"))


def test_tick_rejects_negative_ts_ms() -> None:
    with pytest.raises(ValidationError):
        _make_tick(ts_ms=-1)


def test_tick_rejects_zero_ts_ms() -> None:
    with pytest.raises(ValidationError):
        _make_tick(ts_ms=0)


def test_tick_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Tick(
            symbol=Symbol.THB_BTC,
            price=Decimal("1500000"),
            ts_ms=1_733_000_000_000,
            source="bitkub",
            unknown_field="bad",
        )


def test_tick_is_frozen() -> None:
    tick = _make_tick()
    with pytest.raises(ValidationError):
        tick.price = Decimal("9999")  # type: ignore[misc]


def test_tick_equality_and_hash() -> None:
    tick_a = _make_tick()
    tick_b = _make_tick()
    assert tick_a == tick_b
    assert hash(tick_a) == hash(tick_b)


def test_price_update_from_tick_produces_32_char_hex_event_id() -> None:
    tick = _make_tick()
    update = PriceUpdate.from_tick(tick)
    assert len(update.event_id) == 32
    assert all(c in "0123456789abcdef" for c in update.event_id)


def test_price_update_from_tick_unique_event_ids() -> None:
    tick = _make_tick()
    update_a = PriceUpdate.from_tick(tick)
    update_b = PriceUpdate.from_tick(tick)
    assert update_a.event_id != update_b.event_id
