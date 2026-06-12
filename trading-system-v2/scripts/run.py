"""Entry point: pipeline + dashboard."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog
import uvicorn

from infrastructure.config import get_settings
from infrastructure.logging import configure_logging
from infrastructure.web.api import create_app
from orchestration.runtime import PipelineRuntime


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AI Trading Platform — Phase 1")
    p.add_argument("--simulator", action="store_true", help="Use simulator instead of live Bitkub")
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)

    log = structlog.get_logger()

    runtime = PipelineRuntime(settings, log)
    mode = "simulator" if args.simulator else "live"
    await runtime.start(mode)

    app = create_app(runtime)
    config = uvicorn.Config(
        app,
        host=settings.web_host,
        port=settings.web_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    log.info("dashboard_ready", url=f"http://{settings.web_host}:{settings.web_port}", mode=mode)
    print(
        f"\n  Dashboard → http://{settings.web_host}:{settings.web_port}\n"
        f"  Mode      → {mode}\n"
        f"  Ctrl+C to stop\n"
    )

    try:
        await server.serve()
    finally:
        await runtime.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
    sys.exit(0)
