# Layer 3 — Infrastructure (tests/infrastructure/test_clocks)
"""Tests for FixedClock and SystemClock."""
from __future__ import annotations

import time

from infrastructure.clocks.fixed_clock import FixedClock
from infrastructure.clocks.system_clock import SystemClock


def test_fixed_clock_returns_start_ms() -> None:
    clock = FixedClock(start_ms=1_700_000_000_000)
    assert clock.now_ms() == 1_700_000_000_000


def test_fixed_clock_advance() -> None:
    clock = FixedClock(start_ms=1_000)
    clock.advance(500)
    assert clock.now_ms() == 1_500


def test_fixed_clock_multiple_advances() -> None:
    clock = FixedClock(start_ms=0)
    clock.advance(100)
    clock.advance(200)
    assert clock.now_ms() == 300


def test_system_clock_near_real_time() -> None:
    clock = SystemClock()
    before_ms = int(time.time() * 1000)
    now = clock.now_ms()
    after_ms = int(time.time() * 1000)
    assert before_ms <= now <= after_ms + 10


def test_system_clock_monotone() -> None:
    clock = SystemClock()
    t1 = clock.now_ms()
    t2 = clock.now_ms()
    assert t2 >= t1
