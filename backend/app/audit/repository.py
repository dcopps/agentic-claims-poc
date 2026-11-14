"""
AuditRepository — read access to the audit ledger by run.

The ledger is written by `AuditWriter` and verified by `verify_chain`; this is
the one place that *reads* it back as typed rows. Both the audit API and the
MCP tools call these functions (Phase 10 promoted the SQL out of the router so
the two surfaces cannot drift). Pure reads: nothing here writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from pydantic import BaseModel, ConfigDict

# The same two words as claims.models.HumanDecisionKind; spelt here because the
# claims module imports this one, and the audit layer imports nothing above it.
HumanDecisionKind = Literal["approved", "rejected"]


class AuditEntry(BaseModel):
    """One audit row as the ledger holds it, with the payload untouched."""

    model_config = ConfigDict(extra="forbid")

    audit_id: int
    agent: str
    step: str
    created_at: datetime
    payload: dict[str, Any]
    chain_hash: str


class AuditRepository:
    """Connection-scoped reads over `audit_log`, keyed by correlation id."""

    @staticmethod
    def list_entries(conn: psycopg.Connection, correlation_id: UUID) -> list[AuditEntry]:
        """Every entry under `correlation_id` in chain (`audit_id`) order; `[]` if none."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT audit_id, agent, step, created_at, payload, chain_hash "
                "FROM audit_log WHERE correlation_id = %s ORDER BY audit_id",
                (correlation_id,),
            )
            rows = cur.fetchall()
        return [
            AuditEntry(
                audit_id=row[0],
                agent=row[1],
                step=row[2],
                created_at=row[3],
                payload=row[4],
                chain_hash=row[5],
            )
            for row in rows
        ]

    @staticmethod
    def has_entries(conn: psycopg.Connection, correlation_id: UUID) -> bool:
        """True if at least one row carries `correlation_id` — the run exists."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM audit_log WHERE correlation_id = %s LIMIT 1",
                (correlation_id,),
            )
            return cur.fetchone() is not None

    @staticmethod
    def human_decisions(
        conn: psycopg.Connection, claim_ids: Sequence[UUID]
    ) -> dict[UUID, HumanDecisionKind]:
        """
        What a person decided about each claim, from the trail (Prompt 31).

        The question is answered here, not from `claims.status`, because the
        pipeline and an approval both write `settled`; only the human row says a
        person decided. One grouped query for a page of claims (on
        `audit_log_claim_id_idx`); the last human row per claim wins, though
        api/human.py allows only one. Claims with no row are absent, so callers
        read with a default of None. An empty input returns `{}` without a query.
        """
        if not claim_ids:
            return {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ON (claim_id) claim_id, step FROM audit_log "
                "WHERE agent = 'human' AND step = ANY(%s) AND claim_id = ANY(%s) "
                "ORDER BY claim_id, created_at DESC, audit_id DESC",
                (list(_HUMAN_STEPS), list(claim_ids)),
            )
            rows = cur.fetchall()
        return {claim_id: _HUMAN_STEPS[step] for claim_id, step in rows}


# The two steps api/human.py writes, and the decision each records.
_HUMAN_STEPS: dict[str, HumanDecisionKind] = {
    "human_approval": "approved",
    "human_rejection": "rejected",
}
