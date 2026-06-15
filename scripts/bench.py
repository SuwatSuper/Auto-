# scripts/bench.py — print the performance baseline for the hot paths
"""Usage: python scripts/bench.py
Measures event-bus throughput, backtest bars/sec, and entry-gate latency."""
from __future__ import annotations


def main() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from infrastructure.perf.bench import run_all

    r = run_all()
    print("== Kingdom Prime — performance benchmark ==")
    print(f"event bus publish throughput : {r.event_bus_msgs_per_sec:>12,.0f} msgs/sec")
    print(f"backtest engine throughput   : {r.backtest_bars_per_sec:>12,.0f} bars/sec")
    print(f"entry-gate latency p50 / p95 : {r.gate_latency_p50_us:>8.2f} / {r.gate_latency_p95_us:.2f} µs")


if __name__ == "__main__":
    main()
