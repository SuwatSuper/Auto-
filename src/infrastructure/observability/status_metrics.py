# Layer 3 — Infrastructure (observability/status_metrics)
"""Map a PipelineRuntime status snapshot to Prometheus metrics text.

Pure transform: a status mapping in, metrics text out (no I/O, no runtime
coupling). Every field is read defensively so a partial/old status shape never
500s the /metrics endpoint — a value that can't be coerced is simply omitted.
"""
from __future__ import annotations

from collections.abc import Mapping

from infrastructure.observability.metrics import MetricsRegistry


def _num(value: object) -> float | None:
    """Coerce a status value to float; bools → 1/0; un-coercible → None."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _agent_rows(status: Mapping[str, object]) -> list[dict[str, object]]:
    """Normalise status['agents'] (list-of-dicts OR dict-of-dicts) to a list."""
    raw = status.get("agents", [])
    if isinstance(raw, Mapping):
        return [
            {"name": name, **(info if isinstance(info, Mapping) else {})}
            for name, info in raw.items()
        ]
    if isinstance(raw, list):
        return [a for a in raw if isinstance(a, dict)]
    return []


def render_status_metrics(
    status: Mapping[str, object], *, agent_count: int | None = None
) -> str:
    """Render a runtime status snapshot as Prometheus text.

    ``agent_count`` overrides the agent total for the legacy
    ``trading_agent_count`` gauge so it always matches ``len(runtime.agents)``.
    """
    reg = MetricsRegistry()

    uptime = _num(status.get("uptime_seconds"))
    if uptime is not None:
        reg.gauge("trading_uptime_seconds", uptime, help_text="Process uptime in seconds")

    rows = _agent_rows(status)
    total = agent_count if agent_count is not None else len(rows)
    running = sum(1 for a in rows if a.get("running"))
    stale = sum(1 for a in rows if a.get("stale"))
    reg.gauge("trading_agents_total", float(total), help_text="Registered agents")
    reg.gauge("trading_agents_running", float(running), help_text="Agents currently running")
    reg.gauge("trading_agents_stale", float(stale), help_text="Agents flagged stale")

    health = status.get("health")
    if isinstance(health, Mapping):
        feed = _num(health.get("feed_connected"))
        if feed is not None:
            reg.gauge("trading_feed_connected", feed, help_text="Price feed connected (1/0)")

    emergency = _num(status.get("emergency_stopped"))
    if emergency is not None:
        reg.gauge(
            "trading_emergency_stopped", emergency, help_text="Emergency stop active (1/0)"
        )

    money_fields = (
        ("equity", "trading_equity_thb", "Account equity in THB"),
        ("cash", "trading_cash_thb", "Account cash in THB"),
        ("pnl_today", "trading_pnl_today_thb", "Realized+unrealized PnL today in THB"),
    )
    for key, metric, help_text in money_fields:
        value = _num(status.get(key))
        if value is not None:
            reg.gauge(metric, value, help_text=help_text)

    legacy_fields = (
        ("msg_rate", "trading_msg_rate", "Messages processed per second"),
        ("latency_ms", "trading_latency_ms", "Processing latency in milliseconds"),
    )
    for key, metric, help_text in legacy_fields:
        value = _num(status.get(key))
        if value is not None:
            reg.gauge(metric, value, help_text=help_text)

    # Legacy alias kept for existing scrapers/tests: must equal len(runtime.agents).
    reg.gauge("trading_agent_count", float(total), help_text="Registered agents (legacy alias)")
    return reg.render()
