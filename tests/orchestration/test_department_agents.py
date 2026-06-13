# Layer 2 — Orchestration (tests/orchestration/test_department_agents)
"""Smoke tests for department agents using InMemoryEventBus."""
from __future__ import annotations

import asyncio
import contextlib

import orjson
import pytest
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.entry_exit import EntryExitAgent
from orchestration.agents.historical_research import HistoricalResearchAgent
from orchestration.agents.news_sentiment import NewsSentimentAgent
from orchestration.agents.probability import ProbabilityAgent
from orchestration.agents.risk_agent import RiskAgent
from orchestration.agents.simulation import SimulationAgent
from orchestration.agents.supreme import SupremeAgent
from orchestration.supervisors.supervisor import Supervisor


def _logger() -> structlog.BoundLogger:
    return structlog.get_logger()


async def test_news_sentiment_agent_start_stop() -> None:
    bus = InMemoryEventBus()
    agent = NewsSentimentAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    assert agent.running is True
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert agent.running is False


async def test_news_sentiment_processes_message() -> None:
    bus = InMemoryEventBus()
    out_q = bus.subscribe("out")
    agent = NewsSentimentAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"key", orjson.dumps({"score": "0.7"}))
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    data = orjson.loads(out_q.get_nowait())
    assert data["sentiment_score"] == "0.7"


async def test_news_sentiment_parse_failure_counted() -> None:
    bus = InMemoryEventBus()
    agent = NewsSentimentAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"key", b"bad json{{{")
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert agent.parse_failures == 1


async def test_risk_agent_start_stop() -> None:
    bus = InMemoryEventBus()
    agent = RiskAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    assert agent.running is True
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert agent.running is False


async def test_risk_agent_approves_small_order() -> None:
    bus = InMemoryEventBus()
    out_q = bus.subscribe("out")
    agent = RiskAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"key", orjson.dumps({"qty": "0.01"}))
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    data = orjson.loads(out_q.get_nowait())
    assert data["approved"] is True


async def test_entry_exit_agent_start_stop() -> None:
    bus = InMemoryEventBus()
    agent = EntryExitAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    assert agent.running is True
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert agent.running is False


async def test_entry_exit_processes_prices() -> None:
    bus = InMemoryEventBus()
    agent = EntryExitAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    for i in range(10):
        msg = orjson.dumps({"price": str(1000 + i * 100), "ts_ms": i * 1000})
        await bus.publish("in", b"key", msg)
    await asyncio.sleep(0.1)
    assert agent.msg_count == 10
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_simulation_agent_start_stop() -> None:
    bus = InMemoryEventBus()
    agent = SimulationAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    assert agent.running is True
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_simulation_agent_accumulates_prices() -> None:
    bus = InMemoryEventBus()
    agent = SimulationAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    for i in range(10):
        msg = orjson.dumps({"price": str(1000 + i), "ts_ms": i * 1000})
        await bus.publish("in", b"key", msg)
    await asyncio.sleep(0.1)
    assert agent.msg_count == 10
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)



async def test_historical_research_start_stop() -> None:
    bus = InMemoryEventBus()
    agent = HistoricalResearchAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    assert agent.running is True
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_historical_research_processes_price() -> None:
    bus = InMemoryEventBus()
    out_q = bus.subscribe("out")
    agent = HistoricalResearchAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"key", orjson.dumps({"price": "1500000"}))
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    data = orjson.loads(out_q.get_nowait())
    assert data["price_count"] == 1


async def test_probability_agent_start_stop() -> None:
    bus = InMemoryEventBus()
    agent = ProbabilityAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    assert agent.running is True
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_probability_agent_processes_price() -> None:
    bus = InMemoryEventBus()
    agent = ProbabilityAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"key", orjson.dumps({"price": "1500000"}))
    await asyncio.sleep(0.1)
    assert agent.msg_count == 1
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_supreme_agent_start_stop() -> None:
    bus = InMemoryEventBus()
    agent = SupremeAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    assert agent.running is True
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)


