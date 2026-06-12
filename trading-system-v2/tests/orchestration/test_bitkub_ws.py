# Layer 3 — Infrastructure (tests/orchestration/test_bitkub_ws)
"""B6 regression: BitkubWebSocketGateway backoff bounds test."""
from __future__ import annotations

from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway


def test_backoff_within_bounds_attempts_0_to_10() -> None:
    """B6: _backoff must return values in [0, cap * 1.2] for attempts 0..10."""
    gw = BitkubWebSocketGateway("wss://example.com")
    cap = gw._BACKOFF_CAP

    for attempt in range(11):
        for _ in range(20):  # run multiple times due to jitter
            delay = gw._backoff(attempt)
            assert delay >= 0.0, f"delay {delay} < 0 for attempt {attempt}"
            assert delay <= cap * 1.2, f"delay {delay} > cap*1.2 for attempt {attempt}"


def test_backoff_increases_with_attempts() -> None:
    """Backoff average should grow with attempt count (up to cap)."""
    gw = BitkubWebSocketGateway("wss://example.com")
    avg_0 = sum(gw._backoff(0) for _ in range(100)) / 100
    avg_5 = sum(gw._backoff(5) for _ in range(100)) / 100
    assert avg_5 > avg_0
