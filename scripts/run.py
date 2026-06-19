# Layer 3 — Infrastructure (scripts/run)
"""Entry point for running the trading system."""
from __future__ import annotations

import asyncio
import contextlib
import signal

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
    # Do NOT start the runtime here — create_app()'s lifespan starts it.
    # Starting twice duplicated the price supervisor task (double feed).
    app = create_app(runtime)
    config = uvicorn.Config(
        app,
        host=settings.web_host,
        port=settings.web_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)

    # Graceful shutdown: SIGTERM and SIGINT both set server.should_exit.
    loop = asyncio.get_running_loop()

    def _handle_shutdown() -> None:
        logger.info("shutdown.signal_received")
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, OSError):
            loop.add_signal_handler(sig, _handle_shutdown)

    await server.serve()
    logger.info("shutdown.complete")


if __name__ == "__main__":
    asyncio.run(main())
