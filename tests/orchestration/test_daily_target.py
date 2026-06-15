# Layer 2 — Orchestration (tests/orchestration/test_daily_target)
"""Phase 3: daily profit-target engine — lock the day's gains at target (block
new BUYs), report the REAL net % (not the target), and tune the target live."""
from __future__ import annotations

from decimal import Decimal

import pytest
import structlog
from httpx import ASGITransport, AsyncClient

from domain.trading.paper import ClosedTrade, ExitReason
from infrastructure.config import Settings
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def _rt(**kw: object) -> PipelineRuntime:
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, initial_capital="1000", **kw),  # type: ignore[arg-type]
        logger=structlog.get_logger("t"),
    )
    rt.agents = rt._make_agents()
    return rt


def _settle(rt: PipelineRuntime, pnl: str) -> None:
    assert rt._treasury is not None
    rt._treasury.settle_close(ClosedTrade(
        symbol="thb_btc", qty=Decimal("0.001"),
        entry_price=Decimal("1000000"), exit_price=Decimal("1000000"),
        entry_fee=Decimal("0"), exit_fee=Decimal("0"),
        pnl=Decimal(pnl), reason=ExitReason.TAKE_PROFIT, opened_ms=0, closed_ms=1,
    ))


def test_trade_budget_locks_when_target_reached() -> None:
    rt = _rt()  # target 5% (default), stop_at_daily_target=True (default)
    assert rt._trade_budget() is True              # fresh day → may trade
    _settle(rt, "30")                              # +3% of 1,000 → still chasing
    assert rt._trade_budget() is True
    _settle(rt, "30")                              # +6% total → target reached
    assert rt.daily_profit_pct() >= rt._target_daily_profit_pct
    assert rt._trade_budget() is False             # locked — no new BUYs today


def test_target_lock_disabled_when_stop_at_target_false() -> None:
    rt = _rt(stop_at_daily_target=False)
    _settle(rt, "100")                             # +10% — way past target
    assert rt._trade_budget() is True              # not locked (operator opted out)


def test_daily_status_reports_real_pct_and_reached_flag() -> None:
    rt = _rt()
    _settle(rt, "60")                              # +6%
    daily = rt.status()["daily"]
    assert isinstance(daily, dict)
    assert Decimal(str(daily["profit_pct_today"])) == Decimal("6")   # REAL, not 5
    assert Decimal(str(daily["target_profit_pct"])) == Decimal("5")
    assert daily["target_reached"] is True


def test_set_daily_target_validates_and_persists(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = _rt()
    ok, payload = rt.set_daily_target("3.5")
    assert ok and payload["target_profit_pct"] == "3.5"
    assert rt._target_daily_profit_pct == Decimal("3.5")
    assert "TARGET_DAILY_PROFIT_PCT=3.5" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert rt.set_daily_target("-1")[0] is False
    assert rt.set_daily_target("abc")[0] is False


@pytest.mark.asyncio
async def test_daily_target_endpoint(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    rt = _rt(dashboard_api_key="")
    transport = ASGITransport(app=create_app(rt))  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/settings/daily_target", json={"target_pct": "7"})
        assert r.status_code == 200 and r.json()["target_profit_pct"] == "7"
        daily = (await c.get("/api/status")).json()["daily"]
        assert Decimal(str(daily["target_profit_pct"])) == Decimal("7")
        assert (await c.post("/api/settings/daily_target", json={})).status_code == 400
