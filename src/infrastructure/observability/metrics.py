# Layer 3 — Infrastructure (observability/metrics)
"""Dependency-free Prometheus text-exposition metrics registry.

A tiny in-memory registry for counters and gauges with optional labels, rendered
to the Prometheus text exposition format (v0.0.4). No ``prometheus_client``
dependency — the /metrics endpoint and any future exporter share this one
renderer. Pure and deterministic: given the same samples it renders the same
text, so it is fully unit-testable.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class MetricType(StrEnum):
    """Prometheus metric types this registry can render."""

    COUNTER = "counter"
    GAUGE = "gauge"


@dataclass(frozen=True)
class _Sample:
    value: float
    labels: tuple[tuple[str, str], ...]


@dataclass
class _Metric:
    name: str
    mtype: MetricType
    help_text: str
    samples: list[_Sample] = field(default_factory=list)


def _escape_label_value(value: str) -> str:
    """Escape a label value per the Prometheus text format (\\, \", newline)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{_escape_label_value(v)}"' for k, v in labels)
    return "{" + inner + "}"


def _fmt(value: float) -> str:
    """Render a float the way Prometheus expects (ints without a trailing .0)."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if value == int(value):
        return str(int(value))
    return repr(value)


def _norm_labels(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


class MetricsRegistry:
    """Collects counter/gauge samples and renders them as Prometheus text.

    Metric families are rendered in first-seen order so output is stable.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}

    def _record(
        self,
        name: str,
        mtype: MetricType,
        value: float,
        help_text: str,
        labels: Mapping[str, str] | None,
    ) -> None:
        metric = self._metrics.get(name)
        if metric is None:
            metric = _Metric(name=name, mtype=mtype, help_text=help_text)
            self._metrics[name] = metric
        elif help_text and not metric.help_text:
            metric.help_text = help_text
        metric.samples.append(_Sample(value=float(value), labels=_norm_labels(labels)))

    def gauge(
        self,
        name: str,
        value: float,
        *,
        help_text: str = "",
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Record a gauge sample (a value that can go up or down)."""
        self._record(name, MetricType.GAUGE, value, help_text, labels)

    def counter(
        self,
        name: str,
        value: float,
        *,
        help_text: str = "",
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Record a counter sample (a monotonically increasing total)."""
        self._record(name, MetricType.COUNTER, value, help_text, labels)

    def render(self) -> str:
        """Render all recorded metrics as Prometheus text exposition format."""
        out: list[str] = []
        for metric in self._metrics.values():
            if metric.help_text:
                out.append(f"# HELP {metric.name} {metric.help_text}")
            out.append(f"# TYPE {metric.name} {metric.mtype.value}")
            for sample in metric.samples:
                out.append(f"{metric.name}{_render_labels(sample.labels)} {_fmt(sample.value)}")
        return "\n".join(out) + ("\n" if out else "")
