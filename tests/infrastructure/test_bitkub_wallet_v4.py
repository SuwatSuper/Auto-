# Tests — H3: wallet balances are fetched via the v4 endpoint (the v3
# market/wallet was deprecated by Bitkub), adapted to the legacy shape, with a
# v3 fallback when v4 is unavailable.
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from infrastructure.gateway.bitkub_balance import BitkubBalanceSource
from infrastructure.gateway.bitkub_rest import BitkubRestGateway

_V4 = "/api/v4/wallet/balances"
_V3 = "/api/v3/market/wallet"


def _gw(handler: object) -> BitkubRestGateway:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return BitkubRestGateway(SecretStr("key"), SecretStr("secret"), client=client)


@pytest.mark.asyncio
async def test_get_wallet_uses_v4_and_adapts_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _V4 and request.method == "GET"
        assert request.headers.get("X-BTK-SIGN")  # signed
        return httpx.Response(200, json={
            "code": "0", "message": "success",
            "data": [
                {"currency": "THB", "available": "50000", "reserved": "10", "total": "50010"},
                {"currency": "BTC", "available": "0.002", "reserved": "0", "total": "0.002"},
            ],
        })

    wallet = await _gw(handler).get_wallet()
    # adapted to the legacy {"error":0,"result":{currency: available}} shape
    assert wallet == {"error": 0, "result": {"THB": "50000", "BTC": "0.002"}}
    # …and the balance source parses it into Decimals (available, not reserved)
    bal = await BitkubBalanceSource(_gw(handler)).get_balance()
    assert bal == {"THB": Decimal("50000"), "BTC": Decimal("0.002")}


@pytest.mark.asyncio
async def test_get_wallet_falls_back_to_v3_when_v4_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == _V4:
            return httpx.Response(404)  # v4 not available on this key
        assert request.url.path == _V3 and request.method == "POST"
        return httpx.Response(200, json={"error": 0, "result": {"THB": 1234.5, "BTC": 0}})

    wallet = await _gw(handler).get_wallet()
    assert wallet == {"error": 0, "result": {"THB": 1234.5, "BTC": 0}}
