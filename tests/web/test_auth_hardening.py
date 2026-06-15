# Layer 3 — Infrastructure (tests/web/test_auth_hardening)
"""T1: auth fail-closed + strict token for dangerous endpoints (D3 = strict)."""
from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web._helpers import assert_safe_bind
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def _runtime(**kw: object) -> PipelineRuntime:
    return PipelineRuntime(
        settings=Settings(persist_state=False, **kw),  # type: ignore[arg-type]
        logger=structlog.get_logger("test"),
    )


# ── fail-closed bind guard ───────────────────────────────────────────
def test_assert_safe_bind_refuses_remote_without_credential() -> None:
    with pytest.raises(RuntimeError, match="non-loopback"):
        assert_safe_bind(Settings(web_host="0.0.0.0"))


def test_assert_safe_bind_allows_loopback_without_credential() -> None:
    assert_safe_bind(Settings(web_host="127.0.0.1"))  # no raise


def test_assert_safe_bind_allows_remote_with_key() -> None:
    assert_safe_bind(Settings(web_host="0.0.0.0", dashboard_api_key="secret"))  # no raise


def test_assert_safe_bind_allows_remote_with_password() -> None:
    assert_safe_bind(Settings(web_host="0.0.0.0", dashboard_password="pw"))  # no raise


def test_create_app_refuses_unsafe_bind() -> None:
    rt = _runtime(web_host="0.0.0.0")  # remote bind, no credential
    with pytest.raises(RuntimeError, match="refusing to bind"):
        create_app(rt)


# ── strict auth for dangerous endpoints (even on localhost) ──────────
@pytest.mark.asyncio
async def test_dangerous_endpoint_locked_when_no_key_configured() -> None:
    rt = _runtime(dashboard_api_key="")  # loopback bind ok, but no control key
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt))  # localhost client
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # No token configured at all → dangerous endpoint is locked (fail-closed),
        # even from localhost.
        r = await c.post("/api/execution/mode", json={"mode": "paper"})
        assert r.status_code == 401
        assert "locked" in r.text


@pytest.mark.asyncio
async def test_dangerous_endpoint_requires_token_even_on_localhost() -> None:
    rt = _runtime(dashboard_api_key="secret")
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt))  # default localhost client
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # localhost, but NO header → still 401 (D3 strict: no loopback bypass).
        assert (await c.post("/api/order", json={"side": "BUY"})).status_code == 401
        # correct token → passes auth (reaches the handler, not a 401).
        ok = await c.post(
            "/api/order", json={"side": "BUY"}, headers={"X-API-Key": "secret"}
        )
        assert ok.status_code != 401


@pytest.mark.asyncio
async def test_nondangerous_endpoint_still_localhost_trusted() -> None:
    rt = _runtime(dashboard_api_key="secret")
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt))  # localhost
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Ordinary control endpoint (breaker) is still trusted from localhost.
        assert (await c.post("/api/breaker/trip", json={})).status_code == 200


@pytest.mark.asyncio
async def test_dangerous_endpoint_remote_with_token_ok() -> None:
    rt = _runtime(dashboard_api_key="secret")
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt), client=("203.0.113.7", 5555))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # remote + wrong/no token → 401
        assert (await c.post("/api/positions/close_all")).status_code == 401
        # remote + correct token → reaches handler
        r = await c.post("/api/positions/close_all", headers={"X-API-Key": "secret"})
        assert r.status_code != 401
