# Layer 3 — Infrastructure (bootstrap)
"""Composition root: builds a PipelineRuntime from Settings.

The runtime owns its own adapter wiring (event bus, SQLite state store, price
feed, live gateway) and builds them lazily from Settings, so this entry point
stays a thin composition root.
"""
from __future__ import annotations

import structlog

from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime


def build_runtime(settings: Settings | None = None) -> PipelineRuntime:
    """Build a PipelineRuntime with real infrastructure adapters."""
    if settings is None:
        settings = Settings()

    logger = structlog.get_logger("runtime")
    return PipelineRuntime(settings=settings, logger=logger)
