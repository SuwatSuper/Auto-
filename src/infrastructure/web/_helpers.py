# Layer 3 — Infrastructure (web/_helpers)
"""Shared web helpers: static path, rate limiting, auth gate, and the CEO
serializers (pure Layer-3 adapters — no logic, just mapping domain → JSON)."""
from __future__ import annotations

import hmac
import time
from pathlib import Path

from fastapi import HTTPException, Request

from domain.audit.decision_log import DecisionRecord
from domain.reporting.ceo_report import AgentReport, ExecutiveSummary
from orchestration.runtime import PipelineRuntime

STATIC_DIR = Path(__file__).parent / "static"

# P4: simple in-memory rate limiter (IP → (window_start, count))
_rate_store: dict[str, tuple[float, int]] = {}
_RATE_LIMIT = 100  # requests per window
_RATE_WINDOW = 60.0  # seconds
_RATE_MAX_IPS = 4096  # reap stale IPs past this so the table can't grow forever

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def check_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    # Opportunistic eviction: stale IPs (window long expired) are never removed
    # otherwise, so over a long run with many distinct clients the dict would
    # grow without bound. Sweep only when it gets large to keep this O(1) amortised.
    if len(_rate_store) > _RATE_MAX_IPS:
        for stale_ip in [k for k, (ws, _) in _rate_store.items() if now - ws > _RATE_WINDOW]:
            del _rate_store[stale_ip]
    window_start, count = _rate_store.get(ip, (now, 0))
    if now - window_start > _RATE_WINDOW:
        _rate_store[ip] = (now, 1)
        return True
    if count >= _RATE_LIMIT:
        return False
    _rate_store[ip] = (window_start, count + 1)
    return True


def _secret_value(raw: object) -> str:
    """Extract a plain string from a pydantic SecretStr (or str / None)."""
    if raw is None:
        return ""
    secret = getattr(raw, "get_secret_value", None)
    value = secret() if callable(secret) else raw
    return str(value)


def configured_api_key(runtime: PipelineRuntime) -> str:
    """Effective control-plane key ('' = guard disabled).

    Delegates to ``runtime.control_key()`` which returns the configured
    DASHBOARD_API_KEY, or a per-process auto key for a loopback (local) bind so
    the local dashboard works without manual key handling. Non-loopback binds
    still require an explicit key (enforced at startup by assert_safe_bind)."""
    fn = getattr(runtime, "control_key", None)
    if callable(fn):
        return str(fn())
    return _secret_value(getattr(runtime.settings, "dashboard_api_key", None))


def configured_password(runtime: PipelineRuntime) -> str:
    """Read the operator password from settings ('' = login not configured)."""
    return _secret_value(getattr(runtime.settings, "dashboard_password", None))


def assert_safe_bind(settings: object) -> None:
    """Fail-closed startup guard (T1): refuse to bind a non-loopback host
    (e.g. 0.0.0.0 for phone/LAN access) unless a control credential is set.

    Without this, exposing the dashboard to the network would leave the whole
    control plane (live switch / credentials / orders) open with no auth.
    """
    host = str(getattr(settings, "web_host", "127.0.0.1"))
    if host in _LOOPBACK_HOSTS:
        return
    has_credential = bool(
        _secret_value(getattr(settings, "dashboard_api_key", None))
        or _secret_value(getattr(settings, "dashboard_password", None))
    )
    if not has_credential:
        raise RuntimeError(
            f"refusing to bind non-loopback host {host!r} without "
            "DASHBOARD_PASSWORD/DASHBOARD_API_KEY (fail-closed)"
        )


def is_local_request(request: Request) -> bool:
    """True when the request comes from the same machine (loopback)."""
    client = request.client
    return bool(client and client.host in _LOOPBACK_HOSTS)


def check_api_key(request: Request, runtime: PipelineRuntime) -> None:
    """Auth gate for ordinary control endpoints.

    The dashboard is a single-user local control room: requests from the same
    machine (localhost) are always trusted and need no key. A key is only
    required when the dashboard is reached from another machine over the
    network (and DASHBOARD_API_KEY is set).
    """
    if is_local_request(request):
        return
    expected = configured_api_key(runtime)
    if not expected:
        return
    provided = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


def check_api_key_strict(request: Request, runtime: PipelineRuntime) -> None:
    """Auth gate for live / credential / order / close / kill endpoints.

    The dashboard is a single-user local control room: a request from the same
    machine (loopback) is trusted and needs NO key, so the operator drives every
    control — including arming live — straight from the dashboard with zero key
    handling and zero .env editing. A remote / LAN client still requires a valid
    ``X-API-Key`` (and the fail-closed bind guard forces a credential to exist for
    any non-loopback bind), so the control plane is never open over the network.

    Removing the key on localhost does not remove live-trading safety: arming live
    still needs the typed confirm string, and orders still pass the hard per-order
    cap, the kill switch, and the treasury / circuit-breaker gates.
    """
    if is_local_request(request):
        return
    expected = configured_api_key(runtime)
    if not expected:
        raise HTTPException(
            status_code=401,
            detail=(
                "control endpoint locked — reach it from this machine (localhost) "
                "or set DASHBOARD_API_KEY / log in to authorize remote access"
            ),
        )
    provided = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


# ── CEO serializers (Layer-3 adapters — no logic, pure mapping) ────────
def agent_report_to_dict(report: AgentReport) -> dict[str, object]:
    return {
        "name": report.name,
        "role": report.role,
        "health": report.health.value,
        "detail": report.detail,
        "restarts": report.restarts,
        "msg_count": report.msg_count,
    }


def executive_summary_to_dict(es: ExecutiveSummary) -> dict[str, object]:
    business = es.business
    risk = es.risk
    health = es.health
    return {
        "ts_ms": es.ts_ms,
        "agents": [agent_report_to_dict(a) for a in es.agents],
        "business": {
            "portfolio_value": (
                str(business.portfolio_value) if business.portfolio_value is not None else None
            ),
            "portfolio_value_availability": business.portfolio_value_availability.value,
            "cash": str(business.cash) if business.cash is not None else None,
            "cash_availability": business.cash_availability.value,
            "pnl_total": str(business.pnl_total) if business.pnl_total is not None else None,
            "pnl_today": str(business.pnl_today) if business.pnl_today is not None else None,
            "allocation_pct": [{"symbol": s, "pct": str(p)} for s, p in business.allocation_pct],
        },
        "risk": {
            "drawdown_pct": str(risk.drawdown_pct),
            "daily_loss_pct": str(risk.daily_loss_pct),
            "risk_level": risk.risk_level.value,
            "concentration_alerts": list(risk.concentration_alerts),
            "emergency_stopped": risk.emergency_stopped,
            "treasury_halted": risk.treasury_halted,
        },
        "health": {
            "feed_connected": health.feed_connected,
            "feed_age_ms": health.feed_age_ms,
            "crashed_agents": list(health.crashed_agents),
            "stale_agents": list(health.stale_agents),
            "total_agents": health.total_agents,
            "running_agents": health.running_agents,
        },
    }


def decision_record_to_dict(r: DecisionRecord) -> dict[str, object]:
    return {
        "ts_ms": r.ts_ms,
        "seq": r.seq,
        "agent": r.agent,
        "topic": r.topic,
        "action": r.action,
        "outcome": r.outcome.value,
        "confidence": str(r.confidence),
        "reason": r.reason,
        "inputs": [{"key": k, "value": v} for k, v in r.inputs],
        "result": [{"key": k, "value": v} for k, v in r.result],
        "version": r.version,
    }
