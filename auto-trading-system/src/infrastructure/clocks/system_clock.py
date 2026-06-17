# Layer 3 — Infrastructure (clocks/system_clock)
"""System clock using time.time_ns() for millisecond precision."""
from __future__ import annotations

import time


class SystemClock:
    """Wall-clock implementation of the Clock port."""

    def now_ms(self) -> int:
        """Return current UTC time in milliseconds."""
        return time.time_ns() // 1_000_000
