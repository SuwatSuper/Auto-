# Layer 3 — Infrastructure (web/routes/public)
"""Public dashboard + observability + WebSocket routes (no control actions)."""
from __future__ import annotations

import asyncio
import time

import orjson
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse

from infrastructure.web._helpers import STATIC_DIR, check_api_key, configured_api_key
from orchestration.runtime import PipelineRuntime


def register(app: FastAPI, runtime: PipelineRuntime) -> None:
    def _render_dashboard(filename: str) -> HTMLResponse:
        """Serve a dashboard HTML with the control key injected, no-store."""
        html = (STATIC_DIR / filename).read_text(encoding="utf-8")
        html = html.replace("__DASHBOARD_API_KEY__", configured_api_key(runtime))
        return HTMLResponse(
            content=html,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        """Minimal Kingdom Prime dashboard: a real live price chart with the
        agent's entry/exit markers + the paper/real numbers (win rate, P&L,
        per-trade). The full control room remains at /full."""
        return _render_dashboard("mini.html")

    @app.get("/full", response_class=HTMLResponse)
    async def full() -> HTMLResponse:
        """The full-featured control room (former default dashboard)."""
        return _render_dashboard("kingdom.html")

    @app.get("/classic", response_class=HTMLResponse)
    async def classic() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

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
