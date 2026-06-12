# Layer 3 — Infrastructure (scripts/run)
"""Entry point for running the trading system."""
from __future__ import annotations

import asyncio

import structlog
import uvicorn

from infrastructure.config import get_settings
from infrastructure.logging import configure_logging
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("run")

    runtime = PipelineRuntime(settings, logger)
    await runtime.start("simulator")

    app = create_app(runtime)
    config = uvicorn.Config(
        app,
        host=settings.web_host,
        port=settings.web_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
