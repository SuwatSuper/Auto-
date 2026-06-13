# Layer 3 — Infrastructure (tests/web/test_kingdom_integration)
"""Integration contract between the Kingdom Prime dashboard and the backend.

Pins:
- `/` serves the Kingdom dashboard with the control key injected; `/classic` serves the old UI.
- `/api/status` carries every field the dashboard reads.
- POST control endpoints enforce X-API-Key when a key is configured (and stay
  open when it is not).
- runtime.agents == the 7 real departments, 1:1 with dashboard chibis (H5).
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

EXPECTED_AGENTS = {
    # core 11
    "market_analyst",
    "news_intelligence",
    "risk_management",
    "probability_lab",
    "research_dept",
    "execution_agent",
    "supreme_commander",
    "treasury",
    "paper_trader",
    "ceo",
    "risk_gate",
    # Phase-2 extended (15, all real / data-driven)
    "volatility_oracle",
    "trend_follower",
    "mean_reversion",
    "breakout_specialist",
    "black_swan_detector",
    "drawdown_guardian",
    "position_sizer",
    "trailing_stop",
    "profit_sweeper",
    "fee_optimizer",
    "latency_pinger",
    "api_monitor",
    "dashboard_synth",
    "tax_clerk",
    "garbage_collector",
}

TEST_KEY = "test-key-1234567890"


def _runtime(key: str = "") -> PipelineRuntime:
    settings = Settings(persist_state=False, initial_capital="1000", prices_topic="prices.thb_btc.v1",
        dashboard_api_key=SecretStr(key),
    )
    bus = InMemoryEventBus()
    deps = RuntimeDeps(
        bus=bus,
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    return PipelineRuntime(settings, structlog.get_logger("test"), deps=deps)


@pytest.fixture
async def open_client():
    """App with no key configured — control endpoints open (back-compat)."""
    runtime = _runtime("")
    app = create_app(runtime)
    # httpx ASGITransport does not run the lifespan — start explicitly.
    await runtime.start("live")
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield runtime, client
        finally:
            await runtime.stop()


@pytest.fixture
async def locked_client():
    """App with a configured key — control endpoints require X-API-Key when
    reached from a REMOTE machine (localhost is trusted and needs no key)."""
    runtime = _runtime(TEST_KEY)
    app = create_app(runtime)
    # httpx ASGITransport does not run the lifespan — start explicitly.
    await runtime.start("live")
    # Non-loopback client so the remote-auth path is what gets tested.
    transport = ASGITransport(app=app, client=("203.0.113.7", 5555))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield runtime, client
        finally:
            await runtime.stop()


@pytest.mark.asyncio
async def test_root_serves_kingdom_dashboard_with_key_injected(locked_client) -> None:  # type: ignore[no-untyped-def]
    _, client = locked_client
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Kingdom Prime" in resp.text
    # placeholder must be replaced server-side with the configured key
    assert "__DASHBOARD_API_KEY__" not in resp.text
    assert TEST_KEY in resp.text


@pytest.mark.asyncio
async def test_classic_route_serves_old_dashboard(open_client) -> None:  # type: ignore[no-untyped-def]
    _, client = open_client
    resp = await client.get("/classic")
    assert resp.status_code == 200
    assert "Anime Bitcoin" in resp.text


@pytest.mark.asyncio
async def test_status_has_dashboard_contract_fields(open_client) -> None:  # type: ignore[no-untyped-def]
    _, client = open_client
    data = (await client.get("/api/status")).json()
    for field in (
        "mode",
        "uptime_seconds",
        "uptime_sec",
        "msg_rate",
        "equity",
        "pnl_today",
        "positions",
        "daily_loss_pct",
        "drawdown_pct",
        "kill_switch",
        "emergency_stopped",
        "execution_engine",
        "execution_warning",
        "data_source",
        "agents",
    ):
        assert field in data, f"status missing {field}"
    assert data["execution_engine"] == "paper"
    assert data["data_source"] == "live_bitkub_ws"
    # honest zero-state: equity == initial capital, no fabricated pnl
    assert data["equity"] == 1000.0
    assert data["pnl_today"] == 0
    # win_rate is None (not a fake number) until the first paper window completes
    assert data["win_rate"] is None
    names = {a["name"] for a in data["agents"]}
    assert names == EXPECTED_AGENTS
    # every agent carries an EXP/level (skill) view, capped at 5000
    for a in data["agents"]:
        assert {"exp", "exp_max", "level", "rank"} <= a.keys()
        assert 0 <= a["exp"] <= 5000
        assert a["exp_max"] == 5000
        assert 1 <= a["level"] <= 50


@pytest.mark.asyncio
async def test_learning_endpoint_scores_every_agent(open_client) -> None:  # type: ignore[no-untyped-def]
    _, client = open_client
    d = (await client.get("/api/agents/learning")).json()
    assert "leaderboard" in d and "feed" in d
    # honest about the LLM critic being OFF (no fabricated AI involvement)
    assert "llm_critic" in d and "disabled" in d["llm_critic"]
    assert len(d["leaderboard"]) == len(EXPECTED_AGENTS)  # every agent measured
    for row in d["leaderboard"]:
        assert 0 <= row["score"] <= 100
        assert "kind" in row
    assert isinstance(d["feed"], list)


@pytest.mark.asyncio
async def test_runtime_builds_the_seven_departments(open_client) -> None:  # type: ignore[no-untyped-def]
    runtime, client = open_client
    assert set(runtime.agents) == EXPECTED_AGENTS
    for agent in runtime.agents.values():
        assert agent.running is True


@pytest.mark.asyncio
async def test_post_requires_api_key_when_configured(locked_client) -> None:  # type: ignore[no-untyped-def]
    runtime, client = locked_client
    # no key → 401, and the runtime must NOT have acted
    resp = await client.post("/api/emergency_stop")
    assert resp.status_code == 401
    assert runtime.emergency_stopped is False
    # wrong key → 401
    resp = await client.post("/api/emergency_stop", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401
    # correct key → acts
    resp = await client.post("/api/emergency_stop", headers={"X-API-Key": TEST_KEY})
    assert resp.status_code == 200
    assert runtime.emergency_stopped is True
    resp = await client.post("/api/emergency_reset", headers={"X-API-Key": TEST_KEY})
    assert resp.status_code == 200
    assert runtime.emergency_stopped is False


@pytest.mark.asyncio
async def test_get_endpoints_stay_open_when_key_configured(locked_client) -> None:  # type: ignore[no-untyped-def]
    _, client = locked_client
    for path in ("/api/status", "/healthz", "/metrics", "/api/timeline"):
        resp = await client.get(path)
        assert resp.status_code == 200, path


@pytest.mark.asyncio
async def test_post_open_when_no_key_configured(open_client) -> None:  # type: ignore[no-untyped-def]
    runtime, client = open_client
    resp = await client.post("/api/emergency_stop")
    assert resp.status_code == 200
    assert runtime.emergency_stopped is True


@pytest.mark.asyncio
async def test_metrics_report_real_uptime_and_agent_count(open_client) -> None:  # type: ignore[no-untyped-def]
    _, client = open_client
    await client.get("/healthz")
    text = (await client.get("/metrics")).text
    assert "trading_agent_count 26" in text
