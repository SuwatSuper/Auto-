# Layer 3 — Infrastructure (tests/web/test_control_endpoints_extra)
"""Coverage for the remaining operator control endpoints: agent lifecycle,
emergency stop/reset, manual order/position validation, alerts, and the
invalid-body error branches."""
from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


@pytest.fixture
async def client():
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, dashboard_api_key=""),
        logger=structlog.get_logger("test"),
    )
    rt.agents = rt._make_agents()
    transport = ASGITransport(app=create_app(rt))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield rt, c


@pytest.mark.asyncio
async def test_mode_endpoint_live_ok_other_rejected(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    assert (await c.post("/api/mode/live")).json()["mode"] == "live"
    r = await c.post("/api/mode/simulator")
    assert r.status_code == 400  # only 'live' supported post-migration


@pytest.mark.asyncio
async def test_single_agent_start_stop(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    assert (await c.post("/api/agents/garbage_collector/start")).json()["ok"] is True
    assert (await c.post("/api/agents/garbage_collector/stop")).json()["ok"] is True


@pytest.mark.asyncio
async def test_emergency_stop_then_reset(client) -> None:  # type: ignore[no-untyped-def]
    rt, c = client
    assert (await c.post("/api/emergency_stop")).json()["ok"] is True
    assert rt.emergency_stopped is True
    assert (await c.post("/api/emergency_reset")).json()["ok"] is True
    assert rt.emergency_stopped is False


@pytest.mark.asyncio
async def test_alerts_test_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    r = await c.post("/api/alerts/test")
    assert r.status_code == 200
    assert "delivered" in r.json()


@pytest.mark.asyncio
async def test_order_and_positions_validation(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    # Missing 'side' → 400.
    assert (await c.post("/api/order", json={})).status_code == 400
    # CLOSE with no open position → handled (ok/false), never a 500.
    assert (await c.post("/api/positions/close", json={})).status_code in (200, 400)
    # close_all returns a JSON object.
    r = await c.post("/api/positions/close_all")
    assert r.status_code == 200 and isinstance(r.json(), dict)


@pytest.mark.asyncio
async def test_invalid_json_body_returns_400(client) -> None:  # type: ignore[no-untyped-def]
    _, c = client
    r = await c.post(
        "/api/risk/settings",
        content="not-json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    # A JSON array (not an object) is also rejected.
    r2 = await c.post("/api/execution/mode", json=[1, 2, 3])
    assert r2.status_code == 400
