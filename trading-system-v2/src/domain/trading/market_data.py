# Layer 1 — Domain (trading/market_data)
"""Market data domain models and normalization for trading.

NOTE: structlog is imported here for P0 compatibility with price_supervisor.py.
P1 will refactor normalize_bitkub_ticker to be pure (no structlog dependency).
"""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    import structlog


class PriceUpdate(BaseModel, frozen=True):
    """Normalized price update event."""

    event_id: str
    symbol: str
    price: Decimal
    ts_ms: int
    source: str
    version: int = 1


def normalize_bitkub_ticker(
    raw: dict[str, Any],
    *,
    logger: structlog.BoundLogger | None = None,
) -> PriceUpdate | None:
    """Normalize a raw Bitkub ticker payload to a PriceUpdate.

    Returns None if the payload is invalid.
    """
    try:
        if not isinstance(raw, dict):
            if logger:
                logger.warning("normalize.not_a_dict", raw_type=type(raw).__name__)
            return None

        last_val = raw.get("last")
        if last_val is None:
            if logger:
                logger.warning("normalize.missing_last", raw=raw)
            return None

        try:
            price = Decimal(str(last_val))
        except (InvalidOperation, TypeError):
            if logger:
                logger.warning("normalize.bad_price", last=last_val)
            return None

        if price <= 0:
            if logger:
                logger.warning("normalize.non_positive_price", price=str(price))
            return None

        # Extract ts_ms from 'ts_ms' field (milliseconds) or 'ts' field (seconds)
        ts_raw = raw.get("ts_ms") or raw.get("ts")
        if ts_raw is None:
            if logger:
                logger.warning("normalize.bad_timestamp", raw=raw)
            return None

        ts_ms: int
        try:
            ts_int = int(str(ts_raw))
            # Seconds (< year 2100 in ms would be ~4e12) → convert to ms
            ts_ms = ts_int * 1000 if ts_int < 1_000_000_000_000 else ts_int
        except (ValueError, TypeError):
            if logger:
                logger.warning("normalize.bad_timestamp_value", ts_raw=ts_raw)
            return None

        # Extract symbol from stream name
        stream = str(raw.get("stream", "market.ticker.thb_btc"))
        parts = stream.split(".")
        symbol = parts[-1].upper() if len(parts) >= 1 else "THB_BTC"

        return PriceUpdate(
            event_id=str(uuid.uuid4()),
            symbol=symbol,
            price=price,
            ts_ms=ts_ms,
            source="bitkub",
            version=1,
        )
    except Exception as exc:
        if logger:
            logger.error("normalize.internal_error", exc_info=exc)
        return None
