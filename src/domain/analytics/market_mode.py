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
    atr_pct = atr / price
    if spread < Decimal("0.005"):
        return MarketMode.RANGING
    # BREAKOUT: a strong directional move WITH a volatility expansion — a wide
    # EMA spread AND elevated ATR relative to price. This branch was previously
    # unreachable, leaving the BREAKOUT regime playbook dead code (L4).
    if spread >= Decimal("0.02") and atr_pct >= Decimal("0.02"):
        return MarketMode.BREAKOUT
    if short_ema > long_ema:
        return MarketMode.TRENDING_UP
    return MarketMode.TRENDING_DOWN
