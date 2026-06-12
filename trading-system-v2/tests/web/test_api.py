# Layer 3 — Infrastructure (tests/web/test_api)
"""API endpoint tests including B4 (task leak) and B2 (emergency reset)."""
from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def _make_runtime() -> PipelineRuntime:
    settings = Settings(prices_topic="prices.thb_btc.v1")
    logger = structlog.get_logger("test")
    return PipelineRuntime(settings, logger)


@pytest.fixture
async def runtime_client():
    """B4 fix: fixture awaits runtime.stop() in teardown to prevent task leaks."""
    runtime = _make_runtime()
    app = create_app(runtime)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield runtime, client
        finally:
            await runtime.stop()


@pytest.mark.asyncio
async def test_status_endpoint(runtime_client) -> None:  # type: ignore[no-untyped-def]
    runtime, client = runtime_client
    response = await client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "mode" in data
    assert "emergency_stopped" in data


@pytest.mark.asyncio
async def test_emergency_stop_and_reset(runtime_client) -> None:  # type: ignore[no-untyped-def]
    """B2: stop → reset → start_all should work; status must reflect each state."""
    runtime, client = runtime_client

    # Emergency stop
    resp = await client.post("/api/emergency_stop")
    assert resp.status_code == 200
    assert runtime.emergency_stopped is True

    status = (await client.get("/api/status")).json()
    assert status["emergency_stopped"] is True

    # Reset
    resp = await client.post("/api/emergency_reset")
    assert resp.status_code == 200
    assert runtime.emergency_stopped is False

    status = (await client.get("/api/status")).json()
    assert status["emergency_stopped"] is False

    # Start all agents after reset
    resp = await client.post("/api/agents/start_all")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_mode_switch(runtime_client) -> None:  # type: ignore[no-untyped-def]
    _, client = runtime_client
    resp = await client.post("/api/mode/simulator")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "simulator"


@pytest.mark.asyncio
async def test_mode_switch_invalid(runtime_client) -> None:  # type: ignore[no-untyped-def]
    _, client = runtime_client
    resp = await client.post("/api/mode/invalid")
    assert resp.status_code == 400
