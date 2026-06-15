# Layer 2 — Orchestration (tests/orchestration/test_audit_double_entry)
"""Regression: live double-entry race.

This test was previously present (a stale ``__pycache__`` artifact proved it),
deleted while the underlying bug was still live. It is restored here as the
fail-before / pass-after guard for the fix in ``ExecutionAgent``.

The bug: two near-simultaneous live BUYs placed TWO real exchange bids despite
``max_open_positions=1``, because the only signal that updates the open-position
count (the paper mirror) is consumed asynchronously — so the 2nd decision read a
stale 0 and passed the cap. The fix reserves an in-flight slot the moment an
entry is routed, so the burst is capped without waiting for the async mirror.
"""
from __future__ import annotations

import asyncio
import contextlib

import orjson
import pytest
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.rate_limiter import TokenBucket
from orchestration.agents.execution_agent import ExecutionAgent


class _FakeGateway:
    """Counts real bids; simulates exchange round-trip latency."""

    def __init__(self) -> None:
        self.bids = 0

    async def place_bid(self, sym: str, amount: str, rate: str, typ: str) -> dict[str, object]:
        await asyncio.sleep(0.01)  # network window where the mirror has not landed
        self.bids += 1
        return {"result": {"id": self.bids, "rec": "0.001", "amt": amount}}

    async def place_ask(self, sym: str, amount: str, rate: str, typ: str) -> dict[str, object]:
        return {"result": {"id": 0}}


class _LiveSettings:
    execution_engine = "live"
    live_trading_confirm = "I_ACCEPT_REAL_MONEY_RISK"


@pytest.mark.asyncio
async def test_live_double_entry_race() -> None:
    """Two near-simultaneous live BUYs must place at most ONE real bid when
    max_open_positions=1, even though the paper mirror that updates the
    open-position count is asynchronous."""
    bus = InMemoryEventBus()
    gw = _FakeGateway()

    paper_positions = 0

    async def paper_consumer() -> None:
        nonlocal paper_positions
        q = bus.subscribe("decisions.approved.v1")
        while True:
            raw = await q.get()
            d = orjson.loads(raw)
            if d.get("decision") == "EXECUTE" and d.get("signal") == "BUY":
                await asyncio.sleep(0.05)  # mirror lag: open count updates LATE
                paper_positions += 1

    def _live_order(_data: dict[str, object]) -> dict[str, str]:
        return {"action": "bid", "symbol": "thb_btc", "amount": "50",
                "rate": "2880000", "typ": "limit"}

    agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=_LiveSettings(),
        breaker=CircuitBreaker(),
        rate_limiter=TokenBucket(capacity=100, refill_per_sec=1000.0),
        logger=structlog.get_logger("test"),
        rest_gateway=gw,
        open_positions_fn=lambda: paper_positions,
        max_open_positions=1,
        live_order_fn=_live_order,
    )

    consumer = asyncio.create_task(paper_consumer())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)  # let both subscribe
    try:
        # Distinct ids → idempotency does NOT dedup them; this is the real shape
        # SupremeAgent emits when several strategies agree at once.
        await bus.publish("decisions.v1", b"k",
                          orjson.dumps({"decision": "EXECUTE", "signal": "BUY", "decision_id": "a"}))
        await bus.publish("decisions.v1", b"k",
                          orjson.dumps({"decision": "EXECUTE", "signal": "BUY", "decision_id": "b"}))
        await asyncio.sleep(0.3)
    finally:
        await agent.stop()
        for t in (task, consumer):
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

    assert gw.bids <= 1, (
        f"DOUBLE ENTRY: placed {gw.bids} real bids with max_open_positions=1"
    )


@pytest.mark.asyncio
async def test_inflight_reservation_releases_after_position_closes() -> None:
    """The in-flight reservation must self-heal: once a position is open and then
    closed, a later BUY is allowed again (no permanent block)."""
    bus = InMemoryEventBus()
    gw = _FakeGateway()
    open_count = 0

    def _live_order(_data: dict[str, object]) -> dict[str, str]:
        return {"action": "bid", "symbol": "thb_btc", "amount": "50",
                "rate": "2880000", "typ": "limit"}

    agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=_LiveSettings(),
        breaker=CircuitBreaker(),
        rate_limiter=TokenBucket(capacity=100, refill_per_sec=1000.0),
        logger=structlog.get_logger("test"),
        rest_gateway=gw,
        open_positions_fn=lambda: open_count,
        max_open_positions=1,
        live_order_fn=_live_order,
    )

    async def _one_buy(dec_id: str) -> None:
        await bus.publish("decisions.v1", b"k",
                          orjson.dumps({"decision": "EXECUTE", "signal": "BUY", "decision_id": dec_id}))
        await asyncio.sleep(0.1)

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    try:
        await _one_buy("one")          # places bid #1, reserves a slot
        open_count = 1                  # trader now reflects the open position
        await _one_buy("two")          # capped (1 open + 0 reserved >= 1)
        assert gw.bids == 1
        open_count = 0                  # position closed
        await _one_buy("three")        # allowed again
        assert gw.bids == 2
    finally:
        await agent.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
