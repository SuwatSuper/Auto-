# Layer 3 — Infrastructure (web/api)
from __future__ import annotations

import asyncio
import hmac
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import orjson
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from orchestration.runtime import PipelineRuntime

_STATIC_DIR = Path(__file__).parent / "static"

# P4: simple in-memory rate limiter (IP → (window_start, count))
_rate_store: dict[str, tuple[float, int]] = {}
_RATE_LIMIT = 100  # requests per window
_RATE_WINDOW = 60.0  # seconds


def _check_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    window_start, count = _rate_store.get(ip, (now, 0))
    if now - window_start > _RATE_WINDOW:
        _rate_store[ip] = (now, 1)
        return True
    if count >= _RATE_LIMIT:
        return False
    _rate_store[ip] = (window_start, count + 1)
    return True


def _configured_api_key(runtime: PipelineRuntime) -> str:
    """Read the control-plane key from settings ('' = guard disabled)."""
    raw = getattr(runtime.settings, "dashboard_api_key", None)
    if raw is None:
        return ""
    secret = getattr(raw, "get_secret_value", None)
    value = secret() if callable(secret) else raw
    return str(value)


def _check_api_key(request: Request, runtime: PipelineRuntime) -> None:
    """401 on POST control endpoints when a key is configured and missing/wrong."""
    expected = _configured_api_key(runtime)
    if not expected:
        return
    provided = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


# ── CEO serializers (Layer-3 adapters — no logic, pure mapping) ────────
def _agent_report_to_dict(report: object) -> dict[str, object]:
    return {
        "name": report.name,
        "role": report.role,
        "health": report.health.value,
        "detail": report.detail,
        "restarts": report.restarts,
        "msg_count": report.msg_count,
    }


