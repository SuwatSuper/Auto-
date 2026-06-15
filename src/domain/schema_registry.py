# Layer 1 — Domain (schema_registry)
"""In-code schema registry + backward-compatibility contracts.

The spec calls for "backward-compatible event schemas". We implement that intent
(not a Protobuf transport) as a registry of canonical message contracts: each
contract pins the REQUIRED fields that consumers depend on. The backward-compat
test enforces the rule —
  • adding a NEW field is allowed (forward-compatible), but
  • removing / renaming a REQUIRED field FAILS the test —
and checks it against the REAL producers, so a silent breaking change is caught.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class MessageContract:
    """A canonical message type and the fields consumers require of it."""

    name: str
    required_fields: frozenset[str]

    def missing_fields(self, payload: Mapping[str, object]) -> list[str]:
        """Required fields absent from ``payload`` (empty == compatible)."""
        return sorted(f for f in self.required_fields if f not in payload)

    def is_compatible(self, payload: Mapping[str, object]) -> bool:
        """True when every required field is present (extra fields are fine)."""
        return not self.missing_fields(payload)


CONTRACTS: dict[str, MessageContract] = {
    "event_envelope": MessageContract(
        "event_envelope",
        frozenset({"event_id", "event_type", "ts_ms", "version", "caused_by", "payload"}),
    ),
    "signal": MessageContract("signal", frozenset({"signal", "price", "ts_ms", "source"})),
    "decision": MessageContract("decision", frozenset({"decision", "signal"})),
    "treasury": MessageContract(
        "treasury",
        frozenset({"cash", "realized_pnl", "realized_today", "wins", "losses", "halted"}),
    ),
    "reconciliation": MessageContract(
        "reconciliation", frozenset({"type", "ts_ms", "reconciled", "balances"}),
    ),
}


def contract(name: str) -> MessageContract:
    """Look up a registered contract by name (KeyError if unknown)."""
    return CONTRACTS[name]
