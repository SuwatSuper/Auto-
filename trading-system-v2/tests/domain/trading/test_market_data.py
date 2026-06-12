import copy
from decimal import Decimal

from domain.trading.market_data import _default_now_ms, normalize_bitkub_ticker


def _now_fn(fixed_ms: int):  # type: ignore[no-untyped-def]
    def _inner() -> int:
        return fixed_ms

    return _inner


def test_valid_flat_payload(valid_bitkub_payload: dict, fixed_now_ms: int) -> None:
    result = normalize_bitkub_ticker(valid_bitkub_payload, now_ms=_now_fn(fixed_now_ms))
    assert result is not None
    assert result.price == Decimal("1500000.50")
    assert result.source == "bitkub"


def test_valid_nested_payload(fixed_now_ms: int) -> None:
    ts_sec = fixed_now_ms // 1000
    raw = {"data": {"last": "1500000.50", "ts": ts_sec}}
    result = normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms))
    assert result is not None
    assert result.price == Decimal("1500000.50")


def test_raw_none_returns_none(fixed_now_ms: int) -> None:
    assert normalize_bitkub_ticker(None, now_ms=_now_fn(fixed_now_ms)) is None


def test_raw_string_returns_none(fixed_now_ms: int) -> None:
    assert normalize_bitkub_ticker("string", now_ms=_now_fn(fixed_now_ms)) is None


def test_raw_list_returns_none(fixed_now_ms: int) -> None:
    assert normalize_bitkub_ticker([], now_ms=_now_fn(fixed_now_ms)) is None


def test_missing_last_returns_none(fixed_now_ms: int) -> None:
    raw = {"stream": "market.ticker.thb_btc", "ts": fixed_now_ms // 1000}
    assert normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms)) is None


def test_last_non_numeric_returns_none(fixed_now_ms: int) -> None:
    raw = {"last": "abc", "ts": fixed_now_ms // 1000}
    assert normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms)) is None


def test_last_zero_returns_none(fixed_now_ms: int) -> None:
    raw = {"last": "0", "ts": fixed_now_ms // 1000}
    assert normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms)) is None


def test_last_negative_returns_none(fixed_now_ms: int) -> None:
    raw = {"last": "-1", "ts": fixed_now_ms // 1000}
    assert normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms)) is None


def test_ts_too_old_returns_none(fixed_now_ms: int) -> None:
    old_ts_sec = (fixed_now_ms - 61_000) // 1000
    raw = {"last": "1500000.50", "ts": old_ts_sec}
    assert normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms)) is None


def test_ts_too_far_in_future_returns_none(fixed_now_ms: int) -> None:
    future_ts_sec = (fixed_now_ms + 6_000) // 1000
    raw = {"last": "1500000.50", "ts": future_ts_sec}
    assert normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms)) is None


def test_input_dict_not_mutated(valid_bitkub_payload: dict, fixed_now_ms: int) -> None:
    original = copy.deepcopy(valid_bitkub_payload)
    normalize_bitkub_ticker(valid_bitkub_payload, now_ms=_now_fn(fixed_now_ms))
    assert valid_bitkub_payload == original


def test_two_valid_calls_produce_different_event_ids(
    valid_bitkub_payload: dict, fixed_now_ms: int
) -> None:
    result_a = normalize_bitkub_ticker(valid_bitkub_payload, now_ms=_now_fn(fixed_now_ms))
    result_b = normalize_bitkub_ticker(valid_bitkub_payload, now_ms=_now_fn(fixed_now_ms))
    assert result_a is not None
    assert result_b is not None
    assert result_a.event_id != result_b.event_id


def test_nested_payload_with_ts_ms_field(fixed_now_ms: int) -> None:
    raw = {"data": {"last": "1500000.50", "ts_ms": fixed_now_ms}}
    result = normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms))
    assert result is not None
    assert result.price == Decimal("1500000.50")


def test_nested_payload_no_ts_uses_now(fixed_now_ms: int) -> None:
    raw = {"data": {"last": "1500000.50"}}
    result = normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms))
    assert result is not None


def test_flat_payload_no_ts_uses_now(fixed_now_ms: int) -> None:
    raw = {"last": "1500000.50"}
    result = normalize_bitkub_ticker(raw, now_ms=_now_fn(fixed_now_ms))
    assert result is not None


def test_unexpected_exception_returns_none(fixed_now_ms: int) -> None:
    class BadDict(dict):  # type: ignore[type-arg]
        def __contains__(self, key: object) -> bool:
            raise RuntimeError("unexpected error")

    result = normalize_bitkub_ticker(BadDict(), now_ms=_now_fn(fixed_now_ms))
    assert result is None


def test_default_now_ms_is_callable() -> None:
    ms = _default_now_ms()
    assert isinstance(ms, int)
    assert ms > 0
