# Layer 3 — Infrastructure (gateway/bitkub_rest)
"""Bitkub REST API v3 gateway — the ONLY file allowed to contain order-placement endpoints.

Signing: HMAC-SHA256 over str(ts_ms) + METHOD + path_and_payload.
- GET: path_and_payload = path + "?" + query_string (empty query → path only)
- POST: path_and_payload = path + raw_json_body

Headers: X-BTK-APIKEY, X-BTK-TIMESTAMP, X-BTK-SIGN, Content-Type: application/json.
No automatic retry on signed POSTs (no silent order re-submission).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import SecretStr

_TIMEOUT = 10.0
_BASE = "https://api.bitkub.com"


class BitkubApiError(Exception):
    """Raised when the Bitkub API returns a non-zero error code."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Bitkub API error {code}: {message}")


def _sign(ts_ms: int, method: str, path_and_payload: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature per Bitkub API v3 specification.

    Isolated here so the signing scheme can be corrected in a single place.
    """
    message = str(ts_ms) + method + path_and_payload
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class BitkubRestGateway:
    """Thin async wrapper around the Bitkub REST API v3.

    api_key / api_secret are stored as SecretStr — never logged or printed.
    client is injected for testing; if None, a new httpx.AsyncClient is created.
    clock is injected for deterministic timestamp generation in tests.
    """

    def __init__(
        self,
        api_key: SecretStr,
        api_secret: SecretStr,
        base_url: str = _BASE,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._clock: Callable[[], int] = clock if clock is not None else self._default_clock
        self._owns_client = client is None

    @staticmethod
    def _default_clock() -> int:
        return int(time.time() * 1000)

    def _ts(self) -> int:
        return self._clock()

    def _signed_headers(self, ts_ms: int, method: str, path_and_payload: str) -> dict[str, str]:
        secret = self._api_secret.get_secret_value()
        signature = _sign(ts_ms, method, path_and_payload, secret)
        return {
            "X-BTK-APIKEY": self._api_key.get_secret_value(),
            "X-BTK-TIMESTAMP": str(ts_ms),
            "X-BTK-SIGN": signature,
            "Content-Type": "application/json",
        }

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("No httpx.AsyncClient available — use as async context manager")
        return self._client

    async def __aenter__(self) -> BitkubRestGateway:
        if self._owns_client:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _check(data: dict[str, Any]) -> dict[str, Any]:
        """Raise BitkubApiError on non-zero error code."""
        error_code = data.get("error", 0)
        if error_code:
            msg = data.get("message", str(error_code))
            raise BitkubApiError(int(error_code), str(msg))
        return data

    # ── Public (unsigned) endpoints ───────────────────────────────────

    async def get_server_time(self) -> int:
        """GET /api/v3/servertime → server timestamp in milliseconds."""
        client = self._client_or_raise()
        resp = await client.get(f"{self._base_url}/api/v3/servertime")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return int(data.get("ts", data))

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """GET /api/v3/market/ticker?sym=<SYMBOL> → ticker dict."""
        client = self._client_or_raise()
        resp = await client.get(
            f"{self._base_url}/api/v3/market/ticker",
            params={"sym": symbol},
        )
        resp.raise_for_status()
        return self._check(resp.json())

    # ── Signed endpoints ──────────────────────────────────────────────

    async def get_wallet(self) -> dict[str, Any]:
        """POST /api/v3/market/wallet → available balances."""
        path = "/api/v3/market/wallet"
        body = "{}"
        ts_ms = self._ts()
        headers = self._signed_headers(ts_ms, "POST", path + body)
        client = self._client_or_raise()
        resp = await client.post(
            f"{self._base_url}{path}",
            content=body,
            headers=headers,
        )
        resp.raise_for_status()
        return self._check(resp.json())

    async def place_bid(self, symbol: str, amount_thb: str, rate: str) -> dict[str, Any]:
        """POST /api/v3/market/place-bid — buy order (spend THB, receive coin).

        symbol uses lowercase convention per Bitkub POST body docs (e.g. 'thb_btc').
        amount_thb: THB amount to spend; rate: limit price.
        """
        path = "/api/v3/market/place-bid"
        body_dict = {"sym": symbol, "amt": amount_thb, "rat": rate, "typ": "limit"}
        body = json.dumps(body_dict, separators=(",", ":"))
        ts_ms = self._ts()
        headers = self._signed_headers(ts_ms, "POST", path + body)
        client = self._client_or_raise()
        resp = await client.post(
            f"{self._base_url}{path}",
            content=body,
            headers=headers,
        )
        resp.raise_for_status()
        return self._check(resp.json())

    async def place_ask(self, symbol: str, amount_coin: str, rate: str) -> dict[str, Any]:
        """POST /api/v3/market/place-ask — sell order (spend coin, receive THB).

        symbol uses lowercase convention per Bitkub POST body docs (e.g. 'thb_btc').
        amount_coin: coin quantity to sell; rate: limit price.
        """
        path = "/api/v3/market/place-ask"
        body_dict = {"sym": symbol, "amt": amount_coin, "rat": rate, "typ": "limit"}
        body = json.dumps(body_dict, separators=(",", ":"))
        ts_ms = self._ts()
        headers = self._signed_headers(ts_ms, "POST", path + body)
        client = self._client_or_raise()
        resp = await client.post(
            f"{self._base_url}{path}",
            content=body,
            headers=headers,
        )
        resp.raise_for_status()
        return self._check(resp.json())

    async def cancel_order(self, symbol: str, order_id: int, side: str) -> dict[str, Any]:
        """POST /api/v3/market/cancel-order."""
        path = "/api/v3/market/cancel-order"
        body_dict = {"sym": symbol, "id": order_id, "sd": side}
        body = json.dumps(body_dict, separators=(",", ":"))
        ts_ms = self._ts()
        headers = self._signed_headers(ts_ms, "POST", path + body)
        client = self._client_or_raise()
        resp = await client.post(
            f"{self._base_url}{path}",
            content=body,
            headers=headers,
        )
        resp.raise_for_status()
        return self._check(resp.json())

    async def order_info(self, symbol: str, order_id: int, side: str) -> dict[str, Any]:
        """GET /api/v3/market/order-info?sym=<SYM>&id=<ID>&sd=<SIDE>."""
        path = "/api/v3/market/order-info"
        query = f"sym={symbol}&id={order_id}&sd={side}"
        ts_ms = self._ts()
        headers = self._signed_headers(ts_ms, "GET", f"{path}?{query}")
        client = self._client_or_raise()
        resp = await client.get(
            f"{self._base_url}{path}",
            params={"sym": symbol, "id": order_id, "sd": side},
            headers=headers,
        )
        resp.raise_for_status()
        return self._check(resp.json())
