"""Shared test wiring — provides a fake price feed via deps so tests do not
depend on the (removed) production simulator gateway."""
from __future__ import annotations

import sys
import types

# Provide a minimal pandas_ta stub when the real package is not installed.
# This lets the test suite run on Python 3.11 where pandas_ta requires 3.12.
if "pandas_ta" not in sys.modules:
    _stub = types.ModuleType("pandas_ta")
    _stub.__version__ = "0.0.0-stub"  # type: ignore[attr-defined]
    sys.modules["pandas_ta"] = _stub

import structlog

from infrastructure.config import Settings
from infrastructure.clocks.system_clock import SystemClock
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed


def make_test_runtime(**settings_overrides: object) -> PipelineRuntime:
    """Build a PipelineRuntime wired with a FakePriceFeed test fixture.

    Tests should prefer this helper instead of `PipelineRuntime(...)` so the
    runtime never tries to open a real Bitkub websocket from CI.
    """
    defaults: dict[str, object] = {
        "persist_state": False,
        "initial_capital": "1000",
        "prices_topic": "prices.thb_btc.v1",
    }
    defaults.update(settings_overrides)
    settings = Settings(**defaults)  # type: ignore[arg-type]
    bus = InMemoryEventBus()
    deps = RuntimeDeps(
        bus=bus,
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic=str(defaults["prices_topic"]),
    )
    return PipelineRuntime(settings, structlog.get_logger("test"), deps=deps)
