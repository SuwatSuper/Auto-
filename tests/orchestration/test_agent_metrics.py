# Tests — per-agent metrics exposed for the live monitor (real data, not demo)
from __future__ import annotations

import structlog

from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime


def _rt():
    rt = PipelineRuntime(settings=Settings(training_mode=False, persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    return rt


def test_every_agent_reports_core_metrics():
    rt = _rt()
    agents = rt.status()["agents"]
    assert agents
    for a in agents:
        # the monitor relies on these being present + real for every agent
        assert "name" in a
        assert "running" in a
        assert isinstance(a["msg_count"], int)
        assert "stale" in a and "restarts" in a


def test_signal_and_decision_agents_expose_counts():
    rt = _rt()
    by = {a["name"]: a for a in rt.status()["agents"]}
    # market analyst produces signals
    assert "signal_count" in by["market_analyst"]
    # risk management tracks rejections
    assert "rejected_count" in by["risk_management"]


def test_metrics_are_zero_before_any_data_flows():
    # before prices flow, msg_count is 0 (monitor shows "waiting for data")
    rt = _rt()
    by = {a["name"]: a for a in rt.status()["agents"]}
    assert by["market_analyst"]["msg_count"] == 0
