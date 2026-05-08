"""
FastAPI application entry point.

`create_app()` is the single source of truth for app construction — used by
the module-level `app` (for Uvicorn) and by the test fixture (for an
isolated TestClient per test session). Everything that mutates the app
(routers, middleware) goes through this factory; nothing is stitched on
elsewhere.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import api_router
from backend.app.api.health import health_router
from backend.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI instance.

    `settings` is injectable so tests can pin a known configuration without
    relying on env vars. Production callers pass nothing and get the
    defaults-plus-overlay-plus-env construction.
    """
    cfg = settings if settings is not None else Settings()

    app = FastAPI(
        title=cfg.app_name,
        # The root path stays empty so /health and /api/* are siblings rather
        # than nested — health probes don't need to know the API prefix.
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(api_router)

    return app


# Module-level instance for `uv run uvicorn backend.app.main:app`.
app = create_app()
