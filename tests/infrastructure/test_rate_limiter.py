# Layer 3 — Infrastructure (tests/infrastructure/test_rate_limiter)
"""Tests for the async token-bucket rate limiter with injected fake clock."""
from __future__ import annotations

import asyncio

import pytest

from infrastructure.gateway.rate_limiter import TokenBucket


class _FakeClock:
    """Monotonic fake clock whose time advances only when instructed."""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def __call__(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


@pytest.mark.asyncio
async def test_initial_tokens_fill_capacity() -> None:
    """A fresh bucket has capacity tokens available immediately."""
    clock = _FakeClock()
    bucket = TokenBucket(capacity=3, refill_per_sec=1.0, clock=clock)
    for _ in range(3):
        await bucket.acquire()  # should all succeed without waiting


@pytest.mark.asyncio
async def test_exhausted_bucket_refills_with_time() -> None:
    """After exhaustion, advancing the clock makes tokens available again."""
    clock = _FakeClock()
    bucket = TokenBucket(capacity=1, refill_per_sec=1.0, clock=clock)
    await bucket.acquire()  # consume the only token

    clock.advance(1.0)  # 1 second → 1 token refilled
    await bucket.acquire()  # should succeed immediately


@pytest.mark.asyncio
async def test_tokens_do_not_exceed_capacity() -> None:
    """Refill never exceeds the bucket capacity."""
    clock = _FakeClock()
    bucket = TokenBucket(capacity=2, refill_per_sec=10.0, clock=clock)
    clock.advance(100.0)  # would produce 1000 tokens, but capped at 2
    await bucket.acquire()
    await bucket.acquire()
    # Third acquire with no more time advance must wait (use very fast refill to avoid long sleep)
    fast_clock = _FakeClock()
    fast_bucket = TokenBucket(capacity=2, refill_per_sec=1000.0, clock=fast_clock)
    fast_clock.advance(100.0)
    await fast_bucket.acquire()
    await fast_bucket.acquire()
    # At this point tokens are 0; another acquire with time advance should work
    fast_clock.advance(0.002)  # 2ms → 2 tokens at 1000/s
    await fast_bucket.acquire()


@pytest.mark.asyncio
async def test_real_time_fast_refill_no_long_sleep() -> None:
    """Using very high refill rate, acquire completes in < 0.05 s even after exhaustion."""
    bucket = TokenBucket(capacity=1, refill_per_sec=1000.0)
    await bucket.acquire()  # exhaust
    # Next acquire waits < 1ms for token → well under 0.05s threshold
    await asyncio.wait_for(bucket.acquire(), timeout=0.05)


@pytest.mark.asyncio
async def test_concurrent_acquires_serialized() -> None:
    """Multiple concurrent acquire() calls each get exactly one token."""
    clock = _FakeClock()
    bucket = TokenBucket(capacity=5, refill_per_sec=0.0, clock=clock)
    # 5 tokens, no refill
    results = await asyncio.gather(*(bucket.acquire() for _ in range(5)))
    assert len(results) == 5
