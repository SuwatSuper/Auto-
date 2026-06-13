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
        """Return symbol -> Decimal balance for all non-zero wallet entries.

        Bitkub v3 /market/wallet wraps balances in a ``result`` object, e.g.
        ``{"error": 0, "result": {"THB": 1000, "BTC": 0.5}}``. We unwrap it,
        skip the envelope keys, and drop zero balances (comparing the parsed
        Decimal value — a raw "0" string is truthy and must not slip through).
        """
        payload: dict[str, object] = await self._gw.get_wallet()  # type: ignore[attr-defined]
        raw = payload.get("result", payload)
        if not isinstance(raw, dict):
            return {}
        out: dict[str, Decimal] = {}
        for symbol, value in raw.items():
            if symbol == "error":
                continue
            try:
                amount = Decimal(str(value))
            except (ValueError, ArithmeticError):
                continue
            if amount != 0:
                out[symbol] = amount
        return out
