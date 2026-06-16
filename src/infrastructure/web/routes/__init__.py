# Layer 3 — Infrastructure (web/routes)
"""HTTP/WebSocket route groups for the Kingdom Prime dashboard API.

Each module exposes ``register(app, runtime)`` which attaches its routes to the
shared FastAPI app, closing over the live ``PipelineRuntime``.
"""
