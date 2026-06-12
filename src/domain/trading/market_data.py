# Layer 1 — Domain (trading/market_data)
"""Market data domain models and pure normalization function."""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class PriceUpdate(BaseModel, frozen=True):
    """Normalized price update event."""

    event_id: str
    symbol: str
    price: Decimal
    ts_ms: int
    source: str
    version: int = 1


class NormalizationReason(StrEnum):
    """Machine-readable rejection codes for normalize_bitkub_ticker."""

    NOT_A_DICT = "NOT_A_DICT"
    MISSING_LAST = "MISSING_LAST"
    BAD_PRICE = "BAD_PRICE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    BAD_TIMESTAMP = "BAD_TIMESTAMP"
    STALE = "STALE"
    FUTURE_SKEW = "FUTURE_SKEW"
    INTERNAL = "INTERNAL"


class NormalizationFailure(BaseModel, frozen=True):
    """Returned when a raw ticker cannot be normalized."""

    reason: NormalizationReason


def normalize_bitkub_ticker(
    raw: object,
    *,
    now_ms: int,
    max_age_ms: int = 60_000,
    max_skew_ms: int = 5_000,
) -> PriceUpdate | NormalizationFailure:
    """Normalize a raw Bitkub ticker payload to a PriceUpdate.

    Pure function: no I/O, no logging, no side effects.
    The caller passes concrete now_ms so clocks are injected, not called here.

    Bitkub's ticker stream carries no timestamp; the injected now_ms is used as event time.

    Returns PriceUpdate on success, NormalizationFailure on any invalid input.
    """
    try:
        if not isinstance(raw, dict):
            return NormalizationFailure(reason=NormalizationReason.NOT_A_DICT)

        raw_dict: dict[str, Any] = raw

        last_val = raw_dict.get("last")
        if last_val is None:
            return NormalizationFailure(reason=NormalizationReason.MISSING_LAST)

        try:
            price = Decimal(str(last_val))
        except (InvalidOperation, TypeError):
            return NormalizationFailure(reason=NormalizationReason.BAD_PRICE)

        if price <= 0:
            return NormalizationFailure(reason=NormalizationReason.NON_POSITIVE_PRICE)

        # Accept ts_ms (milliseconds) or ts (seconds); Bitkub ticker stream has no timestamp.
        ts_raw = raw_dict.get("ts_ms") or raw_dict.get("ts")
        if ts_raw is None:
            # No exchange-provided timestamp — use injected now_ms as event time.
            ts_ms = now_ms
        else:
            try:
                ts_int = int(str(ts_raw))
                # Seconds (< year 2100 in ms ≈ 4e12) → convert to ms
                ts_ms = ts_int * 1000 if ts_int < 1_000_000_000_000 else ts_int
            except (ValueError, TypeError):
                return NormalizationFailure(reason=NormalizationReason.BAD_TIMESTAMP)

            age_ms = now_ms - ts_ms
            if age_ms > max_age_ms:
                return NormalizationFailure(reason=NormalizationReason.STALE)
            if ts_ms - now_ms > max_skew_ms:
                return NormalizationFailure(reason=NormalizationReason.FUTURE_SKEW)

        # Extract symbol from stream name
        stream = str(raw_dict.get("stream", "market.ticker.thb_btc"))
        parts = stream.split(".")
        symbol = parts[-1].upper() if parts else "THB_BTC"

        return PriceUpdate(
            event_id=str(uuid.uuid4()),
            symbol=symbol,
            price=price,
            ts_ms=ts_ms,
            source="bitkub",
            version=1,
        )
    except Exception:
        return NormalizationFailure(reason=NormalizationReason.INTERNAL)
