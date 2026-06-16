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


# ── control key: loopback auto-provision, non-loopback fail-closed ───
def test_control_key_uses_explicit_when_set() -> None:
    assert _runtime(dashboard_api_key="explicit").control_key() == "explicit"


def test_control_key_not_autoprovisioned_for_non_loopback() -> None:
    # A network bind must NEVER auto-open the control plane — only an explicit
    # key (enforced separately by assert_safe_bind) is accepted.
    assert _runtime(web_host="0.0.0.0", dashboard_api_key="").control_key() == ""


def test_password_only_network_bind_mints_key_but_does_not_expose_it() -> None:
    # A password-protected network bind must mint a usable control key (so
    # /api/login can return a token and the gates have a real secret), but it must
    # NOT be injected into the served page — the operator logs in to obtain it.
    rt = _runtime(web_host="0.0.0.0", dashboard_api_key="", dashboard_password="pw")
    assert rt.control_key()                 # a real key is minted
    assert rt.page_control_key() == ""      # but never pre-exposed in the page


# ── localhost trusted for ALL control; remote still strict ───────────
@pytest.mark.asyncio
async def test_local_dashboard_control_needs_no_key() -> None:
    """The loopback dashboard is a single-user control room: every control —
    including arming live — works from this machine with NO key and NO .env
    editing. An explicit key, when present, authorizes the same action too."""
    rt = _runtime(dashboard_api_key="")  # loopback bind, no explicit key
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt))  # localhost client
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # No header, no configured key → trusted from localhost (NOT 401).
        assert (await c.post("/api/execution/mode", json={"mode": "paper"})).status_code != 401
        key = rt.control_key()
        assert key  # a per-process key is still minted (used for remote/login)
        ok = await c.post(
            "/api/execution/mode", json={"mode": "paper"}, headers={"X-API-Key": key}
        )
        assert ok.status_code != 401


@pytest.mark.asyncio
async def test_dangerous_endpoint_localhost_trusted() -> None:
    """Money endpoints are reachable from localhost without a token (the
    operator's own machine). Arming live still needs the typed confirm string,
    and orders still pass the hard per-order cap / kill switch / treasury."""
    rt = _runtime(dashboard_api_key="secret")
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt))  # default localhost client
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # localhost, NO header → reaches the handler (not a 401).
        assert (await c.post("/api/order", json={"side": "BUY"})).status_code != 401
        # an explicit token works too.
        ok = await c.post(
            "/api/order", json={"side": "BUY"}, headers={"X-API-Key": "secret"}
        )
        assert ok.status_code != 401


@pytest.mark.asyncio
async def test_dangerous_endpoint_remote_requires_token() -> None:
    """A remote/LAN client must still present the key for money endpoints — the
    control plane is never open over the network."""
    rt = _runtime(dashboard_api_key="secret")
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt), client=("203.0.113.7", 5555))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.post("/api/order", json={"side": "BUY"})).status_code == 401
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


@pytest.mark.asyncio
async def test_connect_account_is_localhost_trusted(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Connecting the Bitkub account is localhost-trusted: on the operator's own
    machine you paste key/secret and connect with NO DASHBOARD_API_KEY — the
    'ใส่หน้าเว็บทีเดียว กรอก เชื่อม' flow. Setting credentials never moves money."""
    monkeypatch.chdir(tmp_path)  # connect_account persists to ./.env — isolate it
    rt = _runtime(dashboard_api_key="")  # loopback, no explicit key
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt))  # localhost client
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/credentials", json={"api_key": "pk", "api_secret": "sk"})
        assert r.status_code == 200, "localhost connect must work without a control key"
        assert r.json()["has_key"] is True
        assert "pk" not in r.text  # the key is never echoed back
    await rt._disconnect_account()


@pytest.mark.asyncio
async def test_connect_account_remote_still_requires_key(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A network bind must NOT open the credential endpoint: a remote client with
    no/invalid token is rejected, so the control plane stays closed over the LAN."""
    monkeypatch.chdir(tmp_path)
    rt = _runtime(dashboard_api_key="secret")
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt), client=("203.0.113.7", 5555))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert (
            await c.post("/api/credentials", json={"api_key": "pk", "api_secret": "sk"})
        ).status_code == 401
        ok = await c.post(
            "/api/credentials",
            json={"api_key": "pk", "api_secret": "sk"},
            headers={"X-API-Key": "secret"},
        )
        assert ok.status_code != 401
    await rt._disconnect_account()
