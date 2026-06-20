# Layer 2 — Orchestration (runtime/runtime_io)
"""External I/O side-effects: operator alerts (out) + news polling (in).

Mixin for PipelineRuntime; see orchestration.runtime for the composed class.
"""
from __future__ import annotations

import asyncio
import time

import orjson

from orchestration.runtime_base import _TOPIC_NEWS_RAW, Notifier, _RuntimeBase


class _IoMixin(_RuntimeBase):

    def _ensure_notifier(self) -> Notifier | None:
        if self._notifier is None:
            from infrastructure.alerts.notifier import AlertNotifier  # noqa: PLC0415

            self._notifier = AlertNotifier(
                telegram_bot_token=str(getattr(self.settings, "telegram_bot_token", "")),
                telegram_chat_id=str(getattr(self.settings, "telegram_chat_id", "")),
                webhook_url=str(getattr(self.settings, "alert_webhook_url", "")),
                logger=self.logger,
            )
        return self._notifier

    async def send_alert(self, message: str, level: str = "info") -> bool:
        """Send an operator alert (Telegram/webhook). Never raises."""
        notifier = self._ensure_notifier()
        if notifier is None:
            return False
        return await notifier.send(message, level)

    def _schedule_alert(self, message: str, level: str = "warning") -> None:
        """Fire an alert without blocking, if an event loop is running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.send_alert(message, level))
        self._alert_tasks.add(task)
        task.add_done_callback(self._alert_tasks.discard)

    async def _news_loop(self) -> None:
        """Poll RSS headlines, score them (pure domain), publish to news.raw.v1.

        The News Intelligence agent consumes news.raw.v1 and republishes a
        sentiment signal. Failures never crash the loop.
        """
        from domain.analytics.sentiment import classify_sentiment, score_headlines  # noqa: PLC0415

        interval = float(getattr(self.settings, "news_poll_interval_s", 120.0))
        if self._news_source is None:
            from infrastructure.gateway.news_rss import NewsRssFeed  # noqa: PLC0415

            self._news_source = NewsRssFeed()
        bus = self._ensure_bus()
        while True:
            try:
                headlines: list[str] = await self._news_source.fetch_headlines()
                if headlines:
                    score = score_headlines(headlines)
                    label = str(classify_sentiment(score))
                    payload = orjson.dumps(
                        {
                            "score": str(score),
                            "label": label,
                            "headline_count": len(headlines),
                            "sample": headlines[:5],
                        }
                    )
                    await bus.publish(_TOPIC_NEWS_RAW, b"news", payload)
                    self.last_news = {
                        "score": str(score),
                        "label": label,
                        "headline_count": len(headlines),
                        "sample": headlines[:5],
                        "ts_ms": int(time.time() * 1000),
                    }
                    self.logger.info(
                        "news.published", score=str(score), label=label, count=len(headlines)
                    )
                else:
                    self.logger.warning("news.no_headlines")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.warning("news.loop_error", exc_info=True)
            await asyncio.sleep(interval)
