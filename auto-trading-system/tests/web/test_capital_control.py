# Layer 3 — Infrastructure (tests/web/test_capital_control)
"""T2: initial_capital mandate default (1,000) + live setter + persistence."""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def test_default_capital_is_mandate_1000() -> None:
    assert Settings().initial_capital == "1000"


def _rt(**kw: object) -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, **kw),  # type: ignore[arg-type]
        logger=structlog.get_logger("t"),
    )
    rt.agents = rt._make_agents()
    return rt


def test_set_initial_capital_updates_runtime_treasury_status(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)  # _persist_capital writes ./.env here
    rt = _rt()
    ok, payload = rt.set_initial_capital("250000")
    assert ok and payload["initial_capital"] == "250000"
    assert rt._initial_capital == Decimal("250000")
    assert rt._treasury is not None and rt._treasury.cash == Decimal("250000")
    assert rt.status()["initial_capital"] == "250000"
    assert "INITIAL_CAPITAL=250000" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_set_initial_capital_rejects_bad_values(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = _rt()
    assert rt.set_initial_capital("0")[0] is False
    assert rt.set_initial_capital("-5")[0] is False
    assert rt.set_initial_capital("abc")[0] is False
    # unchanged after rejected writes
    assert rt._treasury is not None and rt._treasury.cash == Decimal("1000")


@pytest.mark.asyncio
async def test_capital_endpoint_changes_and_validates(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = _rt(dashboard_api_key="")  # localhost-trusted (non-dangerous endpoint)
    transport = ASGITransport(app=create_app(rt))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/settings/capital", json={"capital": "5000"})
        assert r.status_code == 200 and r.json()["initial_capital"] == "5000"
        assert (await c.get("/api/status")).json()["initial_capital"] == "5000"
        # invalid / missing
        assert (await c.post("/api/settings/capital", json={"capital": "-5"})).status_code == 400
        assert (await c.post("/api/settings/capital", json={})).status_code == 400
