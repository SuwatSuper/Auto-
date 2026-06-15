# Layer 2 — Orchestration (ports/clock)
"""Clock port: abstracts wall-clock time for testability."""
from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    """Returns current time in milliseconds since Unix epoch."""

    def now_ms(self) -> int:
        """Return current time in milliseconds."""
        ...
