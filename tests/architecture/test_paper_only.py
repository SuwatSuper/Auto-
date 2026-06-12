# Architecture guard — PAPER ONLY
"""Static guarantee: no code path can ever place a real order.

The user's mandate: simulated trading with a 1,000 THB budget — never live.
This test scans every source file for Bitkub order-placement endpoints and
order-signing primitives. If anyone ever adds live execution code, this
test turns red BEFORE the system can spend real money.
"""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

# Bitkub private/trade API markers + generic order-placement primitives.
FORBIDDEN = (
    "place-bid",
    "place-ask",
    "/api/v3/market/place",
    "/api/market/place",
    "cancel-order",
    "create_order(",
    "X-BTK-APIKEY",   # Bitkub private API auth header
)


def _py_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_source_tree_exists() -> None:
    assert _py_files(), "src tree not found — guard would be vacuous"


def test_no_live_order_execution_paths() -> None:
    offenders: list[str] = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN:
            if marker in text:
                offenders.append(f"{path.relative_to(SRC)}: contains '{marker}'")
    assert not offenders, "LIVE ORDER PATH DETECTED:\n" + "\n".join(offenders)


def test_bitkub_adapter_is_market_data_only() -> None:
    """The only Bitkub touchpoint is the public market-data websocket."""
    ws = SRC.parent / "src/infrastructure/gateway/bitkub_ws.py"
    text = ws.read_text(encoding="utf-8")
    assert "wss://api-ws.bitkub.com" in text or "websocket" in text.lower()
    for marker in ("POST", "place-bid", "place-ask", "balances", "X-BTK-APIKEY"):
        assert marker not in text, f"bitkub_ws.py must stay read-only (found {marker})"


def test_no_mock_data_in_production_dashboard() -> None:
    """Production migration: dashboard JS must not contain random/mock data
    generators. Tests must use the FakePriceFeed in tests/_fixtures/ only.
    """
    dashboard = SRC.parent / "src/infrastructure/web/static/kingdom.html"
    text = dashboard.read_text(encoding="utf-8")
    forbidden = (
        "Math.random()",
        "1284567.89",
        "startDemoSimulator",
        "function simulateAgentMetrics() {\n  const",  # fake metric drift body
    )
    offenders = [m for m in forbidden if m in text]
    assert not offenders, (
        "Mock data pattern found in production dashboard: " + ", ".join(offenders)
    )


def test_simulator_gateway_deleted() -> None:
    """The synthetic-price gateway must not exist in production src/."""
    sim_path = SRC / "infrastructure/gateway/simulator.py"
    assert not sim_path.exists(), f"{sim_path} must be deleted in Production Migration"
