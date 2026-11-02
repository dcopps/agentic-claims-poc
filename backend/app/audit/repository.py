"""
AuditRepository — read access to the audit ledger by run.

The ledger is written by `AuditWriter` and verified by `verify_chain`; this is
the one place that *reads* it back as typed rows. Both the audit API and the
MCP tools call these functions (Phase 10 promoted the SQL out of the router so
the two surfaces cannot drift). Pure reads: nothing here writes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from pydantic import BaseModel, ConfigDict


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
