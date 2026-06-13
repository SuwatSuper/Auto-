# Layer 1 — Domain (analytics/market_mode)
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class MarketMode(StrEnum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    BREAKOUT = "BREAKOUT"
    UNKNOWN = "UNKNOWN"


def detect_market_mode(
    short_ema: Decimal,
    long_ema: Decimal,
    atr: Decimal,
    price: Decimal,
) -> MarketMode:
    if atr == Decimal("0") or price == Decimal("0"):
        return MarketMode.UNKNOWN
    spread = abs(short_ema - long_ema) / price
    if spread < Decimal("0.005"):
        return MarketMode.RANGING
    if short_ema > long_ema:
        return MarketMode.TRENDING_UP
    return MarketMode.TRENDING_DOWN
