# Layer 3 — Infrastructure (alerts/notifier)
"""Outbound alert notifier: Telegram bot or generic webhook.

Fires short messages when the system needs the operator's attention (breaker
tripped, loss limit hit, agent crash, Bitkub disconnect, live order placed).
Network-free in tests: the HTTP client is injected; if none is configured the
notifier is a no-op that still records the last message for inspection.
"""
from __future__ import annotations

import contextlib

import httpx
import structlog


class AlertNotifier:
    """Sends alerts via Telegram (token+chat_id) or a webhook URL.

    Construction is cheap and side-effect-free. send() never raises — delivery
    failures are logged and swallowed so alerting can never crash trading.
    """

    def __init__(
        self,
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
        webhook_url: str = "",
        client: httpx.AsyncClient | None = None,
        logger: structlog.BoundLogger | None = None,
    ) -> None:
        self._tg_token = telegram_bot_token
        self._tg_chat = telegram_chat_id
        self._webhook = webhook_url
        self._client = client
        self._log = (logger or structlog.get_logger()).bind(component="alerts")
        self.last_message: str | None = None
        self.sent_count: int = 0

    @property
    def configured(self) -> bool:
        """True when at least one delivery channel is set up."""
        return bool((self._tg_token and self._tg_chat) or self._webhook)

    async def send(self, message: str, level: str = "info") -> bool:
        """Send an alert. Returns True if a channel accepted it.

        Never raises. Always records last_message regardless of delivery.
        """
        self.last_message = message
        if not self.configured:
            self._log.info("alert.not_configured", message=message, level=level)
            return False

        client = self._client or httpx.AsyncClient(timeout=10.0)
        owns = self._client is None
        delivered = False
        try:
            if self._tg_token and self._tg_chat:
                url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
                resp = await client.post(
                    url, json={"chat_id": self._tg_chat, "text": message}
                )
                delivered = delivered or (resp.status_code == 200)
            if self._webhook:
                resp = await client.post(
                    self._webhook, json={"text": message, "level": level}
                )
                delivered = delivered or (200 <= resp.status_code < 300)
        except Exception as exc:  # delivery must never crash the caller
            self._log.warning("alert.delivery_failed", error=str(exc))
        finally:
            if owns:
                with contextlib.suppress(Exception):
                    await client.aclose()
        if delivered:
            self.sent_count += 1
        return delivered
