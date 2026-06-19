# Layer 1 — Domain (tests/domain/test_events)
"""Tests for EventEnvelope serialization."""
from __future__ import annotations

import json

from domain.events import EventEnvelope, from_canonical_json, to_canonical_json


def _envelope(**kwargs: object) -> EventEnvelope:
    defaults: dict[str, object] = {
        "event_id": "evt-001",
        "event_type": "PriceUpdated",
        "ts_ms": 1_700_000_000_000,
        "version": 1,
        "caused_by": None,
        "payload": {"price": "1500000.00", "symbol": "THB_BTC"},
    }
    defaults.update(kwargs)
    return EventEnvelope(**defaults)  # type: ignore[arg-type]


def test_to_canonical_json_is_bytes() -> None:
    env = _envelope()
    data = to_canonical_json(env)
    assert isinstance(data, bytes)


def test_to_canonical_json_sorted_keys() -> None:
    env = _envelope()
    data = to_canonical_json(env)
    parsed = json.loads(data)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_roundtrip() -> None:
    env = _envelope()
    data = to_canonical_json(env)
    recovered = from_canonical_json(data)
    assert recovered.event_id == env.event_id
    assert recovered.event_type == env.event_type
    assert recovered.ts_ms == env.ts_ms
    assert recovered.caused_by == env.caused_by


def test_caused_by_set() -> None:
    env = _envelope(caused_by="parent-evt-001")
    data = to_canonical_json(env)
    recovered = from_canonical_json(data)
    assert recovered.caused_by == "parent-evt-001"
