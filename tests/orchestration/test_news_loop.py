# Tests — runtime news loop scores headlines and feeds the news agent
from __future__ import annotations

import asyncio
import contextlib

import orjson
import pytest
import structlog

from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime


class _FakeNews:
    async def fetch_headlines(self):
        return ["Bitcoin surges to record high", "ETF inflows soar"]


@pytest.mark.asyncio
async def test_news_loop_publishes_score_to_bus():
    rt = PipelineRuntime(
        settings=Settings(persist_state=False, news_poll_interval_s=0.2),
        logger=structlog.get_logger("t"),
    )
    rt._news_source = _FakeNews()
    bus = rt._ensure_bus()
    q = bus.subscribe("news.raw.v1")
    task = asyncio.create_task(rt._news_loop())
    msg = await asyncio.wait_for(q.get(), timeout=3)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    data = orjson.loads(msg)
    assert float(data["score"]) > 0  # bullish headlines
    assert data["headline_count"] == 2
    # surfaced for the dashboard
    assert rt.last_news["label"] in ("BULLISH", "VERY_BULLISH")
