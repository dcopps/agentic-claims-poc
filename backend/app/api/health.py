"""
Health endpoint — small, stable surface for deployment probes and the
frontend's connectivity check. Mounted at the app root rather than under
`/api` so platform health checks don't have to know about the API prefix.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

# Distribution name as declared in pyproject.toml's `[project] name`.
# Looking it up via importlib.metadata keeps the field truthful — the
# response moves whenever the package version moves.
_DISTRIBUTION_NAME = "agentic-claims-poc"

# Sentinel returned when the package isn't installed (e.g. during a
# misconfigured CI run before `uv sync`). Surfaces the misconfiguration
# instead of pretending everything is fine.
_VERSION_UNKNOWN = "unknown"


health_router = APIRouter()


class HealthResponse(BaseModel):
    """Locked /health response shape. Adding fields is fine; removing or
    renaming requires an explicit interface-stability review."""

    status: Literal["ok"]
    version: str


@health_router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(status="ok", version=_resolve_version())


def _resolve_version() -> str:
    try:
        return version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return _VERSION_UNKNOWN
