# Layer 3 — Infrastructure (tests/infrastructure/test_perf_guard)
"""Performance regression guard. Budgets are deliberately conservative (≈10–40×
below the measured baseline) so they catch a real regression without flaking on
a slow CI runner. Baseline (dev box): bus ≈1.2M msgs/s, backtest ≈617 bars/s,
gate p95 ≈2.5 µs — see `python scripts/bench.py`."""
from __future__ import annotations

from infrastructure.perf.bench import bench_backtest, bench_event_bus, bench_gate_latency


def test_event_bus_throughput_within_budget() -> None:
    rate = bench_event_bus(20_000)
    assert rate >= 50_000, f"event bus regressed: {rate:,.0f} msgs/sec (budget 50,000)"


def test_backtest_throughput_within_budget() -> None:
    rate = bench_backtest(2_000)
    assert rate >= 100, f"backtest regressed: {rate:,.0f} bars/sec (budget 100)"


def test_entry_gate_latency_within_budget() -> None:
    _p50, p95 = bench_gate_latency(10_000)
    assert p95 <= 200.0, f"entry-gate latency regressed: p95 {p95:.1f} µs (budget 200)"
