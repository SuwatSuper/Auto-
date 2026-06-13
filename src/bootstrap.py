# Layer 3 — Infrastructure (bootstrap)
"""Composition root: wires ports and concrete adapters into a PipelineRuntime."""
from __future__ import annotations

import structlog

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.runtime import PipelineRuntime


def build_runtime(settings: Settings | None = None) -> PipelineRuntime:
    """Build a PipelineRuntime with real infrastructure adapters."""
    if settings is None:
        settings = Settings()

    logger = structlog.get_logger("runtime")

    # Concrete adapters — all wired here, never inside orchestration/domain
    _bus = InMemoryEventBus()
    _clock = SystemClock()
    _state_store = InMemoryStateStore()
    _event_store = InMemoryEventStore()

    return PipelineRuntime(settings=settings, logger=logger)
