"""Shared test wiring — provides a fake price feed via deps so tests do not
depend on the (removed) production simulator gateway."""
from __future__ import annotations

import pytest
import structlog

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed


class _NoNetworkNewsFeed:
    """Drop-in for NewsRssFeed that performs NO network I/O (test isolation)."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def fetch_headlines(self) -> list[str]:
        return []


@pytest.fixture(autouse=True)
def _no_real_rss(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop the runtime's news loop from hitting real RSS feeds during tests.

    ``_news_loop`` imports ``NewsRssFeed`` lazily and constructs it with the
    DEFAULT live feeds when no source is injected — that made integration tests
    perform real (egress-blocked) network calls that could stall the suite.
    Patching the module attribute swaps in a no-network fake for that lazy
    import, while ``test_news_rss`` (which imports the real class at module load)
    is unaffected and still exercises the real parser/fetcher with its own mock.
    """
    monkeypatch.setattr(
        "infrastructure.gateway.news_rss.NewsRssFeed", _NoNetworkNewsFeed, raising=True
    )


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
