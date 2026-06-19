# Layer 2 — Orchestration (tests/orchestration/test_strategy_control)
"""T3: strategy control has REAL effect — a disabled strategy emits no signals,
and a parameter change alters the strategy's behaviour."""
from __future__ import annotations

from decimal import Decimal

import orjson
import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.agents.extended import BreakoutSpecialistAgent
from orchestration.runtime import PipelineRuntime
from orchestration.runtime_strategy import _apply_params

_LOG = structlog.get_logger("test")


class _RecBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def subscribe(self, topic: str, maxsize: int = 10_000):  # type: ignore[no-untyped-def]
        import asyncio
        return asyncio.Queue()

    def unsubscribe(self, topic: str, queue) -> None:  # type: ignore[no-untyped-def]
        pass

    async def publish(self, topic: str, key: bytes, value: bytes) -> None:
        self.published.append((topic, orjson.loads(value)))


async def _feed(agent, prices) -> None:  # type: ignore[no-untyped-def]
    for p in prices:
        d = Decimal(str(p))
        agent._prices.append(d)
        await agent.on_price(d, 1_000)


def _breakout(bus: _RecBus) -> BreakoutSpecialistAgent:
    return BreakoutSpecialistAgent("breakout_specialist", bus, "p", "signals", _LOG)  # type: ignore[arg-type]


# ── disable → no signal into the pipeline ────────────────────────────
@pytest.mark.asyncio
async def test_disabled_strategy_emits_no_signal() -> None:
    on_bus = _RecBus()
    enabled = _breakout(on_bus)
    await _feed(enabled, [100] * 21 + [130])  # a real breakout above the channel
    assert any(t == "signals" for t, _ in on_bus.published), "enabled strategy must emit"

    off_bus = _RecBus()
    disabled = _breakout(off_bus)
    disabled.enabled = False
    await _feed(disabled, [100] * 21 + [130])  # same breakout
    assert off_bus.published == [], "disabled strategy must emit nothing"


# ── param change → behaviour changes ─────────────────────────────────
@pytest.mark.asyncio
async def test_widening_channel_suppresses_breakout() -> None:
    narrow_bus = _RecBus()
    narrow = _breakout(narrow_bus)  # default channel N=20 → 22 bars is enough
    await _feed(narrow, [100] * 21 + [130])
    assert narrow_bus.published, "N=20 breakout should fire"

    wide_bus = _RecBus()
    wide = _breakout(wide_bus)
    errs = _apply_params(wide, {"channel_n": "50"})  # control-path param apply
    assert errs == [] and wide._n == 50
    await _feed(wide, [100] * 21 + [130])  # only 22 bars < 51 → still warming up
    assert wide_bus.published == [], "wider channel changes behaviour (no fire yet)"


def test_apply_params_validation() -> None:
    bus = _RecBus()
    agent = _breakout(bus)
    assert _apply_params(agent, {"channel_n": "1"})       # 1 < 2 → error
    assert _apply_params(agent, {"channel_n": "abc"})     # not a number → error
    assert _apply_params(agent, {"nope": "1"})            # unknown param → error
    assert _apply_params(agent, {"channel_n": "30"}) == []  # valid
    assert agent._n == 30


# ── runtime + HTTP control plane ─────────────────────────────────────
def _rt(**kw: object) -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, **kw),  # type: ignore[arg-type]
        logger=structlog.get_logger("t"),
    )
    rt.agents = rt._make_agents()
    return rt


def test_runtime_set_strategy_enabled_unknown() -> None:
    rt = _rt()
    ok, payload = rt.set_strategy_enabled("does_not_exist", False)
    assert ok is False and "unknown strategy" in str(payload)


@pytest.mark.asyncio
async def test_strategy_endpoints() -> None:
    rt = _rt(dashboard_api_key="")
    transport = ASGITransport(app=create_app(rt))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        ls = await c.get("/api/strategies")
        assert ls.status_code == 200
        ids = {s["id"] for s in ls.json()["strategies"]}
        assert {"market_analyst", "trend_follower", "mean_reversion", "breakout_specialist"} <= ids

        # disable → reflected in overview + the live agent
        d = await c.post("/api/strategies/trend_follower/disable")
        assert d.status_code == 200 and d.json()["enabled"] is False
        assert rt.agents["trend_follower"].enabled is False  # type: ignore[attr-defined]
        assert (await c.post("/api/strategies/trend_follower/enable")).json()["enabled"] is True

        # tune a param
        p = await c.post("/api/strategies/mean_reversion/params", json={"rsi_oversold": "20"})
        assert p.status_code == 200 and p.json()["params"]["rsi_oversold"] == "20"

        # invalid value → 400, unknown strategy → 404
        assert (await c.post(
            "/api/strategies/mean_reversion/params", json={"rsi_oversold": "999"}
        )).status_code == 400
        assert (await c.post("/api/strategies/ghost/enable")).status_code == 404
