# Layer 3 — Infrastructure (web/api)
from __future__ import annotations

import asyncio
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


def create_app(runtime: PipelineRuntime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

    @app.post("/api/mode/{mode}")
    async def switch_mode(mode: str) -> dict[str, object]:
        if mode not in ("live", "simulator"):
            raise HTTPException(400, "mode must be 'live' or 'simulator'")
        await runtime.switch_mode(mode)
        return {"ok": True, "mode": mode}

    @app.post("/api/agents/{name}/start")
    async def start_agent(name: str) -> dict[str, object]:
        await runtime.start_agent(name)
        return {"ok": True}

    @app.post("/api/agents/{name}/stop")
    async def stop_agent(name: str) -> dict[str, object]:
        await runtime.stop_agent(name)
        return {"ok": True}

    @app.post("/api/agents/start_all")
    async def start_all() -> dict[str, object]:
        for name in runtime.agents:
            await runtime.start_agent(name)
        return {"ok": True}

    @app.post("/api/agents/stop_all")
    async def stop_all() -> dict[str, object]:
        for name in runtime.agents:
            await runtime.stop_agent(name)
        return {"ok": True}

    @app.post("/api/emergency_stop")
    async def emergency_stop() -> dict[str, object]:
        await runtime.emergency_stop()
        return {"ok": True}

    @app.post("/api/emergency_reset")
    async def emergency_reset() -> dict[str, object]:
        await runtime.emergency_reset()
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        # P4: WS origin validation
        origin = websocket.headers.get("origin", "")
        allowed_origins = {"http://localhost:8000", "http://127.0.0.1:8000", ""}
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
