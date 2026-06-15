"""
Audit API — read access to the audit ledger and one-click chain verification.

`GET /api/audit?correlation_id=` lists every entry under a run in chain order, for
the audit-log viewer. `GET /api/audit/verify/{correlation_id}` runs the
chain-integrity verifier.

**Chain verification is whole-ledger, not per-run.** The hash chain links *every*
`audit_log` row across the entire table in `audit_id` order, so a single run's
rows cannot be verified as an isolated sub-chain. The endpoint therefore runs the
full-ledger `verify_chain`; the `correlation_id` only scopes the 404 (the run must
exist) and gives the UI context. The viewer copy states this explicitly so the
semantics are reviewer-evident.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from backend.app.api.pipeline import get_settings
from backend.app.audit.verify import verify_chain
from backend.db.connection import open_connection
from backend.settings import Settings

audit_router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntryView(BaseModel):
    """One audit row, for the viewer."""

    model_config = ConfigDict(extra="forbid")

    audit_id: int
    agent: str
    step: str
    created_at: datetime
    payload: dict[str, Any]
    chain_hash: str


class AuditBreakView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: int
    kind: str
    expected: str
    actual: str


class ChainVerificationView(BaseModel):
    """Whole-ledger chain-verification result (see module docstring)."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    rows_checked: int
    first_break: AuditBreakView | None


@audit_router.get("", response_model=list[AuditEntryView])
async def list_audit_entries(
    correlation_id: UUID, settings: Settings = Depends(get_settings)
) -> list[AuditEntryView]:
    """List every audit entry under `correlation_id` in chain order. 404 if none."""
    entries = await run_in_threadpool(_list_entries, settings, correlation_id)
    if not entries:
        raise HTTPException(
            status_code=404, detail=f"no audit entries for correlation_id {correlation_id}"
        )
    return entries


@audit_router.get("/verify/{correlation_id}", response_model=ChainVerificationView)
async def verify_audit_chain(
    correlation_id: UUID, settings: Settings = Depends(get_settings)
) -> ChainVerificationView:
    """Verify the whole audit ledger. 404 if the correlation_id has no entries."""
    result = await run_in_threadpool(_verify, settings, correlation_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"no audit entries for correlation_id {correlation_id}"
        )
    return result


def _list_entries(settings: Settings, correlation_id: UUID) -> list[AuditEntryView]:
    with open_connection(settings) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT audit_id, agent, step, created_at, payload, chain_hash "
            "FROM audit_log WHERE correlation_id = %s ORDER BY audit_id",
            (correlation_id,),
        )
        rows = cur.fetchall()
    return [
        AuditEntryView(
            audit_id=row[0],
            agent=row[1],
            step=row[2],
            created_at=row[3],
            payload=row[4],
            chain_hash=row[5],
        )
        for row in rows
    ]


def _verify(settings: Settings, correlation_id: UUID) -> ChainVerificationView | None:
    with open_connection(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM audit_log WHERE correlation_id = %s LIMIT 1",
                (correlation_id,),
            )
            if cur.fetchone() is None:
                return None
        result = verify_chain(conn)  # whole-ledger; see module docstring
    first_break = (
        AuditBreakView(
            audit_id=result.first_break.audit_id,
            kind=result.first_break.kind,
            expected=result.first_break.expected,
            actual=result.first_break.actual,
        )
        if result.first_break is not None
        else None
    )
    return ChainVerificationView(
        ok=result.ok, rows_checked=result.rows_checked, first_break=first_break
    )
