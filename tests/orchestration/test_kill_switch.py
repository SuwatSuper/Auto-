# Layer 2 — Orchestration (tests/orchestration/test_kill_switch)
"""T4: KILL_SWITCH toggle from the control plane blocks/unblocks arming live."""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime

_LIVE = "I_ACCEPT_REAL_MONEY_RISK"


def _rt(**kw: object) -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, **kw),  # type: ignore[arg-type]
        logger=structlog.get_logger("t"),
    )
    rt.agents = rt._make_agents()
    return rt


def test_kill_switch_blocks_then_unblocks_live(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)  # data/KILL_SWITCH is created under cwd
    rt = _rt()
    rt._max_single_order_thb = Decimal("500")
    # M1: arming live requires real backstops (finite breaker, daily-loss < 100).
    from domain.portfolio.treasury import TreasuryLimits  # noqa: PLC0415
    assert rt._circuit_breaker is not None and rt._treasury is not None
    rt._circuit_breaker.update_threshold(5)
    rt._treasury.update_limits(
        TreasuryLimits(
            initial_capital=rt._initial_capital,
            survival_floor_pct=Decimal("70"),
            max_daily_loss_pct=Decimal("5"),
        )
    )

    rt.set_kill_switch(True)
    assert rt.kill_switch_on() is True
    assert (tmp_path / "data" / "KILL_SWITCH").exists()
    ok, payload = rt.set_execution_mode("live", confirm=_LIVE)
    assert ok is False and "KILL_SWITCH" in str(payload)  # blocked by the kill switch

    rt.set_kill_switch(False)
    assert rt.kill_switch_on() is False
    ok2, _ = rt.set_execution_mode("live", confirm=_LIVE)
    assert ok2 is True  # gate clears once the kill switch is off


@pytest.mark.asyncio
async def test_kill_switch_endpoints(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = _rt(dashboard_api_key="k")
    transport = ASGITransport(app=create_app(rt))  # type: ignore[arg-type]
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-API-Key": "k"}
    ) as c:
        assert (await c.get("/api/kill_switch")).json()["on"] is False
        on = await c.post("/api/kill_switch", json={"on": True})
        assert on.status_code == 200 and on.json()["on"] is True
        assert (await c.get("/api/kill_switch")).json()["on"] is True
        off = await c.post("/api/kill_switch", json={"on": False})
        assert off.status_code == 200 and off.json()["on"] is False
        # bad body → 400
        assert (await c.post("/api/kill_switch", json={})).status_code == 400


@pytest.mark.asyncio
async def test_kill_switch_post_localhost_trusted_remote_strict(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = _rt(dashboard_api_key="k")
    app = create_app(rt)
    # localhost (no header) → trusted, toggles fine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/api/kill_switch", json={"on": False})).status_code == 200
    # remote (no header) → rejected before acting
    transport = ASGITransport(app=app, client=("203.0.113.7", 5555))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.post("/api/kill_switch", json={"on": True})).status_code == 401
