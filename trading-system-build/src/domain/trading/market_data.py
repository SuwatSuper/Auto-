from __future__ import annotations

import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation

import structlog

from domain.trading.models import PriceUpdate, Symbol, Tick


def _default_now_ms() -> int:
    return time.time_ns() // 1_000_000


def normalize_bitkub_ticker(
    raw: object,
    *,
    now_ms: Callable[[], int] = _default_now_ms,
    max_age_ms: int = 60_000,
    max_skew_ms: int = 5_000,
    logger: structlog.BoundLogger | None = None,
) -> PriceUpdate | None:
    _log = logger or structlog.get_logger(__name__)
    try:
        if not isinstance(raw, dict):
            return None

        last: object = None
        data_dict: dict[str, object] = {}

        if "last" in raw:
            last = raw["last"]
            data_dict = raw
        elif isinstance(raw.get("data"), dict):
            nested = raw["data"]
            if isinstance(nested, dict):
                data_dict = nested
                last = data_dict.get("last")

        if last is None:
            return None

        ts_val = data_dict.get("ts")
        computed_ts_ms: int
        if isinstance(ts_val, int):
            computed_ts_ms = ts_val * 1000
        else:
            ts_ms_val = data_dict.get("ts_ms")
            if isinstance(ts_ms_val, int):
                computed_ts_ms = ts_ms_val
            else:
                computed_ts_ms = now_ms()

        try:
            price = Decimal(str(last))
        except InvalidOperation:
            return None

        if price <= 0:
            return None

        if computed_ts_ms <= 0:
            return None

        current_ms = now_ms()
        if current_ms - computed_ts_ms > max_age_ms:
            return None
        if computed_ts_ms - current_ms > max_skew_ms:
            return None

        tick = Tick(
            symbol=Symbol.THB_BTC,
            price=price,
            ts_ms=computed_ts_ms,
            source="bitkub",
        )
        return PriceUpdate.from_tick(tick)

    except Exception as exc:
        _log.warning("normalize_bitkub_ticker failed", exc_info=exc)
        return None
