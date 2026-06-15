# Layer 1 — Domain (events)
"""EventEnvelope: canonical event model for the audit log."""
from __future__ import annotations

import json

from pydantic import BaseModel


class EventEnvelope(BaseModel, frozen=True):
    """Canonical event envelope wrapping any typed event payload."""

    event_id: str
    event_type: str
    ts_ms: int
    version: int
    caused_by: str | None
    payload: dict[str, object]


def to_canonical_json(envelope: EventEnvelope) -> bytes:
    """Serialize envelope to canonical JSON bytes (sorted keys, no spaces)."""
    return json.dumps(
        envelope.model_dump(),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def from_canonical_json(data: bytes) -> EventEnvelope:
    """Deserialize canonical JSON bytes to an EventEnvelope."""
    return EventEnvelope.model_validate_json(data)
