# Layer 1 — Domain (risk/circuit_breaker)
"""Pure circuit-breaker state machine: no I/O, no datetime.now()."""
from __future__ import annotations

import contextlib
from collections.abc import Callable
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
        # Optional persistence hook: the runtime sets this to a callback that
        # snapshots the breaker to disk on every state change, so a TRIPPED
        # breaker SURVIVES A RESTART — the operator (not a silent restart) must
        # be the one to reset it. Pure-domain default is None (no I/O).
        self.on_change: Callable[[], None] | None = None

    def _notify(self) -> None:
        """Fire the persistence hook (best-effort) after any state change."""
        if self.on_change is not None:
            self.on_change()

    def trip(self, reason: str, now: int) -> None:
        """Open the circuit breaker and record the trip event."""
        self._open = True
        self._trip_history.append((now, reason))
        self._notify()

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

    def record_trade(self, realized_pnl: Decimal, now: int = 0) -> None:
        """Record a completed trade outcome.

        Increments the consecutive-loss counter on negative PnL and resets it
        on positive PnL. Auto-trips when the counter reaches the threshold —
        unless the threshold is ``0`` (UNLIMITED), in which case the streak is
        still counted for display but never trips the breaker.

        ``now`` (epoch seconds) is stamped on an auto-trip so the audit trail in
        ``trip_history`` carries the real time, not 1970. Callers that don't have
        a clock may omit it (defaults to 0).
        """
        changed = False
        if realized_pnl < Decimal(0):
            self._consecutive_losses += 1
            changed = True
            if (
                self._max_consecutive_losses > 0
                and self._consecutive_losses >= self._max_consecutive_losses
            ):
                self.trip("CONSECUTIVE_LOSSES", now)  # trip() already notifies
                return
        elif realized_pnl > Decimal(0):
            if self._consecutive_losses != 0:
                changed = True
            self._consecutive_losses = 0
        if changed:
            self._notify()

    def reset(self, token: str, now: int) -> bool:
        """Attempt to close the circuit breaker.

        Returns True and closes the breaker only when the token equals the
        hard-coded confirmation string.  No time-based auto-reset ever occurs.
        """
        if token != self._RESET_TOKEN:
            return False
        self._open = False
        self._consecutive_losses = 0
        self._notify()
        return True

    @property
    def trip_history(self) -> tuple[tuple[int, str], ...]:
        """Immutable record of every trip event as (epoch_seconds, reason)."""
        return tuple(self._trip_history)

    # ── Persistence (so a tripped breaker survives a restart) ────────────
    def to_dict(self) -> dict[str, object]:
        """Serialize the breaker state to a JSON-safe dict."""
        return {
            "open": self._open,
            "consecutive_losses": self._consecutive_losses,
            "max_consecutive_losses": self._max_consecutive_losses,
            "trip_history": [[int(ts), str(r)] for ts, r in self._trip_history],
        }

    def load_dict(self, data: dict[str, object]) -> None:
        """Restore breaker state from :meth:`to_dict` (best-effort, tolerant).

        Does NOT fire the persistence hook (restoring is not a new event) and
        does NOT overwrite the live ``max_consecutive_losses`` threshold, which
        the operator's control settings own — only the tripped/streak/history
        state is restored.
        """
        if not isinstance(data, dict):
            return
        self._open = bool(data.get("open", self._open))
        streak = data.get("consecutive_losses", self._consecutive_losses)
        if isinstance(streak, int):
            self._consecutive_losses = streak
        hist = data.get("trip_history")
        if isinstance(hist, list):
            restored: list[tuple[int, str]] = []
            for item in hist:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    with contextlib.suppress(TypeError, ValueError):
                        restored.append((int(item[0]), str(item[1])))
            self._trip_history = restored
