from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


@pytest.fixture
def settings() -> Settings:
    return Settings(
        bitkub_ws_url="wss://api.bitkub.com/websocket-api/market.ticker.thb_btc",
        log_level="INFO",
        prices_topic="prices.thb_btc.v1",
        web_host="127.0.0.1",
        web_port=8000,
    )


@pytest.fixture
def runtime(settings: Settings) -> PipelineRuntime:
    log = structlog.get_logger("test")
    return PipelineRuntime(settings, log)


@pytest.fixture
async def client(runtime: PipelineRuntime) -> AsyncClient:
    app = create_app(runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


async def test_index_returns_html(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Trading Platform" in resp.text


async def test_status_returns_expected_keys(client: AsyncClient) -> None:
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "mode",
        "uptime_sec",
        "msg_per_sec",
        "latency_ms",
        "latest_price",
        "emergency_stopped",
        "agents",
    ):
        assert key in data
    assert len(data["agents"]) == 3


async def test_invalid_mode_returns_400(client: AsyncClient) -> None:
    resp = await client.post("/api/mode/invalid")
    assert resp.status_code == 400


async def test_start_agent_returns_ok(client: AsyncClient, runtime: PipelineRuntime) -> None:
    resp = await client.post("/api/agents/agent_1/start")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_emergency_stop_stops_all_agents(
    client: AsyncClient, runtime: PipelineRuntime
) -> None:
    resp = await client.post("/api/emergency_stop")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    status_resp = await client.get("/api/status")
    status = status_resp.json()
    assert status["emergency_stopped"] is True
    for agent in status["agents"]:
        assert agent["running"] is False
