"""
FastAPI application entry point.

`create_app()` is the single source of truth for app construction — used by
the module-level `app` (for Uvicorn) and by the test fixture (for an
isolated TestClient per test session). Everything that mutates the app
(routers, middleware, lifespan) goes through this factory; nothing is stitched
on elsewhere.

The lifespan builds the cheap, always-available collaborators once at startup —
the escalation policy (which also fails fast on a malformed policy file) and the
in-process event bus — and stashes them on `app.state`. The orchestrator is
built lazily on the first pipeline request (see `api/pipeline.py`), because
wiring it loads the embedder, which is too heavy to pay at every startup.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import api_router
from backend.app.api.health import health_router
from backend.app.escalation import EscalationPolicy
from backend.app.orchestrator import PipelineEventBus
from backend.app.orchestrator.variant_registry import VariantRegistry
from backend.settings import Settings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build startup collaborators and hang them off `app.state`."""
    cfg: Settings = app.state.settings
    # Load + validate the policy once. A malformed policy fails here, at
    # startup, rather than at the first request.
    app.state.policy = EscalationPolicy.load_from_yaml(cfg.escalation.policy_path)
    # Load + validate the variant registry once, alongside the policy.
    app.state.variant_registry = VariantRegistry.load_from_yaml(cfg.pipeline.variants_path)
    app.state.event_bus = PipelineEventBus(
        grace_period_s=cfg.pipeline.event_grace_period_s,
        queue_maxsize=cfg.pipeline.event_queue_maxsize,
    )
    # Built lazily on first pipeline request; see api/pipeline.get_orchestrator_factory.
    app.state.orchestrator = None
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI instance.

    `settings` is injectable so tests can pin a known configuration without
    relying on env vars. Production callers pass nothing and get the
    defaults-plus-overlay-plus-env construction.
    """
    cfg = settings if settings is not None else Settings()

    app = FastAPI(
        title=cfg.app_name,
        lifespan=_lifespan,
        # The root path stays empty so /health and /api/* are siblings rather
        # than nested — health probes don't need to know the API prefix.
    )
    # Stash settings so the lifespan and the pipeline dependencies resolve the
    # same configuration the app was built with.
    app.state.settings = cfg

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
