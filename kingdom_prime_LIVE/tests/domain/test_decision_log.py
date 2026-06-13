"""Tests for Layer-1 domain.audit.decision_log — pure, no I/O."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.audit.decision_log import (
    SCHEMA_VERSION,
    AuditFilter,
    DecisionOutcome,
    DecisionRecord,
    canonicalize,
    is_deterministic_replay,
    replay,
)


def _rec(seq: int = 0, **overrides: object) -> DecisionRecord:
    base: dict[str, object] = {
        "ts_ms": 1_000 + seq,
        "seq": seq,
        "agent": "supreme_commander",
        "topic": "decisions.v1",
        "action": "BUY",
        "outcome": DecisionOutcome.EXECUTED,
        "confidence": Decimal("0.75"),
        "reason": "EMA crossover + RSI < 30",
        "inputs": canonicalize({"price": "1500000", "ema_fast": "1499000"}),
        "result": canonicalize({"qty": "0.0001"}),
    }
    base.update(overrides)
    return DecisionRecord(**base)  # type: ignore[arg-type]


def test_record_is_frozen() -> None:
    r = _rec()
    with pytest.raises(dataclasses_FrozenInstanceError := __import__("dataclasses").FrozenInstanceError):
        r.agent = "x"  # type: ignore[misc]


def test_confidence_must_be_decimal() -> None:
    with pytest.raises(TypeError):
        _rec(confidence=0.75)  # type: ignore[arg-type]


def test_confidence_range_enforced() -> None:
    with pytest.raises(ValueError):
        _rec(confidence=Decimal("1.01"))
    with pytest.raises(ValueError):
        _rec(confidence=Decimal("-0.01"))


def test_empty_agent_rejected() -> None:
    with pytest.raises(ValueError):
        _rec(agent="")


def test_empty_action_rejected() -> None:
    with pytest.raises(ValueError):
        _rec(action="")


def test_negative_seq_rejected() -> None:
    with pytest.raises(ValueError):
        _rec(seq=-1)


def test_canonicalize_is_sorted_and_str() -> None:
    out = canonicalize({"z": 1, "a": Decimal("2.5"), "m": True})
    assert out == (("a", "2.5"), ("m", "True"), ("z", "1"))


def test_replay_empty_yields_zero_counts() -> None:
    view = replay([])
    assert view.total_count == 0
    assert view.records == ()
    assert view.by_agent == ()
    assert view.by_outcome == ()


def test_replay_counts_by_agent_and_outcome() -> None:
    records = [
        _rec(seq=0, agent="a", outcome=DecisionOutcome.APPROVED),
        _rec(seq=1, agent="b", outcome=DecisionOutcome.REJECTED),
        _rec(seq=2, agent="a", outcome=DecisionOutcome.APPROVED),
    ]
    view = replay(records)
    assert view.total_count == 3
    assert dict(view.by_agent) == {"a": 2, "b": 1}
    assert dict(view.by_outcome) == {
        DecisionOutcome.APPROVED: 2,
        DecisionOutcome.REJECTED: 1,
    }


def test_replay_filter_by_agent() -> None:
    records = [_rec(seq=i, agent=("a" if i % 2 == 0 else "b")) for i in range(4)]
    view = replay(records, AuditFilter(agent="a"))
    assert view.total_count == 2
    assert all(r.agent == "a" for r in view.records)


def test_replay_filter_by_time_window() -> None:
    records = [_rec(seq=i, ts_ms=100 + i * 10) for i in range(5)]
    view = replay(records, AuditFilter(since_ms=120, until_ms=140))
    # ts in {100,110,120,130,140} → matches 120, 130 (inclusive since, exclusive until)
    assert [r.ts_ms for r in view.records] == [120, 130]


def test_replay_filter_by_outcome() -> None:
    records = [
        _rec(seq=0, outcome=DecisionOutcome.APPROVED),
        _rec(seq=1, outcome=DecisionOutcome.REJECTED),
        _rec(seq=2, outcome=DecisionOutcome.APPROVED),
    ]
    view = replay(records, AuditFilter(outcome=DecisionOutcome.APPROVED))
    assert view.total_count == 2


def test_what_happened_is_newest_first() -> None:
    records = [_rec(seq=i, ts_ms=i) for i in range(5)]
    view = replay(records)
    out = view.what_happened(limit=3)
    assert [r.seq for r in out] == [4, 3, 2]


def test_what_happened_limit_zero_and_negative_are_safe() -> None:
    view = replay([_rec(seq=0)])
    assert view.what_happened(limit=0) == ()
    assert view.what_happened(limit=-5) == ()


def test_who_decided_returns_first_seen_order() -> None:
    records = [
        _rec(seq=0, agent="alice", action="BUY"),
        _rec(seq=1, agent="bob",   action="BUY"),
        _rec(seq=2, agent="alice", action="BUY"),
        _rec(seq=3, agent="carol", action="SELL"),
    ]
    view = replay(records)
    assert view.who_decided("BUY") == ("alice", "bob")
    assert view.who_decided("SELL") == ("carol",)
    assert view.who_decided("UNKNOWN") == ()


def test_replay_is_deterministic_for_same_inputs() -> None:
    records = [_rec(seq=i) for i in range(20)]
    a = replay(records)
    b = replay(records)
    assert a == b
    assert is_deterministic_replay(records, list(records))


def test_replay_detects_divergent_sequences() -> None:
    base = [_rec(seq=i) for i in range(5)]
    altered = base[:-1] + [_rec(seq=99)]
    assert not is_deterministic_replay(base, altered)


def test_schema_version_is_pinned() -> None:
    """Field set is part of the contract — bump SCHEMA_VERSION on changes."""
    assert SCHEMA_VERSION == 1
    r = _rec()
    assert r.version == 1
