"""ASGI entry point — exposes module-level `app` for uvicorn."""
from __future__ import annotations

from bootstrap import build_runtime
from infrastructure.web.api import create_app

app = create_app(build_runtime())
