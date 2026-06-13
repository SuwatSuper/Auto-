# Layer 3 — Infrastructure (gateway/bitkub_balance)
"""BitkubBalanceSource — reads wallet balance via BitkubRestGateway."""
from __future__ import annotations

from decimal import Decimal


class BitkubBalanceSource:
    """Adapter: fetches account balance from Bitkub REST API.

    Wraps BitkubRestGateway.get_wallet() and converts values to Decimal.
    Only non-zero balances are returned.
    """

    def __init__(self, gateway: object) -> None:
        self._gw = gateway  # BitkubRestGateway — typed as object to avoid circular import

    async def get_balance(self) -> dict[str, Decimal]:
        """Return symbol → Decimal balance for all non-zero wallet entries."""
        wallet: dict[str, object] = await self._gw.get_wallet()  # type: ignore[attr-defined]
        return {k: Decimal(str(v)) for k, v in wallet.items() if v}
