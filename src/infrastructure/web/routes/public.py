# Layer 3 — Infrastructure (web/routes/public)
"""Public dashboard + observability + WebSocket routes (no control actions)."""
from __future__ import annotations

import asyncio
import time

import orjson
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse

from infrastructure.observability import render_status_metrics
from infrastructure.web._helpers import STATIC_DIR, check_api_key, configured_api_key
from orchestration.runtime import PipelineRuntime


def register(app: FastAPI, runtime: PipelineRuntime) -> None:
    def _render_dashboard(filename: str) -> HTMLResponse:
        """Serve a dashboard HTML with the control key injected, no-store."""
        html = (STATIC_DIR / filename).read_text(encoding="utf-8")
        # page_control_key (not configured_api_key) so a password-protected NETWORK
        # bind does not leak the control key into the page — there you must log in.
        html = html.replace("__DASHBOARD_API_KEY__", runtime.page_control_key())
        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        """The default (mini) Kingdom Prime dashboard: live price chart with the
        agent's entry/exit markers, the paper/real numbers (win rate, P&L,
        per-trade), and every control (connect, login, start/stop, kill, live,
        risk, daily target). The richer multi-page view lives at /full."""
        return _render_dashboard("mini.html")

    @app.get("/full", response_class=HTMLResponse)
    async def full_dashboard() -> HTMLResponse:
        """The full multi-page dashboard (left nav: dashboard / portfolio /
        trading / analytics / risk / agents / CEO / settings). Controls live on
        the Settings page. Same live data + API as the mini view at /."""
        return _render_dashboard("kingdom.html")

    @app.get("/api/prices/history")
    async def prices_history(request: Request) -> dict[str, object]:
        """Recent price ticks so the chart can backfill on load (WS streams live).
        Loopback is trusted; a remote client needs the key when one is set."""
        check_api_key(request, runtime)
        return {"prices": runtime.price_history()}

    @app.get("/api/trades")
    async def trades(request: Request) -> dict[str, object]:
        """Recent paper FILL/CLOSE events (per-trade entry/exit/qty/P&L). Carries
        account state, so gate it like /api/status (loopback trusted; remote needs
        the key when configured)."""
        check_api_key(request, runtime)
        return {"trades": runtime.recent_trades()}

    # P4: /healthz — liveness probe
    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"status": "ok", "ts_ms": int(time.time() * 1000)}

    # P4: /metrics — Prometheus text exposition (rich runtime metrics).
    # The legacy ``trading_agent_count`` is pinned to len(runtime.agents) so
    # existing scrapers keep working; the rest is derived from the real status.
    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        return render_status_metrics(runtime.status(), agent_count=len(runtime.agents))

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
    async def status(request: Request) -> dict[str, object]:
        # Require auth only when a real account is connected (balance data exposed).
        s = runtime.status()
        if s.get("bitkub_account_connected") and configured_api_key(runtime):
            check_api_key(request, runtime)
        return s

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
            "feed_connected": (
                health_info.get("feed_connected", False)
                if isinstance(health_info := s.get("health", {}), dict)
                else False
            ),
            "emergency_stopped": s.get("emergency_stopped", False),
        }

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
