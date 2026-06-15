# Layer 3 — Infrastructure (web/api)
"""FastAPI app factory. Wires middleware, CORS, static files, and delegates the
route definitions to the ``routes`` package (public / ceo / control)."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from infrastructure.web._helpers import STATIC_DIR, check_rate_limit
from infrastructure.web.routes import ceo, control, public
from orchestration.runtime import PipelineRuntime


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
    async def security_headers(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Rate limiting
        ip = request.client.host if request.client else "unknown"
        if not check_rate_limit(ip):
            return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)
        response = await call_next(request)
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

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Route groups (each closes over the live runtime).
    public.register(app, runtime)
    ceo.register(app, runtime)
    control.register(app, runtime)

    return app
