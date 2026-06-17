# Architecture guard — EXECUTION GATE (replaces test_paper_only.py)
"""Static guarantee: live execution code is caged — not absent, but strictly isolated.

Phase 2 migration: live order code now EXISTS in bitkub_rest.py but is only
accessible through ExecutionAgent behind four mandatory gates.  This test
verifies the cage boundaries are intact.
"""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import orjson
import pytest
import structlog

from infrastructure.config import Settings

SRC = Path(__file__).resolve().parents[2] / "src"

# Bitkub private/trade API markers + generic order-placement primitives.
_ORDER_MARKERS = (
    "place-bid",
    "place-ask",
    "/api/v3/market/place",
    "cancel-order",
    "X-BTK-APIKEY",
)

_BITKUB_REST = SRC / "infrastructure/gateway/bitkub_rest.py"
_EXECUTION_AGENT = SRC / "orchestration/agents/execution_agent.py"


def _py_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


# ── Cage boundary: markers live ONLY in bitkub_rest.py ───────────────

def test_source_tree_exists() -> None:
    assert _py_files(), "src tree not found — guard would be vacuous"


def test_order_markers_only_in_bitkub_rest() -> None:
    """Order-placement markers must appear in bitkub_rest.py only."""
    offenders: list[str] = []
    for path in _py_files():
        if path == _BITKUB_REST:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in _ORDER_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(SRC)}: contains '{marker}'")
    assert not offenders, "ORDER MARKER OUTSIDE bitkub_rest.py:\n" + "\n".join(offenders)


def test_only_execution_agent_imports_bitkub_rest() -> None:
    """The signed ORDER gateway module ``bitkub_rest`` must only be referenced
    by execution_agent.py. (The read-only ``bitkub_rest_ticker`` price feed and
    the ``bitkub_rest_url`` setting are deliberately excluded — they place no
    orders.)"""
    import re  # noqa: PLC0415

    # 'bitkub_rest' NOT followed by an underscore — excludes bitkub_rest_ticker
    # and bitkub_rest_url while still catching the order-gateway module.
    pattern = re.compile(r"bitkub_rest(?!_)")
    offenders: list[str] = []
    for path in _py_files():
        if path == _BITKUB_REST:
            continue  # the module itself
        if path == _EXECUTION_AGENT:
            continue  # the allowed importer
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            offenders.append(str(path.relative_to(SRC)))
    assert not offenders, f"bitkub_rest (order gateway) referenced outside execution_agent: {offenders}"


def test_bitkub_ws_stays_read_only() -> None:
    """The websocket gateway must never contain order-placement code."""
    ws = SRC / "infrastructure/gateway/bitkub_ws.py"
    text = ws.read_text(encoding="utf-8")
    assert "websocket" in text.lower()
    for marker in ("POST", "place-bid", "place-ask", "balances", "X-BTK-APIKEY"):
        assert marker not in text, f"bitkub_ws.py must stay read-only (found {marker!r})"


def test_execution_engine_default_is_paper() -> None:
    """Settings() must default to paper engine — never live on cold start."""
    assert Settings().execution_engine == "paper"


# ── Functional gate: wrong confirm → paper path ───────────────────────

@pytest.mark.asyncio
async def test_live_gate_blocked_without_confirm() -> None:
    """ExecutionAgent with execution_engine='live' but empty confirm routes to paper.

    The mock REST gateway must NEVER be called.
    """
    from domain.risk.circuit_breaker import CircuitBreaker
    from infrastructure.eventbus.in_memory import InMemoryEventBus
    from infrastructure.gateway.rate_limiter import TokenBucket
    from orchestration.agents.execution_agent import ExecutionAgent

    bus = InMemoryEventBus()
    breaker = CircuitBreaker()
    bucket = TokenBucket(capacity=10, refill_per_sec=100.0)
    logger = structlog.get_logger("test")

    # Settings with live engine but empty confirmation token
    settings = Settings(execution_engine="live", live_trading_confirm="", persist_state=False)

    mock_called = False

    class _MockGateway:
        async def place_bid(self, *a: object, **kw: object) -> None:
            nonlocal mock_called
            mock_called = True

        async def place_ask(self, *a: object, **kw: object) -> None:
            nonlocal mock_called
            mock_called = True

    agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="paper.decisions.v1",
        settings=settings,
        breaker=breaker,
        rate_limiter=bucket,
        logger=logger,
        rest_gateway=_MockGateway(),
    )

    decision_payload = orjson.dumps(
        {"decision": "EXECUTE", "signal": "BUY", "decision_id": "test-gate-001"}
    )

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)  # wait for agent to subscribe
    try:
        await bus.publish("decisions.v1", b"key", decision_payload)
        await asyncio.sleep(0.2)
    finally:
        await agent.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Live gateway must NEVER have been called
    assert mock_called is False, "MockGateway was called — live gate should have blocked it"


# ── Preserve existing dashboard + simulator assertions ────────────────

def test_no_mock_data_in_production_dashboard() -> None:
    """Production migration: dashboard JS must not contain random/mock data generators."""
    dashboard = SRC.parent / "src/infrastructure/web/static/kingdom.html"
    text = dashboard.read_text(encoding="utf-8")
    forbidden = (
        "Math.random()",
        "1284567.89",
        "startDemoSimulator",
        "function simulateAgentMetrics() {\n  const",
    )
    offenders = [m for m in forbidden if m in text]
    assert not offenders, (
        "Mock data pattern found in production dashboard: " + ", ".join(offenders)
    )


def test_simulator_gateway_deleted() -> None:
    """The synthetic-price gateway must not exist in production src/."""
    sim_path = SRC / "infrastructure/gateway/simulator.py"
    assert not sim_path.exists(), f"{sim_path} must be deleted in Production Migration"
