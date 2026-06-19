# Layer 3 — Infrastructure (tests/web/test_health)
"""Regression test: GET /api/health must work against the REAL runtime.

PipelineRuntime.status() returns "agents" as a LIST of per-agent dicts
(see PipelineRuntime._agent_status). A previous version of the /api/health
handler assumed a dict and crashed with AttributeError ('list' has no
attribute 'items') on every real boot while over-mocked tests stayed green.
This test uses the real runtime so that shape mismatch can never return.
"""
from __future__ import annotations

import pytest
import structlog
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed


def _make_runtime() -> PipelineRuntime:
    settings = Settings(
        persist_state=False,
        initial_capital="1000",
        prices_topic="prices.thb_btc.v1",
        dashboard_api_key=SecretStr(""),
    )
    logger = structlog.get_logger("test")
    bus = InMemoryEventBus()
    deps = RuntimeDeps(
        bus=bus,
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    return PipelineRuntime(settings, logger, deps=deps)


@pytest.mark.asyncio
async def test_api_health_real_runtime_status_shape() -> None:
    """/api/health returns 200 with the documented schema using the real
    runtime.status() output (agents as a list)."""
    runtime = _make_runtime()
    app = create_app(runtime)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            for key in (
                "status",
                "ts_ms",
                "uptime_seconds",
                "agent_count",
                "running_agents",
                "stale_agents",
                "feed_connected",
                "emergency_stopped",
            ):
                assert key in body, f"missing key: {key}"
            assert body["status"] == "ok"
            assert isinstance(body["stale_agents"], list)
            assert isinstance(body["agent_count"], int)
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_api_health_tolerates_dict_shaped_agents(monkeypatch) -> None:
    """Defensive path: if status() ever reports agents as a dict, the
    endpoint must still respond 200 with consistent counts."""
    runtime = _make_runtime()

    def _dict_status() -> dict[str, object]:
        return {
            "uptime_seconds": 1,
            "emergency_stopped": False,
            "health": {"feed_connected": False},
            "agents": {
                "alpha": {"running": True, "stale": False},
                "beta": {"running": False, "stale": True},
            },
        }

    monkeypatch.setattr(runtime, "status", _dict_status)
    app = create_app(runtime)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["agent_count"] == 2
            assert body["running_agents"] == 1
            assert body["stale_agents"] == ["beta"]
    finally:
        await runtime.stop()