async def test_supreme_agent_buy_signal_executes() -> None:
    bus = InMemoryEventBus()
    out_q = bus.subscribe("out")
    agent = SupremeAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"key", orjson.dumps({"signal": "BUY"}))
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    data = orjson.loads(out_q.get_nowait())
    assert data["decision"] == "EXECUTE"


async def test_supreme_agent_stamps_unique_decision_id() -> None:
    """Each emitted decision carries a unique decision_id so the execution
    gate can identify genuine duplicates instead of falling back to id(data)."""
    bus = InMemoryEventBus()
    out_q = bus.subscribe("out")
    agent = SupremeAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    for _ in range(5):
        await bus.publish("in", b"key", orjson.dumps({"signal": "BUY"}))
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)

    ids: list[str] = []
    while not out_q.empty():
        data = orjson.loads(out_q.get_nowait())
        assert data["decision"] == "EXECUTE"
        assert "decision_id" in data and data["decision_id"]
        ids.append(data["decision_id"])
    assert len(ids) == 5
    assert len(set(ids)) == 5  # all unique


async def test_supreme_consensus_requires_multiple_sources() -> None:
    """With buy_votes=2, one source BUY -> OBSERVE; a second distinct source
    BUY within the window -> EXECUTE (real multi-agent consensus)."""
    bus = InMemoryEventBus()
    out_q = bus.subscribe("out")
    agent = SupremeAgent(
        bus=bus, topic_in="in", topic_out="out", logger=_logger(),
        window_s=8.0, buy_votes=2, sell_votes=2,
    )
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"k", orjson.dumps({"signal": "BUY", "source": "trend_follower", "ts_ms": 1000}))
    await asyncio.sleep(0.05)
    await bus.publish("in", b"k", orjson.dumps({"signal": "BUY", "source": "breakout_specialist", "ts_ms": 1100}))
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)

    decisions = [orjson.loads(out_q.get_nowait()) for _ in range(2)]
    assert decisions[0]["decision"] == "OBSERVE"   # only 1 source so far
    assert decisions[1]["decision"] == "EXECUTE"   # 2 sources agree
    assert decisions[1]["signal"] == "BUY"
    assert decisions[1]["net_votes"] == 2


async def test_supreme_agent_hold_observes() -> None:
    bus = InMemoryEventBus()
    out_q = bus.subscribe("out")
    agent = SupremeAgent(bus=bus, topic_in="in", topic_out="out", logger=_logger())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"key", orjson.dumps({"signal": "HOLD"}))
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    data = orjson.loads(out_q.get_nowait())
    assert data["decision"] == "OBSERVE"


async def test_supervisor_restarts_on_failure() -> None:
    call_count = 0

    async def flaky() -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("flaky failure")
        # succeed on 3rd call, then stop the supervisor
        sup.stop()

    sup = Supervisor("test", flaky, structlog.get_logger(), max_restarts=5, backoff_base=0.01)
    task = asyncio.create_task(sup.run())
    await asyncio.wait_for(task, timeout=2.0)
    assert call_count >= 3


async def test_supervisor_gives_up_after_max_restarts() -> None:
    async def always_fail() -> None:
        raise RuntimeError("always fails")

    sup = Supervisor("test", always_fail, structlog.get_logger(), max_restarts=2, backoff_base=0.01)
    with pytest.raises(RuntimeError):
        await asyncio.wait_for(sup.run(), timeout=2.0)


async def test_supervisor_stop_before_run() -> None:
    async def noop() -> None:
        pass

    sup = Supervisor("test", noop, structlog.get_logger())
    sup.stop()
    assert sup._running is False


async def test_supervisor_stop_during_run() -> None:
    async def long_running() -> None:
        await asyncio.sleep(10)  # would block forever without stop

    sup = Supervisor("test", long_running, structlog.get_logger())
    task = asyncio.create_task(sup.run())
    await asyncio.sleep(0.05)
    sup.stop()
    task.cancel()
    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
