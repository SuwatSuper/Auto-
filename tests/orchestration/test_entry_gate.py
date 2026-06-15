"""Win-probability entry gate + per-agent learning board + daily governance."""
from __future__ import annotations

from decimal import Decimal

import structlog

from orchestration.runtime import PipelineRuntime

D = Decimal


class _S:
    prices_topic = "prices.thb_btc.v1"
    bitkub_ws_url = ""
    persist_state = False
    initial_capital = "1000000"
    price_feed_mode = "rest"
    bitkub_api_key = None
    bitkub_api_secret = None
    max_consecutive_losses = 5
    max_open_positions = 1
    min_p_win = "0.80"
    entry_gate_enabled = True
    max_trades_per_day = 1000
    target_daily_profit_pct = "5"


def _rt() -> PipelineRuntime:
    rt = PipelineRuntime(_S(), structlog.get_logger("t"))
    rt._ensure_bus()
    rt.agents = rt._make_agents()
    return rt


def test_gate_blocks_buy_until_pwin_proven() -> None:
    rt = _rt()
    # analyst has no data yet → sample too small → blocked
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert not approved
    assert "SAMPLE_TOO_SMALL" in reasons or "P_WIN_BELOW_MIN" in reasons

    # simulate analyst measuring a high win rate over a real sample
    rt._timeline.p_win = D("0.85")        # type: ignore[attr-defined]
    rt._timeline.p_win_samples = 40       # type: ignore[attr-defined]
    rt._timeline.regime = "TREND_UP"      # type: ignore[attr-defined]
    approved2, reasons2 = rt._entry_gate({"signal": "BUY"})
    assert approved2 and reasons2 == []

    # drop p_win below the floor → blocked again
    rt._timeline.p_win = D("0.60")        # type: ignore[attr-defined]
    approved3, reasons3 = rt._entry_gate({"signal": "BUY"})
    assert not approved3 and "P_WIN_BELOW_MIN" in reasons3


def test_disabled_gate_passes() -> None:
    rt = _rt()
    rt._entry_gate_enabled = False
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert approved and reasons == []


def test_learning_overview_has_card_for_every_agent() -> None:
    rt = _rt()
    ov = rt.learning_overview()
    assert len(ov["leaderboard"]) == len(rt.agents)
    for row in ov["leaderboard"]:
        assert isinstance(row["learns_from"], str) and row["learns_from"]
        assert isinstance(row["can_improve"], str) and row["can_improve"]
        assert isinstance(row["recent_mistakes"], list)
        assert isinstance(row["recent_improvements"], list)


def test_status_exposes_timeline_gate_and_daily() -> None:
    rt = _rt()
    st = rt.status()
    assert st["timeline"]["available"] is True
    assert "p_win_pct" in st["timeline"] and "regime" in st["timeline"]
    assert st["entry_gate"]["enabled"] is True
    assert st["daily"]["max_trades_per_day"] == 1000
    assert st["daily"]["target_profit_pct"] == 5.0
    # every agent status row carries the learning board fields
    for a in st["agents"]:
        assert "learns_from" in a and "can_improve" in a
