# Layer 2 — Orchestration (tests/orchestration/test_memory_persistence)
"""Agents remember their mistakes + fixes across a shutdown.

The runtime serialises every agent's Learner to the state store and restores it
on the next start, so 'tomorrow' each agent recalls what it got wrong and what
it changed (ความทรงจำจากของเดิม)."""
from __future__ import annotations

import structlog

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.agents.learning import Learner
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed


# ── Learner serialisation ────────────────────────────────────────────
def test_learner_to_dict_and_load_dict_roundtrip() -> None:
    src = Learner("trend_follower", "strategy")
    src.resolved, src.correct = 9, 4
    src.today_resolved, src.today_correct = 5, 2
    src.adapt_count = 3
    src.score = 71.5
    src.log("ผล BUY @100 → 90: ❌ ผิด (-10%)", "outcome")
    src.log("เพิ่มเงื่อนไขยืนยัน EMA", "adapt")

    blob = src.to_dict()
    dst = Learner("trend_follower", "strategy")
    dst.load_dict(blob)

    assert (dst.resolved, dst.correct) == (9, 4)
    assert (dst.today_resolved, dst.today_correct) == (5, 2)
    assert dst.adapt_count == 3
    assert dst.score == 71.5
    assert len(dst.recent_mistakes()) == 1
    assert len(dst.recent_improvements()) == 1


def test_load_dict_tolerates_garbage() -> None:
    learner = Learner("x")
    learner.load_dict({"resolved": "nope", "score": None, "journal": ["bad", {"ts_ms": "x"}]})
    assert learner.resolved == 0
    assert learner.score == 50.0  # default kept


# ── runtime persist → restore ────────────────────────────────────────
def _runtime(store: InMemoryStateStore) -> PipelineRuntime:
    settings = Settings(persist_state=True, initial_capital="1000", prices_topic="prices.thb_btc.v1")
    deps = RuntimeDeps(
        bus=InMemoryEventBus(),
        clock=SystemClock(),
        state_store=store,
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    return PipelineRuntime(settings, structlog.get_logger("test"), deps=deps)


async def test_runtime_persists_and_restores_agent_memory() -> None:
    store = InMemoryStateStore()

    # Session 1: an agent makes a mistake and adapts, then memory is saved.
    rt1 = _runtime(store)
    rt1.agents = rt1._make_agents()
    learner = rt1._learner_for("trend_follower", rt1.agents["trend_follower"])
    learner.resolved, learner.correct = 7, 3
    learner.log("ผล BUY @100 → 90: ❌ ผิด (-10%)", "outcome")
    learner.log("เพิ่ม gap ยืนยัน 0.10%→0.20%", "adapt")
    await rt1._persist_memories()

    # Session 2 (a fresh runtime sharing the same on-disk store): memory returns.
    rt2 = _runtime(store)
    rt2.agents = rt2._make_agents()
    await rt2._restore_memories()
    restored = rt2._learner_for("trend_follower", rt2.agents["trend_follower"])
    assert restored.resolved == 7
    assert restored.correct == 3
    assert len(restored.recent_mistakes()) >= 1
    assert len(restored.recent_improvements()) >= 1


async def test_memory_is_a_noop_without_a_store() -> None:
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("test"))
    rt.agents = rt._make_agents()
    # No deps and persistence off → no store; these must not raise.
    await rt._persist_memories()
    await rt._restore_memories()
