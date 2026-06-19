# Layer 3 — Infrastructure (tests/infrastructure/test_metrics)
"""Unit tests for the Prometheus metrics registry and status→metrics mapping."""
from __future__ import annotations

from infrastructure.observability.metrics import MetricsRegistry, MetricType
from infrastructure.observability.status_metrics import render_status_metrics


def test_gauge_and_counter_render_with_type_and_help() -> None:
    reg = MetricsRegistry()
    reg.gauge("temp_celsius", 21, help_text="Current temperature")
    reg.counter("requests_total", 5, help_text="Total requests")
    text = reg.render()
    assert "# HELP temp_celsius Current temperature" in text
    assert "# TYPE temp_celsius gauge" in text
    assert "temp_celsius 21" in text  # whole number → no trailing .0
    assert "# TYPE requests_total counter" in text
    assert "requests_total 5" in text
    assert text.endswith("\n")


def test_labels_sorted_and_escaped() -> None:
    reg = MetricsRegistry()
    reg.gauge("http_requests", 2, labels={"method": "GET", "path": 'a"b\\c'})
    line = next(line for line in reg.render().splitlines() if line.startswith("http_requests"))
    # labels are emitted in sorted key order with the value escaped
    assert line == 'http_requests{method="GET",path="a\\"b\\\\c"} 2'


def test_float_formatting_keeps_precision_and_handles_specials() -> None:
    reg = MetricsRegistry()
    reg.gauge("equity_thb", 1234.5)
    reg.gauge("big_thb", 2_000_000.0)  # must not render in scientific notation
    reg.gauge("nan_metric", float("nan"))
    reg.gauge("inf_metric", float("inf"))
    text = reg.render()
    assert "equity_thb 1234.5" in text
    assert "big_thb 2000000" in text
    assert "nan_metric NaN" in text
    assert "inf_metric +Inf" in text


def test_empty_registry_renders_empty_string() -> None:
    assert MetricsRegistry().render() == ""
    assert MetricType.GAUGE.value == "gauge"


def test_render_status_metrics_from_list_shaped_status() -> None:
    status = {
        "uptime_seconds": 42,
        "emergency_stopped": False,
        "health": {"feed_connected": True},
        "equity": "1000.50",
        "cash": 900,
        "pnl_today": -25,
        "agents": [
            {"name": "a", "running": True, "stale": False},
            {"name": "b", "running": False, "stale": True},
        ],
    }
    text = render_status_metrics(status)
    assert "trading_uptime_seconds 42" in text
    assert "trading_agents_total 2" in text
    assert "trading_agents_running 1" in text
    assert "trading_agents_stale 1" in text
    assert "trading_feed_connected 1" in text
    assert "trading_emergency_stopped 0" in text
    assert "trading_equity_thb 1000.5" in text
    assert "trading_cash_thb 900" in text
    assert "trading_pnl_today_thb -25" in text
    assert "trading_agent_count 2" in text


def test_render_status_metrics_dict_shape_and_agent_count_override() -> None:
    status = {
        "agents": {"x": {"running": True}, "y": {"running": True, "stale": True}},
        "msg_rate": 12,
        "latency_ms": 3,
    }
    text = render_status_metrics(status, agent_count=172)
    # legacy alias must honour the override (== len(runtime.agents)), not the rows
    assert "trading_agent_count 172" in text
    assert "trading_agents_total 172" in text
    assert "trading_agents_running 2" in text
    assert "trading_msg_rate 12" in text
    assert "trading_latency_ms 3" in text


def test_render_status_metrics_tolerates_garbage_and_missing_fields() -> None:
    text = render_status_metrics({"uptime_seconds": "n/a", "agents": "oops"})
    # un-coercible uptime is omitted; bad agents shape → zero agents, no crash
    assert "trading_uptime_seconds" not in text
    assert "trading_agents_total 0" in text
