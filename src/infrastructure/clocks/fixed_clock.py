# Layer 3 — Infrastructure (clocks/fixed_clock)
"""Fixed/test clock: deterministic time for testing."""
from __future__ import annotations


class FixedClock:
    """Test double for the Clock port with controllable time."""

    def __init__(self, start_ms: int = 1_700_000_000_000) -> None:
        self._ms = start_ms

    def now_ms(self) -> int:
        """Return the current fixed time in milliseconds."""
        return self._ms

    def advance(self, ms: int) -> None:
        """Advance the clock by ms milliseconds."""
        self._ms += ms