def _executive_summary_to_dict(es: object) -> dict[str, object]:
    business = es.business
    risk = es.risk
    health = es.health
    return {
        "ts_ms": es.ts_ms,
        "agents": [_agent_report_to_dict(a) for a in es.agents],
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


def _decision_record_to_dict(r: object) -> dict[str, object]:
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


def create_app(runtime: PipelineRuntime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Production migration: only 'live' is supported. The Bitkub WS gateway
        # auto-reconnects with backoff on failure. The dashboard surfaces
        # "DATA UNAVAILABLE" until the first real tick arrives.
        await runtime.start("live")
        yield
        await runtime.stop()

    app = FastAPI(lifespan=lifespan)

    # P4: security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next: object) -> object:
        # Rate limiting
        ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(ip):
            return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:;"
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        """Kingdom Prime dashboard. The control-plane key is injected so the
        page can authenticate its own POST calls; the page is only reachable
        by whoever can reach this server (CORS locked to localhost)."""
        html = (_STATIC_DIR / "kingdom.html").read_text(encoding="utf-8")
        return html.replace("__DASHBOARD_API_KEY__", _configured_api_key(runtime))

    @app.get("/classic", response_class=HTMLResponse)
    async def classic() -> str:
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

    # P4: /healthz — liveness probe
    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"status": "ok", "ts_ms": int(time.time() * 1000)}

    # P4: /metrics — Prometheus-style text metrics
    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        status = runtime.status()
        uptime = status.get("uptime_seconds", 0)
        msg_rate = status.get("msg_rate", 0)
        latency = status.get("latency_ms", 0)
        agent_count = len(runtime.agents)
        lines = [
            "# HELP trading_uptime_seconds Total uptime in seconds",
            "# TYPE trading_uptime_seconds gauge",
            f"trading_uptime_seconds {uptime}",
            "# HELP trading_msg_rate Messages per second",
            "# TYPE trading_msg_rate gauge",
            f"trading_msg_rate {msg_rate}",
            "# HELP trading_latency_ms Latency in milliseconds",
            "# TYPE trading_latency_ms gauge",
            f"trading_latency_ms {latency}",
            "# HELP trading_agent_count Number of registered agents",
            "# TYPE trading_agent_count gauge",
            f"trading_agent_count {agent_count}",
        ]
        return "\n".join(lines) + "\n"

    # P4: /api/timeline — recent event timeline
    @app.get("/api/timeline")
    async def timeline() -> dict[str, object]:
        status = runtime.status()
        return {
            "ts_ms": int(time.time() * 1000),
            "mode": status.get("mode", "unknown"),
            "uptime_seconds": status.get("uptime_seconds", 0),
            "agents": status.get("agents", {}),
        }

    @app.get("/api/status")
    async def status() -> dict[str, object]:
        return runtime.status()

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        """Detailed health check: agent counts, feed status, uptime."""
        s = runtime.status()
        # runtime.status() returns "agents" as a LIST of per-agent dicts
        # (see PipelineRuntime._agent_status). Accept a dict too for safety.
        raw_agents: object = s.get("agents", [])
        if isinstance(raw_agents, dict):
            agent_list: list[dict[str, object]] = [
                {"name": name, **(info if isinstance(info, dict) else {})}
                for name, info in raw_agents.items()
            ]
        elif isinstance(raw_agents, list):
            agent_list = [a for a in raw_agents if isinstance(a, dict)]
        else:
            agent_list = []
        stale = [
            str(a.get("name", "?")) for a in agent_list if a.get("stale", False)
        ]
        return {
            "status": "ok",
            "ts_ms": int(time.time() * 1000),
            "uptime_seconds": s.get("uptime_seconds", 0),
            "agent_count": len(agent_list),
            "running_agents": len(
                [a for a in agent_list if a.get("running", False)]
            ),
            "stale_agents": stale,
            "feed_connected": s.get("health", {}).get("feed_connected", False),  # type: ignore[union-attr]
            "emergency_stopped": s.get("emergency_stopped", False),
        }

    # ── CEO Executive Reporting endpoints (Production Migration) ─────────
    @app.get("/api/ceo/summary")
    async def ceo_summary() -> dict[str, object]:
        """Top-level executive view. Returns 503 with explicit reason if CEO
        agent is not yet running — NEVER fabricates data (Production rule)."""
        ceo = runtime.ceo
        if ceo is None:
            raise HTTPException(
                status_code=503,
                detail="CEO agent not initialized — runtime has not started",
            )
        es = ceo.executive_summary()
        return _executive_summary_to_dict(es)

    @app.get("/api/ceo/audit")
    async def ceo_audit(
        limit: int = 100,
        agent: str | None = None,
        action: str | None = None,
    ) -> dict[str, object]:
        """Replayable audit trail. Answers
        'เกิดอะไรขึ้น / ใครตัดสินใจ / ตัดสินใจจากข้อมูลอะไร / ผลลัพธ์เป็นอย่างไร'."""
        ceo = runtime.ceo
        if ceo is None:
            raise HTTPException(status_code=503, detail="CEO agent not initialized")
        from domain.audit.decision_log import AuditFilter  # noqa: PLC0415

        flt = AuditFilter(agent=agent, action=action) \
            if (agent or action) else None
        view = ceo.audit_view(flt)
        recent = view.what_happened(limit=max(1, min(limit, 1000)))
        return {
            "total_count": view.total_count,
            "by_agent": [{"agent": a, "count": c} for a, c in view.by_agent],
            "by_outcome": [{"outcome": o.value, "count": c} for o, c in view.by_outcome],
            "records": [_decision_record_to_dict(r) for r in recent],
        }

    @app.get("/api/ceo/agents")
    async def ceo_agents() -> dict[str, object]:
        """Per-agent health + role view for the CEO dashboard tab."""
        ceo = runtime.ceo
        if ceo is None:
            raise HTTPException(status_code=503, detail="CEO agent not initialized")
        es = ceo.executive_summary()
        return {
            "ts_ms": es.ts_ms,
            "agents": [_agent_report_to_dict(a) for a in es.agents],
        }

    @app.post("/api/mode/{mode}")
    async def switch_mode(mode: str, request: Request) -> dict[str, object]:
        _check_api_key(request, runtime)
        # Production migration: simulator/paper/demo modes were removed.
        # The endpoint is retained for API stability — clients sending
        # "live" get an OK; everything else gets a clear 400.
        if mode != "live":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"mode {mode!r} is not supported — this build runs in 'live' "
                    "mode only (simulator/paper/demo removed in Production Migration)"
                ),
            )
        return {"ok": True, "mode": "live"}

    @app.post("/api/agents/{name}/start")
    async def start_agent(name: str, request: Request) -> dict[str, object]:
        _check_api_key(request, runtime)
        await runtime.start_agent(name)
        return {"ok": True}

    @app.post("/api/agents/{name}/stop")
    async def stop_agent(name: str, request: Request) -> dict[str, object]:
        _check_api_key(request, runtime)
        await runtime.stop_agent(name)
        return {"ok": True}

    @app.post("/api/agents/start_all")
    async def start_all(request: Request) -> dict[str, object]:
        _check_api_key(request, runtime)
        for name in runtime.agents:
            await runtime.start_agent(name)
        return {"ok": True}

    @app.post("/api/agents/stop_all")
    async def stop_all(request: Request) -> dict[str, object]:
        _check_api_key(request, runtime)
        for name in runtime.agents:
            await runtime.stop_agent(name)
        return {"ok": True}

    @app.post("/api/emergency_stop")
    async def emergency_stop(request: Request) -> dict[str, object]:
        _check_api_key(request, runtime)
        await runtime.emergency_stop()
        return {"ok": True}

    @app.post("/api/emergency_reset")
    async def emergency_reset(request: Request) -> dict[str, object]:
        _check_api_key(request, runtime)
        await runtime.emergency_reset()
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        # P4: WS origin validation
        origin = websocket.headers.get("origin", "")
        host = websocket.headers.get("host", "")
        port = str(getattr(runtime.settings, "web_port", 8000))
        allowed_origins = {
            "",
            f"http://{host}",
            f"https://{host}",
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
        }
        if origin and origin not in allowed_origins:
            await websocket.close(code=4403)
            return

        await websocket.accept()
        topic: str = getattr(runtime.settings, "prices_topic", "prices.thb_btc.v1")
        queue = runtime.bus.subscribe(topic)

        async def _forward_prices() -> None:
            while True:
                value = await queue.get()
                payload: dict[str, object] = orjson.loads(value)
                await websocket.send_json({"type": "price", "data": payload})

        async def _send_status() -> None:
            while True:
                await asyncio.sleep(1.0)
                await websocket.send_json({"type": "status", "data": runtime.status()})

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(_forward_prices())
                tg.create_task(_send_status())
        except* WebSocketDisconnect:
            pass
        except* Exception:
            pass
        finally:
            runtime.bus.unsubscribe(topic, queue)

    return app
