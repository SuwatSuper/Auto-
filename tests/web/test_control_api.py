# Layer 3 — Infrastructure (tests/web/test_control_api)
"""HTTP tests for the operator control-plane endpoints."""
from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


@pytest.fixture
async def client():
    runtime = PipelineRuntime(
        settings=Settings(persist_state=False, dashboard_api_key="k"),
        logger=structlog.get_logger("test"),
    )
    # Build agents (trader/treasury/breaker/risk gate) without starting the live feed.
    runtime.agents = runtime._make_agents()
    app = create_app(runtime)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    # Default the control token so dangerous (strict-auth) endpoints are authorized.
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-API-Key": "k"}
    ) as c:
        yield runtime, c


@pytest.mark.asyncio
async def test_get_risk_settings(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    r = await c.get("/api/risk/settings")
    assert r.status_code == 200
    assert "risk_per_trade_pct" in r.json()["settings"]


@pytest.mark.asyncio
async def test_post_risk_settings_applies(client) -> None:  # type: ignore[no-untyped-def]
    rt, c = client
    r = await c.post("/api/risk/settings", json={"risk_per_trade_pct": "2.5"})
    assert r.status_code == 200
    assert r.json()["settings"]["risk_per_trade_pct"] == "2.5"
    assert rt._trade_params.risk_per_trade_pct.__str__() == "2.5"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_post_risk_settings_invalid_returns_400(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    r = await c.post("/api/risk/settings", json={"risk_per_trade_pct": "9999"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_breaker_trip_then_reset(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    assert (await c.post("/api/breaker/trip", json={"reason": "test"})).json()["is_open"] is True
    bad = await c.post("/api/breaker/reset", json={"token": "nope"})
    assert bad.status_code == 400
    ok = await c.post("/api/breaker/reset", json={"token": "MANUAL_RESET_CONFIRMED"})
    assert ok.status_code == 200 and ok.json()["is_open"] is False


@pytest.mark.asyncio
async def test_execution_mode_switch_gated(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    # default paper
    assert (await c.get("/api/execution/mode")).json()["mode"] == "paper"
    # live without token -> 400
    assert (await c.post("/api/execution/mode", json={"mode": "live"})).status_code == 400
    # live with token but NO per-order cap -> 400 (real-money safety guard)
    assert (await c.post(
        "/api/execution/mode", json={"mode": "live", "confirm": "I_ACCEPT_REAL_MONEY_RISK"}
    )).status_code == 400
    # set a per-order cap first, then arming live succeeds
    assert (await c.post("/api/risk/settings", json={"max_single_order_thb": "10000"})).status_code == 200
    ok = await c.post(
        "/api/execution/mode", json={"mode": "live", "confirm": "I_ACCEPT_REAL_MONEY_RISK"}
    )
    assert ok.status_code == 200 and ok.json()["mode"] == "live"
    # back to paper
    assert (await c.post("/api/execution/mode", json={"mode": "paper"})).json()["mode"] == "paper"


@pytest.mark.asyncio
async def test_control_audit_lists_actions(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    await c.post("/api/breaker/trip", json={})
    r = await c.get("/api/control/audit")
    assert r.status_code == 200
    assert any(rec["action"] == "breaker_trip" for rec in r.json()["records"])


@pytest.mark.asyncio
async def test_control_requires_auth_when_key_set() -> None:
    runtime = PipelineRuntime(
        settings=Settings(persist_state=False, dashboard_api_key="secret123"),
        logger=structlog.get_logger("test"),
    )
    runtime.agents = runtime._make_agents()
    app = create_app(runtime)
    # Simulate a REMOTE client (non-loopback) so the API-key gate applies;
    # localhost requests are intentionally trusted and need no key.
    transport = ASGITransport(app=app, client=("203.0.113.7", 5555))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # no key -> 401
        assert (await c.post("/api/breaker/trip", json={})).status_code == 401
        # correct key -> ok
        r = await c.post("/api/breaker/trip", json={}, headers={"X-API-Key": "secret123"})
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_login_flow() -> None:
    runtime = PipelineRuntime(
        settings=Settings(
            persist_state=False, dashboard_api_key="thekey", dashboard_password="hunter2"
        ),
        logger=structlog.get_logger("test"),
    )
    runtime.agents = runtime._make_agents()
    app = create_app(runtime)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # wrong password -> 401
        assert (await c.post("/api/login", json={"password": "nope"})).status_code == 401
        # correct password -> returns the control token
        r = await c.post("/api/login", json={"password": "hunter2"})
        assert r.status_code == 200 and r.json()["token"] == "thekey"


@pytest.mark.asyncio
async def test_login_not_configured() -> None:
    runtime = PipelineRuntime(
        settings=Settings(persist_state=False), logger=structlog.get_logger("test")
    )
    runtime.agents = runtime._make_agents()
    app = create_app(runtime)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.post("/api/login", json={"password": "x"})).status_code == 400


@pytest.mark.asyncio
async def test_credentials_status_and_set(client, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt, c = client
    # initially no key
    s = await c.get("/api/credentials/status")
    assert s.status_code == 200 and s.json()["has_key"] is False
    # missing fields -> 400
    assert (await c.post("/api/credentials", json={"api_key": ""})).status_code == 400
    # set both -> connects (real gateway built; no poll triggered in this call path)
    r = await c.post("/api/credentials", json={"api_key": "pk", "api_secret": "sk"})
    assert r.status_code == 200
    assert r.json()["has_key"] is True
    assert "pk" not in r.text  # key never leaked
    await rt._disconnect_account()


@pytest.mark.asyncio
async def test_localhost_bypasses_api_key_even_when_set() -> None:
    # Key configured, but a LOCAL (loopback) request needs no key — this is the
    # single-user local control room: open localhost:8000 and it just works.
    runtime = PipelineRuntime(
        settings=Settings(persist_state=False, dashboard_api_key="secret123"),
        logger=structlog.get_logger("test"),
    )
    runtime.agents = runtime._make_agents()
    app = create_app(runtime)
    transport = ASGITransport(app=app)  # default client host = 127.0.0.1 (local)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # no X-API-Key header, yet allowed because it's localhost
        assert (await c.post("/api/breaker/trip", json={})).status_code == 200
        assert (await c.get("/api/risk/settings")).status_code == 200
