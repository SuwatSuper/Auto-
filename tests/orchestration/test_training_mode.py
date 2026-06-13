"""TRAINING_MODE — unlocks all limits + big paper bankroll, forces paper."""
from __future__ import annotations

from decimal import Decimal

import structlog

from orchestration.runtime import PipelineRuntime


class _TrainOn:
    training_mode = True
    training_capital = "10000000"
    prices_topic = "prices.thb_btc.v1"
    bitkub_ws_url = ""
    persist_state = False
    price_feed_mode = "rest"
    bitkub_api_key = None
    bitkub_api_secret = None


class _TrainOff(_TrainOn):
    training_mode = False
    initial_capital = "1000"
    max_consecutive_losses = "5"
    survival_floor_pct = "70"
    max_daily_loss_pct = "10"
    entry_gate_enabled = True
    execution_engine = "paper"


def test_training_mode_unlocks_all_limits_and_forces_paper() -> None:
    rt = PipelineRuntime(_TrainOn(), structlog.get_logger("t"))
    rt._ensure_bus()
    rt.agents = rt._make_agents()
    # big bankroll
    assert rt._initial_capital == Decimal("10000000")
    # breaker effectively unlimited (never auto-trips)
    assert rt._circuit_breaker.max_consecutive_losses >= 1_000_000
    # entry gate off → agents trade freely to train
    assert rt._entry_gate_enabled is False
    assert rt._entry_gate({"signal": "BUY"}) == (True, [])
    # treasury limits unlocked: floor 0, daily-loss cap = full capital
    t = rt._treasury
    assert t.limits.survival_floor_pct == Decimal("0")
    assert t.limits.floor_equity() == Decimal("0")
    assert t.limits.max_daily_loss_pct == Decimal("100")
    # SAFETY: execution forced to paper even though limits are unlimited
    assert rt.settings.execution_engine == "paper"
    assert rt._live_orders_armed() is False


def test_training_mode_off_keeps_disciplined_config() -> None:
    rt = PipelineRuntime(_TrainOff(), structlog.get_logger("t"))
    rt._ensure_bus()
    rt.agents = rt._make_agents()
    assert rt._initial_capital == Decimal("1000")
    assert rt._circuit_breaker.max_consecutive_losses == 5
    assert rt._entry_gate_enabled is True
    assert rt._treasury.limits.survival_floor_pct == Decimal("70")
