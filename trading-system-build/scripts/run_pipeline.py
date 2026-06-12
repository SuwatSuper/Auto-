from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys

import structlog

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from infrastructure.config import get_settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway
from infrastructure.gateway.simulator import SimulatorGateway
from infrastructure.logging import configure_logging
from orchestration.agents.sample_agent import SampleAgent
from orchestration.supervisors.price_supervisor import PriceSupervisor


async def main(use_simulator: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger("run_pipeline")

    bus = InMemoryEventBus()

    if use_simulator:
        feed = SimulatorGateway()
        log.info("pipeline.mode", mode="simulator")
    else:
        feed = BitkubWebSocketGateway(settings.bitkub_ws_url)
        log.info("pipeline.mode", mode="live", url=settings.bitkub_ws_url)

    supervisor = PriceSupervisor(feed, bus, settings.prices_topic, log)
    agent = SampleAgent(bus, settings.prices_topic, log)

    loop = asyncio.get_running_loop()

    def _shutdown(sig: signal.Signals) -> None:
        log.info("pipeline.shutdown_signal", signal=sig.name)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _shutdown, sig)

    with contextlib.suppress(asyncio.CancelledError, KeyboardInterrupt):
        await asyncio.gather(supervisor.run(), agent.start())

    print("Pipeline stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Trading Platform — Phase 1 Pipeline")
    parser.add_argument("--simulator", action="store_true", help="Use offline simulator")
    args = parser.parse_args()

    try:
        asyncio.run(main(use_simulator=args.simulator))
    except KeyboardInterrupt:
        print("Pipeline stopped.")
    sys.exit(0)
