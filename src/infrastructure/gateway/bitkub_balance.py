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
        """Return symbol → Decimal balance for all non-zero wallet entries.

        Bitkub v3 /market/wallet returns {"error":0,"result":{"THB":..,"BTC":..}}.
        We unwrap the ``result`` envelope (when present) before converting, and
        skip any non-numeric / nested values defensively.
        """
        raw: dict[str, object] = await self._gw.get_wallet()  # type: ignore[attr-defined]
        wallet = raw.get("result", raw) if isinstance(raw, dict) else raw
        if not isinstance(wallet, dict):
            return {}
        out: dict[str, Decimal] = {}
        for sym, val in wallet.items():
            if isinstance(val, dict):
                continue
            try:
                amount = Decimal(str(val))
            except (ArithmeticError, ValueError, TypeError):
                continue
            if amount != 0:
                out[str(sym)] = amount
        return out
