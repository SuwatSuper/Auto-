# Layer 3 — Infrastructure (tests/web/test_status_confluence)
"""End-to-end: the REAL FastAPI app + REAL started runtime expose the bus-fed
confluence and the dynamic-weighting feedback over /api/status.

Boots the full pipeline (181 agents) behind the ASGI app, drives the Event Bus,
and asserts the operator can actually see Task-1 (confluence) and Task-2
(dynamic weighting) state in the served status payload.
"""
from __future__ import annotations

import asyncio

import orjson
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


def _make_runtime() -> tuple[PipelineRuntime, InMemoryEventBus]:
    bus = InMemoryEventBus()
    deps = RuntimeDeps(
        bus=bus, clock=SystemClock(), state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(), feed_factory=lambda _m: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    settings = Settings(
        persist_state=False, initial_capital="1000",
        prices_topic="prices.thb_btc.v1", dashboard_api_key=SecretStr(""),
    )
    return PipelineRuntime(settings, structlog.get_logger("test"), deps=deps), bus


@pytest.mark.asyncio
async def test_status_surfaces_confluence_and_dynamic_weighting() -> None:
    runtime, bus = _make_runtime()
    app = create_app(runtime)
    await runtime.start("live")
    try:
        # Freeze the Timeline Analyst so our injected verdict isn't overwritten,
        # then publish it on the bus — the confluence loop must fold it in.
        await runtime.stop_agent("timeline_analyst")
        for _ in range(50):
            await bus.publish(
                "timeline.v1", b"t",
                orjson.dumps({
                    "type": "TIMELINE_ANALYSIS", "p_win": "0.73",
                    "p_win_samples": 30, "regime": "TREND_UP",
                }),
            )
            if runtime._confluence["p_win"] == "0.73":
                break
            await asyncio.sleep(0.03)

        # A real trade outcome routed back: the weighting loop must attribute it.
        for _ in range(50):
            await bus.publish(
                "paper.events.v1", b"p",
                orjson.dumps({"type": "CLOSE", "voters": ["entry_chief"], "pnl_net": "55"}),
            )
            if runtime._source_perf.samples("entry_chief") >= 1:
                break
            await asyncio.sleep(0.03)

        transport = ASGITransport(app=app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/status")
            assert resp.status_code == 200, resp.text
            s = resp.json()

        # Task 1 — the confluence the gate uses is served and fed from the bus.
        assert s["confluence"]["p_win"] == "0.73"
        assert s["confluence"]["regime"] == "TREND_UP"
        assert s["timeline"]["p_win"] == "0.73"   # same single source of truth
        # Task 2 — the dynamic weighting reflects the real paper.events outcome.
        assert "entry_chief" in s["dynamic_weighting"]["sources"]
        assert s["dynamic_weighting"]["sources"]["entry_chief"]["samples"] >= 1
    finally:
        await runtime.stop()
