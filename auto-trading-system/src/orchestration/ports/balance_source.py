# Layer 2 — Orchestration (ports/balance_source)
"""BalanceSource port: abstract interface for reading account balances."""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class BalanceSource(Protocol):
    """Port for fetching current account balances (symbol → quantity)."""

    async def get_balance(self) -> dict[str, Decimal]:
        """Return a mapping of currency/symbol to held quantity."""
        ...


class NullBalanceSource:
    """Paper-mode stub: immediately returns an empty balance (always reconciled)."""

    async def get_balance(self) -> dict[str, Decimal]:
        return {}
