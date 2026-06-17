# Composition-root + agent-spec coverage.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bootstrap import build_runtime
from infrastructure.config import Settings
from orchestration.agents.spec import AgentSpec, Department
from orchestration.runtime import PipelineRuntime


def test_build_runtime_with_explicit_settings() -> None:
    rt = build_runtime(Settings(persist_state=False))
    assert isinstance(rt, PipelineRuntime)
    assert rt.mode == "live"


def test_build_runtime_defaults_settings() -> None:
    # settings=None → Settings() is constructed internally (composition root).
    rt = build_runtime()
    assert isinstance(rt, PipelineRuntime)
    assert rt.logger is not None


def test_agent_spec_is_frozen_and_typed() -> None:
    spec = AgentSpec(
        name="market_analyst",
        department=Department.ENTRY_EXIT,
        topic_in="prices.thb_btc.v1",
        topic_out="signals.v1",
    )
    assert spec.department is Department.ENTRY_EXIT
    assert spec.description == ""
    assert Department("risk") is Department.RISK
    with pytest.raises(ValidationError):
        spec.name = "changed"  # frozen model — assignment is rejected
