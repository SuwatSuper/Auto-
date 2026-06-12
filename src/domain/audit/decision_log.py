# Layer 1 — Domain (audit/decision_log)
"""Immutable, append-only decision record + replayable audit query API.

Pure Python. No I/O. No frameworks. Every CEO-level question
("เกิดอะไรขึ้น? / ใครตัดสินใจ? / ตัดสินใจจากข้อมูลอะไร? / ผลลัพธ์? / ย้อนเวลาแล้วเหมือนเดิมไหม?")
must be answerable from a sequence of DecisionRecords alone.

Determinism contract:
    Given the same sequence of DecisionRecords appended in the same order,
    replay(...) MUST return an identical AuditView every time.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Final


class DecisionOutcome(StrEnum):
    """Closed set of decision results — never expands silently (extensibility via version bump)."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


# Stable schema version — never rename/remove fields; bump on additions (event design rule).
SCHEMA_VERSION: Final[int] = 1


@dataclasses.dataclass(frozen=True, slots=True)
class DecisionRecord:
    """One immutable line in the decision ledger.

    Fields are intentionally minimal and stable. Anything additional must
    arrive through inputs/result (free-form dicts of primitives) — never by
    adding/renaming top-level fields without bumping SCHEMA_VERSION.
    """

    ts_ms: int                  # monotonic-ish event timestamp (ms since epoch)
    seq: int                    # monotonically increasing within a log
    agent: str                  # who proposed the decision
    topic: str                  # event topic / decision domain (e.g. "decisions.v1")
    action: str                 # what was proposed (e.g. "BUY", "REJECT_ORDER")
    outcome: DecisionOutcome    # what actually happened
    confidence: Decimal         # 0.0 .. 1.0 — agent's stated confidence
    reason: str                 # human-readable justification (≤ 500 chars expected)
    inputs: tuple[tuple[str, str], ...]   # canonical (key, value) inputs used — sorted
    result: tuple[tuple[str, str], ...]   # canonical (key, value) result — sorted
    version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        # Cheap invariants — never use floats for confidence in audit records
        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence must be Decimal (no floats in audit records)")
        if self.confidence < Decimal("0") or self.confidence > Decimal("1"):
            raise ValueError(f"confidence out of range: {self.confidence}")
        if self.seq < 0:
            raise ValueError(f"seq must be >= 0, got {self.seq}")
        if self.ts_ms < 0:
            raise ValueError(f"ts_ms must be >= 0, got {self.ts_ms}")
        if not self.agent:
            raise ValueError("agent must not be empty")
        if not self.action:
            raise ValueError("action must not be empty")


def canonicalize(items: dict[str, object]) -> tuple[tuple[str, str], ...]:
    """Project any dict of primitives into the canonical, deterministic key/value tuple.

    Determinism is non-negotiable for audit replay — strings are coerced via str()
    and the tuple is sorted by key. Nested structures are str()-ified (best effort);
    callers SHOULD pre-flatten complex values for human readability.
    """
    return tuple(sorted((k, str(v)) for k, v in items.items()))


@dataclasses.dataclass(frozen=True, slots=True)
class AuditFilter:
    """Filter for replay() — all fields are AND-combined; None means 'any'."""

    agent: str | None = None
    topic: str | None = None
    action: str | None = None
    outcome: DecisionOutcome | None = None
    since_ms: int | None = None    # inclusive
    until_ms: int | None = None    # exclusive

    def matches(self, r: DecisionRecord) -> bool:
        if self.agent is not None and r.agent != self.agent:
            return False
        if self.topic is not None and r.topic != self.topic:
            return False
        if self.action is not None and r.action != self.action:
            return False
        if self.outcome is not None and r.outcome != self.outcome:
            return False
        if self.since_ms is not None and r.ts_ms < self.since_ms:
            return False
        if self.until_ms is not None and r.ts_ms >= self.until_ms:
            return False
        return True


@dataclasses.dataclass(frozen=True, slots=True)
class AuditView:
    """Read-only projection of the ledger answering the CEO's five questions."""

    records: tuple[DecisionRecord, ...]
    total_count: int
    by_agent: tuple[tuple[str, int], ...]
    by_outcome: tuple[tuple[DecisionOutcome, int], ...]

    def what_happened(self, limit: int = 50) -> tuple[DecisionRecord, ...]:
        """Most-recent-first slice. Answers 'เกิดอะไรขึ้น?'."""
        return tuple(reversed(self.records))[:max(0, limit)]

    def who_decided(self, action: str) -> tuple[str, ...]:
        """Distinct agents who emitted this action, in first-seen order.

        Answers 'ใครเป็นคนตัดสินใจ?' for a given action.
        """
        seen: dict[str, None] = {}
        for r in self.records:
            if r.action == action and r.agent not in seen:
                seen[r.agent] = None
        return tuple(seen)


def replay(records: Iterable[DecisionRecord], flt: AuditFilter | None = None) -> AuditView:
    """Deterministically project an ordered DecisionRecord stream into an AuditView.

    Determinism: same input sequence → identical output. Used both at run-time
    (for live dashboards) and at audit time ("ย้อนเวลาแล้วระบบจะตัดสินใจเหมือนเดิมหรือไม่?").
    """
    flt = flt or AuditFilter()
    materialized: list[DecisionRecord] = []
    agent_counts: dict[str, int] = {}
    outcome_counts: dict[DecisionOutcome, int] = {}

    for r in records:
        if not flt.matches(r):
            continue
        materialized.append(r)
        agent_counts[r.agent] = agent_counts.get(r.agent, 0) + 1
        outcome_counts[r.outcome] = outcome_counts.get(r.outcome, 0) + 1

    return AuditView(
        records=tuple(materialized),
        total_count=len(materialized),
        by_agent=tuple(sorted(agent_counts.items())),
        by_outcome=tuple(sorted(outcome_counts.items(), key=lambda kv: kv[0].value)),
    )


def is_deterministic_replay(a: Sequence[DecisionRecord], b: Sequence[DecisionRecord]) -> bool:
    """Two record sequences yield equal AuditViews iff they are equal as tuples.

    Provides a single, named answer to 'ย้อนเวลากลับไป ระบบจะตัดสินใจเหมือนเดิมหรือไม่?'.
    """
    return tuple(a) == tuple(b)
