# Layer 1 — Domain (strategy/base)
"""Strategy protocol and signal model."""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class SignalAction(StrEnum):
    """Trading signal actions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Signal(BaseModel, frozen=True):
    """A trading signal produced by a strategy."""

    action: SignalAction
    confidence: Decimal
    reason: str


class StrategyContext(BaseModel, frozen=True):
    """Context passed to a strategy for decision-making."""

    prices: tuple[Decimal, ...]
    position_qty: Decimal


class Strategy(Protocol):
    """Strategy protocol: stateless, pure decision function."""

    def decide(self, ctx: StrategyContext) -> Signal:
        """Return a trading signal for the given context."""
        ...
