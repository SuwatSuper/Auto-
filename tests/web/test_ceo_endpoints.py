# Layer 3 — Infrastructure (tests/web/test_ceo_endpoints)
"""HTTP tests for the CEO executive-reporting endpoints (real data only)."""
from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def _runtime(with_agents: bool) -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, dashboard_api_key=""),
        logger=structlog.get_logger("test"),
    )
    if with_agents:
        # Build agents (incl. CEO observer) without starting the live feed.
        rt.agents = rt._make_agents()
    return rt


@pytest.fixture
async def client_with_ceo():
    rt = _runtime(with_agents=True)
    transport = ASGITransport(app=create_app(rt))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield rt, c


@pytest.mark.asyncio
async def test_ceo_summary_returns_real_executive_view(client_with_ceo) -> None:  # type: ignore[no-untyped-def]
    _, c = client_with_ceo
    r = await c.get("/api/ceo/summary")
    assert r.status_code == 200
    body = r.json()
    assert {"ts_ms", "agents", "business", "risk", "health"} <= set(body)
    assert isinstance(body["agents"], list) and body["agents"]
    # serializer maps enums to their plain string values
    assert isinstance(body["risk"]["risk_level"], str) and body["risk"]["risk_level"]
    assert body["business"]["cash_availability"] in {"AVAILABLE", "UNAVAILABLE"}


@pytest.mark.asyncio
async def test_ceo_audit_and_agents_endpoints(client_with_ceo) -> None:  # type: ignore[no-untyped-def]
    _, c = client_with_ceo
    r = await c.get("/api/ceo/audit", params={"limit": 5})
    assert r.status_code == 200
    audit = r.json()
    assert {"total_count", "by_agent", "by_outcome", "records"} <= set(audit)

    r2 = await c.get("/api/ceo/audit", params={"agent": "ceo", "action": "BUY"})
    assert r2.status_code == 200  # filter branch

    r3 = await c.get("/api/ceo/agents")
    assert r3.status_code == 200
    assert isinstance(r3.json()["agents"], list)


@pytest.mark.asyncio
async def test_ceo_endpoints_503_when_not_started() -> None:
    rt = _runtime(with_agents=False)  # no CEO agent built yet
    transport = ASGITransport(app=create_app(rt))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for path in ("/api/ceo/summary", "/api/ceo/audit", "/api/ceo/agents"):
            r = await c.get(path)
            assert r.status_code == 503, path
