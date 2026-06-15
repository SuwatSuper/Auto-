# Layer 3 — Infrastructure (tests/web/test_mini_dashboard)
"""Minimal live dashboard: routes, chart/trade endpoints, and the loopback
rate-limit fix that previously broke the operator's own login/connect."""
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
from orchestration.runtime_base import _TOPIC_PAPER_EVENTS
from tests._fixtures import FakePriceFeed

_TOPIC = "prices.thb_btc.v1"


def _runtime(key: str = "") -> PipelineRuntime:
    settings = Settings(
        persist_state=False, initial_capital="1000", prices_topic=_TOPIC,
        dashboard_api_key=SecretStr(key),
    )
    deps = RuntimeDeps(
        bus=InMemoryEventBus(),
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic=_TOPIC,
    )
    return PipelineRuntime(settings, structlog.get_logger("test"), deps=deps)


@pytest.fixture
async def local_client():
    """Loopback client (ASGITransport defaults to 127.0.0.1)."""
    runtime = _runtime("")
    app = create_app(runtime)
    await runtime.start("live")
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            yield runtime, client
        finally:
            await runtime.stop()


@pytest.mark.asyncio
async def test_root_serves_minimal_chart_dashboard(local_client) -> None:  # type: ignore[no-untyped-def]
    _, client = local_client
    r = await client.get("/")
    assert r.status_code == 200
    assert "Kingdom Prime" in r.text          # brand kept (dashboard contract)
    assert "กราฟราคา" in r.text                # the real price chart heading
    assert 'id="chart"' in r.text             # the canvas
    assert "__DASHBOARD_API_KEY__" not in r.text


@pytest.mark.asyncio
async def test_full_route_serves_control_room(local_client) -> None:  # type: ignore[no-untyped-def]
    _, client = local_client
    r = await client.get("/full")
    assert r.status_code == 200
    # kingdom.html is the heavy control room — it loads Chart.js; mini does not.
    assert "chart.umd.min.js" in r.text


@pytest.mark.asyncio
async def test_prices_history_endpoint_backfills_after_ticks(local_client) -> None:  # type: ignore[no-untyped-def]
    _, client = local_client
    await asyncio.sleep(0.25)  # let the fake feed publish a few ticks
    r = await client.get("/api/prices/history")
    assert r.status_code == 200
    prices = r.json()["prices"]
    assert isinstance(prices, list) and len(prices) >= 1
    assert {"ts_ms", "price"} <= set(prices[0].keys())


@pytest.mark.asyncio
async def test_trades_endpoint_reflects_paper_events(local_client) -> None:  # type: ignore[no-untyped-def]
    runtime, client = local_client
    # Empty shape first.
    r0 = await client.get("/api/trades")
    assert r0.status_code == 200 and isinstance(r0.json()["trades"], list)
    # Publish a FILL then a CLOSE to the paper-events topic; the recorder mirrors them.
    fill = orjson.dumps({"type": "FILL", "ts_ms": 1, "qty": "0.001", "entry": "2880000"})
    close = orjson.dumps({"type": "CLOSE", "ts_ms": 2, "exit": "2900000", "pnl_net": "12.50", "reason": "TAKE_PROFIT"})
    await runtime.bus.publish(_TOPIC_PAPER_EVENTS, b"paper", fill)
    await runtime.bus.publish(_TOPIC_PAPER_EVENTS, b"paper", close)
    for _ in range(50):
        await asyncio.sleep(0.02)
        trades = (await client.get("/api/trades")).json()["trades"]
        if len(trades) >= 2:
            break
    types = [t.get("type") for t in trades]
    assert "FILL" in types and "CLOSE" in types
    closed = next(t for t in trades if t["type"] == "CLOSE")
    assert closed["pnl_net"] == "12.50"


@pytest.mark.asyncio
async def test_status_exposes_entry_gate_warmup(local_client) -> None:  # type: ignore[no-untyped-def]
    """The mini page explains WHY there are no trades yet — status must carry the
    entry-gate warmup progress + block reasons it reads."""
    _, client = local_client
    eg = (await client.get("/api/status")).json()["entry_gate"]
    assert {"enabled", "samples", "min_samples", "warming_up", "blocked_by_reason"} <= set(eg)
    assert isinstance(eg["min_samples"], int) and eg["min_samples"] >= 1
    assert isinstance(eg["warming_up"], bool)


@pytest.mark.asyncio
async def test_recent_trades_loop_survives_bad_frame(local_client) -> None:  # type: ignore[no-untyped-def]
    """A non-dict frame on the paper-events topic must not kill the (un-watched)
    recorder loop — the trades feed must keep working."""
    runtime, client = local_client
    await runtime.bus.publish(_TOPIC_PAPER_EVENTS, b"x", orjson.dumps([1, 2, 3]))  # bad frame
    await runtime.bus.publish(
        _TOPIC_PAPER_EVENTS, b"x",
        orjson.dumps({"type": "FILL", "ts_ms": 1, "qty": "0.001", "entry": "100"}),
    )
    trades: list[dict] = []
    for _ in range(50):
        await asyncio.sleep(0.02)
        trades = (await client.get("/api/trades")).json()["trades"]
        if trades:
            break
    assert any(t.get("type") == "FILL" for t in trades)


@pytest.mark.asyncio
async def test_trade_endpoints_require_key_for_remote() -> None:
    """The new read endpoints carry account state — a remote client needs the key
    when one is configured (loopback stays trusted)."""
    runtime = _runtime("SECRET")
    app = create_app(runtime)
    await runtime.start("live")
    transport = ASGITransport(app=app, client=("203.0.113.9", 5555))  # type: ignore[arg-type]
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/api/trades")).status_code == 401
            assert (await c.get("/api/prices/history")).status_code == 401
            ok = await c.get("/api/trades", headers={"X-API-Key": "SECRET"})
            assert ok.status_code == 200
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_loopback_is_not_rate_limited(local_client) -> None:  # type: ignore[no-untyped-def]
    """Regression: the local dashboard polls heavily; loopback must NOT hit 429
    (this previously blocked the operator's own login/connect)."""
    _, client = local_client
    codes = {(await client.get("/healthz")).status_code for _ in range(150)}
    assert codes == {200}


@pytest.mark.asyncio
async def test_remote_is_still_rate_limited() -> None:
    """Non-loopback traffic is still capped (network-abuse protection intact)."""
    runtime = _runtime("k")
    app = create_app(runtime)
    await runtime.start("live")
    # A fresh remote IP so the module-global limiter window is this test's alone.
    transport = ASGITransport(app=app, client=("198.51.100.207", 4242))  # type: ignore[arg-type]
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            statuses = [(await client.get("/healthz")).status_code for _ in range(140)]
    finally:
        await runtime.stop()
    assert 429 in statuses
