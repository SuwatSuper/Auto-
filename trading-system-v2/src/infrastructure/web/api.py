from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import orjson
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles

from orchestration.runtime import PipelineRuntime

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(runtime: PipelineRuntime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield
        await runtime.stop()

    app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

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

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = runtime.bus.subscribe(runtime.settings.prices_topic)
        try:
            while True:
                try:
                    value = await asyncio.wait_for(queue.get(), timeout=1.0)
                    payload: dict[str, object] = orjson.loads(value)
                    await websocket.send_json({"type": "price", "data": payload})
                except TimeoutError:
                    await websocket.send_json({"type": "status", "data": runtime.status()})
        except WebSocketDisconnect:
            pass
        finally:
            runtime.bus.unsubscribe(runtime.settings.prices_topic, queue)

    return app
