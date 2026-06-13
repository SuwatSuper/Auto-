# Layer 3 — Infrastructure (tests/infrastructure/test_bitkub_signing)
"""Golden test for Bitkub REST API v3 HMAC-SHA256 signing scheme."""
from __future__ import annotations

import hashlib
import hmac

from infrastructure.gateway.bitkub_rest import _sign


def test_golden_post_wallet_signing() -> None:
    """Golden test — computed once with hashlib and frozen as a literal.

    secret   = "test-secret"
    ts_ms    = 1700000000000
    method   = POST
    path     = /api/v3/market/wallet
    body     = {}
    message  = "1700000000000POST/api/v3/market/wallet{}"
    expected = HMAC-SHA256("test-secret", message).hexdigest()
    """
    _FROZEN_HEX = "b437098003f3e6892a21380ff8ed1296e14091e0110721e362362ef931c792bf"

    result = _sign(
        ts_ms=1700000000000,
        method="POST",
        path_and_payload="/api/v3/market/wallet{}",
        secret="test-secret",
    )
    assert result == _FROZEN_HEX


def test_signing_matches_stdlib_hmac() -> None:
    """Any signature from _sign must match the stdlib reference implementation."""
    ts_ms = 1699381086593
    method = "GET"
    path_and_payload = "/api/v3/market/my-order-history?sym=BTC_THB"
    secret = "my-api-secret"

    expected = hmac.new(
        secret.encode(),
        (str(ts_ms) + method + path_and_payload).encode(),
        hashlib.sha256,
    ).hexdigest()

    assert _sign(ts_ms, method, path_and_payload, secret) == expected


def test_different_secrets_produce_different_signatures() -> None:
    result_a = _sign(1700000000000, "POST", "/api/v3/market/wallet{}", "secret-a")
    result_b = _sign(1700000000000, "POST", "/api/v3/market/wallet{}", "secret-b")
    assert result_a != result_b


def test_different_timestamps_produce_different_signatures() -> None:
    result_a = _sign(1700000000000, "POST", "/api/v3/market/wallet{}", "secret")
    result_b = _sign(1700000000001, "POST", "/api/v3/market/wallet{}", "secret")
    assert result_a != result_b


def test_get_query_string_is_included() -> None:
    """GET signing includes the query string in the path_and_payload."""
    result_no_query = _sign(1700000000000, "GET", "/api/v3/market/order-info", "secret")
    result_with_query = _sign(
        1700000000000, "GET", "/api/v3/market/order-info?sym=THB_BTC&id=123", "secret"
    )
    assert result_no_query != result_with_query
