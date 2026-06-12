from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, field_validator


class Symbol(StrEnum):
    THB_BTC = "THB_BTC"


class Tick(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    symbol: Symbol
    price: Decimal
    ts_ms: int
    source: str
    version: int = 1

    @field_validator("price")
    @classmethod
    def _price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be positive")
        return v

    @field_validator("ts_ms")
    @classmethod
    def _ts_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ts_ms must be positive")
        return v


class PriceUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    event_id: str
    symbol: Symbol
    price: Decimal
    ts_ms: int
    source: str
    version: int = 1

    @classmethod
    def from_tick(cls, tick: Tick) -> PriceUpdate:
        return cls(
            event_id=uuid4().hex,
            symbol=tick.symbol,
            price=tick.price,
            ts_ms=tick.ts_ms,
            source=tick.source,
            version=tick.version,
        )
