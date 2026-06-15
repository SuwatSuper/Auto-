# Tests — wallet balance parsing (v3 result envelope) + error surfacing
from __future__ import annotations

from decimal import Decimal

import pytest

from infrastructure.gateway.bitkub_balance import BitkubBalanceSource


class _GwEnvelope:
    async def get_wallet(self):
        # Bitkub v3 shape: error code + result map
        return {"error": 0, "result": {"THB": 5000.5, "BTC": 0.002, "ETH": 0}}


class _GwFlat:
    async def get_wallet(self):
        return {"THB": 1000, "BTC": 0}


class _GwError:
    async def get_wallet(self):
        raise RuntimeError("Bitkub API error 3: Invalid API key")


@pytest.mark.asyncio
async def test_unwraps_v3_result_envelope_and_drops_zero() -> None:
    bal = await BitkubBalanceSource(_GwEnvelope()).get_balance()
    assert bal == {"THB": Decimal("5000.5"), "BTC": Decimal("0.002")}  # ETH (0) dropped
    assert "error" not in bal and "result" not in bal  # envelope keys never leak


@pytest.mark.asyncio
async def test_handles_flat_wallet_too() -> None:
    bal = await BitkubBalanceSource(_GwFlat()).get_balance()
    assert bal == {"THB": Decimal("1000")}


@pytest.mark.asyncio
async def test_error_propagates() -> None:
    with pytest.raises(RuntimeError):
        await BitkubBalanceSource(_GwError()).get_balance()
