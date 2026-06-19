# Layer 1 — Domain (tests/contracts/test_schema_compat)
"""Automated backward-compatibility tests for the event/message schemas.

Enforces the contract rule end-to-end:
  • adding a NEW field is backward-compatible (parses, value preserved/ignored)
  • removing/renaming a REQUIRED field FAILS
and checks the registry against the REAL producers (Supreme, Treasury), so a
silent breaking change to a published message is caught here.
"""
from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal

import orjson
import pytest
import structlog
from pydantic import ValidationError

from domain.events import EventEnvelope, from_canonical_json, to_canonical_json
from domain.portfolio.treasury import TreasuryLimits
from domain.schema_registry import CONTRACTS
from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.supreme import SupremeAgent
from orchestration.agents.treasury_agent import TreasuryAgent


def _envelope() -> EventEnvelope:
    return EventEnvelope(
        event_id="e1", event_type="SIGNAL", ts_ms=1, version=1, caused_by=None,
        payload={"a": 1},
    )


# ── EventEnvelope: add = ok, remove = fail ───────────────────────────
def test_event_envelope_roundtrips() -> None:
    e = _envelope()
    assert from_canonical_json(to_canonical_json(e)) == e


def test_adding_a_payload_field_is_backward_compatible() -> None:
    data = orjson.loads(to_canonical_json(_envelope()))
    data["payload"]["new_field"] = "added-in-a-later-version"  # NEW field
    restored = from_canonical_json(orjson.dumps(data))
    assert restored.payload["new_field"] == "added-in-a-later-version"  # preserved


def test_removing_a_required_field_fails() -> None:
    data = orjson.loads(to_canonical_json(_envelope()))
    del data["version"]  # remove/rename a required top-level field
    with pytest.raises(ValidationError):
        from_canonical_json(orjson.dumps(data))


# ── Registry validator: add = ok, remove = fail ──────────────────────
def test_registry_flags_missing_required_field() -> None:
    decision = CONTRACTS["decision"]
    assert decision.is_compatible({"decision": "EXECUTE", "signal": "BUY"})
    assert decision.missing_fields({"decision": "EXECUTE"}) == ["signal"]  # remove = fail
    assert decision.is_compatible({"decision": "EXECUTE", "signal": "BUY", "extra": 1})  # add = ok


# ── Real producers must keep their contracts ─────────────────────────
async def test_real_supreme_decision_satisfies_contract() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("out")
    agent = SupremeAgent(bus=bus, topic_in="in", topic_out="out", logger=structlog.get_logger("t"))
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("in", b"k", orjson.dumps({"signal": "BUY", "source": "s", "ts_ms": 1}))
    await asyncio.sleep(0.08)
    await agent.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    msg = orjson.loads(out.get_nowait())
    assert CONTRACTS["decision"].is_compatible(msg), CONTRACTS["decision"].missing_fields(msg)


async def test_real_treasury_event_satisfies_contract() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("treasury.v1")
    treasury = TreasuryAgent(
        bus, "treasury.v1", structlog.get_logger("t"),
        TreasuryLimits(initial_capital=Decimal("1000")),
    )
    task = asyncio.create_task(treasury.start())
    await asyncio.sleep(0.1)
    await treasury.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    msg = orjson.loads(out.get_nowait())
    assert CONTRACTS["treasury"].is_compatible(msg), CONTRACTS["treasury"].missing_fields(msg)
