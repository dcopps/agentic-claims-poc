"""
Runs API — read access to reconstructed past runs and their comparison.

Every run is reconstructed purely from the audit_log, so these endpoints write
nothing. `compare` exists for the side-by-side variant view: it reconstructs two
runs and diffs them, guarding that both target the same claim.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from backend.app.api.pipeline import get_settings
from backend.app.orchestrator import PipelineResult
from backend.app.runs import (
    RunClaimMismatchError,
    RunComparison,
    RunNotFoundError,
    RunsRepository,
)
from backend.db.connection import open_connection
from backend.settings import Settings

runs_router = APIRouter(prefix="/runs", tags=["runs"])


# `/compare/...` is declared before `/{correlation_id}` so the literal segment is
# matched first rather than being parsed as a (failing) correlation id.
@runs_router.get("/compare/{correlation_id_a}/{correlation_id_b}", response_model=RunComparison)
async def compare_runs(
    correlation_id_a: UUID,
    correlation_id_b: UUID,
    settings: Settings = Depends(get_settings),
) -> RunComparison:
    """Reconstruct two runs of the same claim and return them with their diff."""
    try:
        return await run_in_threadpool(
            _compare, settings, correlation_id_a, correlation_id_b
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RunClaimMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@runs_router.get("/{correlation_id}", response_model=PipelineResult)
async def get_run(
    correlation_id: UUID, settings: Settings = Depends(get_settings)
) -> PipelineResult:
    """Reconstruct one completed run, or 404."""
    result = await run_in_threadpool(_get_run, settings, correlation_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"run not found: {correlation_id}"
        )
    return result


def _get_run(settings: Settings, correlation_id: UUID) -> PipelineResult | None:
    with open_connection(settings) as conn:
        return RunsRepository.get_run(conn, correlation_id)


def _compare(settings: Settings, cid_a: UUID, cid_b: UUID) -> RunComparison:
    with open_connection(settings) as conn:
        return RunsRepository.compare(conn, cid_a, cid_b)
