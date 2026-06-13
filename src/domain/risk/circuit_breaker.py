# Layer 1 — Domain (risk/circuit_breaker)
"""Pure circuit-breaker state machine: no I/O, no datetime.now()."""
from __future__ import annotations

from decimal import Decimal


class CircuitBreaker:
    """Stateful circuit breaker for trading halt logic.

    Time is always injected as an integer epoch-seconds argument.
    There is no time-based auto-reset — only manual reset with the confirmation token.
    """

    _RESET_TOKEN: str = "MANUAL_RESET_CONFIRMED"

    def __init__(self, max_consecutive_losses: int = 5) -> None:
        self._open: bool = False
        self._max_consecutive_losses: int = max_consecutive_losses
        self._consecutive_losses: int = 0
        self._trip_history: list[tuple[int, str]] = []

    def trip(self, reason: str, now: int) -> None:
        """Open the circuit breaker and record the trip event."""
        self._open = True
        self._trip_history.append((now, reason))

    @property
    def is_open(self) -> bool:
        """True when the circuit breaker is open and trading is halted."""
        return self._open

    @property
    def consecutive_losses(self) -> int:
        """Current consecutive-loss count (for dashboard display)."""
        return self._consecutive_losses

    @property
    def max_consecutive_losses(self) -> int:
        """Active consecutive-loss threshold (for dashboard display)."""
        return self._max_consecutive_losses

    def update_threshold(self, max_consecutive_losses: int) -> None:
        """Change the consecutive-loss threshold live (operator control).

        ``0`` means UNLIMITED — the breaker never auto-trips on a losing streak
        (ปลดลิมิตเบรกเกอร์เป็นไม่จำกัด). Negative values are rejected.
        """
        if max_consecutive_losses < 0:
            raise ValueError("max_consecutive_losses must be >= 0 (0 = unlimited)")
        self._max_consecutive_losses = max_consecutive_losses

    @property
    def unlimited(self) -> bool:
        """True when the auto-trip threshold is disabled (0 = unlimited)."""
        return self._max_consecutive_losses <= 0

    def record_trade(self, realized_pnl: Decimal) -> None:
        """Record a completed trade outcome.

        Increments the consecutive-loss counter on negative PnL and resets it
        on positive PnL. Auto-trips when the counter reaches the threshold —
        unless the threshold is ``0`` (UNLIMITED), in which case the streak is
        still counted for display but never trips the breaker.
        """
        if realized_pnl < Decimal(0):
            self._consecutive_losses += 1
            if (
                self._max_consecutive_losses > 0
                and self._consecutive_losses >= self._max_consecutive_losses
            ):
                self.trip("CONSECUTIVE_LOSSES", 0)
        elif realized_pnl > Decimal(0):
            self._consecutive_losses = 0

    def reset(self, token: str, now: int) -> bool:
        """Attempt to close the circuit breaker.

        Returns True and closes the breaker only when the token equals the
        hard-coded confirmation string.  No time-based auto-reset ever occurs.
        """
        if token != self._RESET_TOKEN:
            return False
        self._open = False
        self._consecutive_losses = 0
        return True

    @property
    def trip_history(self) -> tuple[tuple[int, str], ...]:
        """Immutable record of every trip event as (epoch_seconds, reason)."""
        return tuple(self._trip_history)
