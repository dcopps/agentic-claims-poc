"""
Human decision API — capture a reviewer's approve/reject on an escalated claim.

When a claim is `awaiting_human`, a reviewer decides its fate. The decision is
written as an audit entry with `agent="human"` (the *who* and *why* in the
tamper-evident ledger) under the claim's most recent run's correlation_id, and the
claim's status is moved to a terminal state — `settled` on approval, `aborted` on
rejection. No new `claim_status` values: the *reason* lives in the audit entry.

**Unauthenticated in the prototype.** Production gates this on an Entra ID role;
here it is open by design, flagged as a production gap to close.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from backend.app.api.pipeline import get_settings
from backend.app.audit import AuditEvent, AuditWriter
from backend.app.claims import ClaimRecord, ClaimsRepository
from backend.app.runs import RunsRepository
from backend.db.connection import open_connection
from backend.settings import Settings

human_router = APIRouter(prefix="/claims", tags=["human"])

# Audit step identifiers + status mapping for a human decision. Locked.
_STEP_APPROVAL = "human_approval"
_STEP_REJECTION = "human_rejection"
_STATUS_ON_APPROVAL = "settled"
_STATUS_ON_REJECTION = "aborted"
# Only a claim in this status may receive a human decision.
_DECIDABLE_STATUS = "awaiting_human"


class HumanDecision(BaseModel):
    """Request body for a human approve/reject decision."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    decided_by: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("decided_by", mode="after")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("decided_by must not be empty or whitespace")
        return cleaned


@human_router.post("/{claim_id}/human-decision", response_model=ClaimRecord)
async def submit_human_decision(
    claim_id: UUID,
    decision: HumanDecision,
    settings: Settings = Depends(get_settings),
) -> ClaimRecord:
    """Record a reviewer's decision on an `awaiting_human` claim."""
    state = await run_in_threadpool(_claim_state, settings, claim_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"claim not found: {claim_id}")
    claim, latest_run = state
    # Idempotent: a claim already moved past awaiting_human (a prior decision, or a
    # run still in flight) cannot be decided again.
    if claim.status != _DECIDABLE_STATUS:
        raise HTTPException(
            status_code=409,
            detail=f"claim {claim_id} is not awaiting human review (status={claim.status})",
        )
    if latest_run is None:
        raise HTTPException(
            status_code=409, detail=f"claim {claim_id} has no run to decide on"
        )
    return await run_in_threadpool(
        _write_decision, settings, claim_id, latest_run, decision
    )


def _claim_state(
    settings: Settings, claim_id: UUID
) -> tuple[ClaimRecord, UUID | None] | None:
    """Return the claim and its most-recent run correlation_id, or None if absent."""
    with open_connection(settings) as conn:
        claim = ClaimsRepository.get(conn, claim_id)
        if claim is None:
            return None
        summaries = RunsRepository.list_runs_for_claim(conn, claim_id)
        latest = summaries[0].correlation_id if summaries else None
        return claim, latest


def _write_decision(
    settings: Settings, claim_id: UUID, correlation_id: UUID, decision: HumanDecision
) -> ClaimRecord:
    """Write the human audit entry and move the claim to its terminal status."""
    approved = decision.decision == "approved"
    step = _STEP_APPROVAL if approved else _STEP_REJECTION
    new_status = _STATUS_ON_APPROVAL if approved else _STATUS_ON_REJECTION
    now = datetime.now(UTC)
    with open_connection(settings) as conn:
        AuditWriter(conn).append(
            AuditEvent(
                correlation_id=correlation_id,
                claim_id=claim_id,
                agent="human",
                step=step,
                payload={
                    "decision": decision.decision,
                    "decided_by": decision.decided_by,
                    "comment": decision.comment,
                    "decided_at": now.isoformat(),
                },
                created_at=now,
            )
        )
        ClaimsRepository.update_status(conn, claim_id, new_status)
        updated = ClaimsRepository.get(conn, claim_id)
    assert updated is not None  # we just updated it in the same connection
    return updated
