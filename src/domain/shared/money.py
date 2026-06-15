# Layer 1 — Domain (shared/money)
"""Money value object: currency-safe arithmetic with Decimal only."""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import BaseModel

THB = "THB"
BTC = "BTC"


def quantize_price(d: Decimal) -> Decimal:
    """Quantize to 2 decimal places, ROUND_HALF_EVEN."""
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def quantize_qty(d: Decimal) -> Decimal:
    """Quantize to 8 decimal places, ROUND_HALF_EVEN."""
    return d.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)


class CurrencyMismatchError(ValueError):
    """Raised when arithmetic is attempted across different currencies."""


class Money(BaseModel, frozen=True):
    """Immutable money value: amount + currency."""

    amount: Decimal
    currency: str

    def __add__(self, other: Money) -> Money:
        """Add two Money values of the same currency."""
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot add {self.currency} and {other.currency}"
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        """Subtract two Money values of the same currency."""
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot subtract {other.currency} from {self.currency}"
            )
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __neg__(self) -> Money:
        """Negate this Money value."""
        return Money(amount=-self.amount, currency=self.currency)

    def mul(self, scalar: Decimal) -> Money:
        """Multiply by a scalar Decimal."""
        return Money(amount=self.amount * scalar, currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        """Compare amounts in the same currency."""
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot compare {self.currency} and {other.currency}"
            )
        return self.amount >= other.amount
