"""
Claims API — submission and read access to the claims system-of-record.

`POST /api/claims` is the synchronous submission step that decouples receiving a
claim from processing it: the claim is persisted with `status='received'` before
any agent fires (the production equivalent is the Claims-of-Record system emitting
a `ClaimReceived` event). Processing is then triggered separately via the pipeline
endpoints.

Every handler offloads its blocking psycopg work to a worker thread so the event
loop stays responsive.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from backend.app.api.pipeline import get_settings
from backend.app.claims import (
    ClaimRecord,
    ClaimsRepository,
    ClaimStatus,
    ClaimSubmission,
)
from backend.app.runs import RunsRepository
from backend.app.runs.models import RunSummary
from backend.db.connection import open_connection
from backend.settings import Settings

claims_router = APIRouter(prefix="/claims", tags=["claims"])


@claims_router.post("", status_code=201, response_model=ClaimRecord)
async def submit_claim(
    submission: ClaimSubmission, settings: Settings = Depends(get_settings)
) -> ClaimRecord:
    """Persist a submitted claim with `status='received'` and return the row."""
    return await run_in_threadpool(_insert, settings, submission)


@claims_router.get("", response_model=list[ClaimRecord])
async def list_claims(
    limit: int = Query(default=50, ge=1, le=200),
    status: ClaimStatus | None = None,
    settings: Settings = Depends(get_settings),
) -> list[ClaimRecord]:
    """List claims most-recent-first, optionally filtered by status."""
    return await run_in_threadpool(_list, settings, limit, status)


@claims_router.get("/{claim_id}", response_model=ClaimRecord)
async def get_claim(
    claim_id: UUID, settings: Settings = Depends(get_settings)
) -> ClaimRecord:
    """Return one claim, or 404."""
    record = await run_in_threadpool(_get, settings, claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"claim not found: {claim_id}")
    return record


@claims_router.get("/{claim_id}/runs", response_model=list[RunSummary])
async def list_claim_runs(
    claim_id: UUID, settings: Settings = Depends(get_settings)
) -> list[RunSummary]:
    """List every run that targeted the claim, most-recent-first. 404 if no claim."""
    record = await run_in_threadpool(_get, settings, claim_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"claim not found: {claim_id}")
    return await run_in_threadpool(_list_runs, settings, claim_id)


# --------------------------------------------------------------------------- #
# Blocking helpers — each opens a short-lived connection.
# --------------------------------------------------------------------------- #


def _insert(settings: Settings, submission: ClaimSubmission) -> ClaimRecord:
    with open_connection(settings) as conn:
        return ClaimsRepository.insert(conn, submission)


def _list(
    settings: Settings, limit: int, status: ClaimStatus | None
) -> list[ClaimRecord]:
    with open_connection(settings) as conn:
        return ClaimsRepository.list_claims(conn, limit=limit, status=status)


def _get(settings: Settings, claim_id: UUID) -> ClaimRecord | None:
    with open_connection(settings) as conn:
        return ClaimsRepository.get(conn, claim_id)


def _list_runs(settings: Settings, claim_id: UUID) -> list[RunSummary]:
    with open_connection(settings) as conn:
        return RunsRepository.list_runs_for_claim(conn, claim_id)
