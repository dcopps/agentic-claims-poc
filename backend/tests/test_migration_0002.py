"""
Tests for migration 0002 — the audit_log agent CHECK extension to include 'human'.

The `clean_db` fixture applies migrations (through 0002) before these run, so they
assert the *applied* state: a `human` audit entry is now insertable, the
constraint definition lists `human`, and the documented downgrade hazard holds (a
six-value constraint cannot be re-added while a `human` row exists). The hazard
test does its constraint surgery inside a transaction it rolls back, so the shared
schema is left untouched.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest

from backend.app.audit import AuditEvent, AuditWriter

_SIX_VALUE_CHECK = (
    "ALTER TABLE audit_log ADD CONSTRAINT audit_log_agent_check "
    "CHECK (agent IN ('system','doc_parser','validator','adjuster',"
    "'guardrail','orchestrator'))"
)


def _insert_claim(conn: psycopg.Connection) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO claims (
                claim_number, line_of_business, claimant_name, policy_number,
                loss_date, reported_date, jurisdiction, narrative, claim_type,
                reported_amount, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING claim_id
            """,
            (
                f"MIG-{uuid4().hex[:8].upper()}",
                "Commercial Property",
                "Acme Ltd",
                "POL-1",
                date(2026, 4, 1),
                date(2026, 4, 3),
                "United Kingdom",
                "Loss.",
                "water_damage",
                Decimal("85000.00"),
                "awaiting_human",
            ),
        )
        row = cur.fetchone()
        assert row is not None
        claim_id: UUID = row[0]
    conn.commit()
    return claim_id


def _write_human_entry(conn: psycopg.Connection, claim_id: UUID) -> None:
    AuditWriter(conn).append(
        AuditEvent(
            correlation_id=uuid4(),
            claim_id=claim_id,
            agent="human",
            step="human_approval",
            payload={"decision": "approved", "decided_by": "Reviewer"},
            created_at=datetime.now(UTC),
        )
    )


def test_human_agent_audit_entry_persists(clean_db: psycopg.Connection) -> None:
    claim_id = _insert_claim(clean_db)
    _write_human_entry(clean_db, claim_id)
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT agent, step FROM audit_log WHERE claim_id = %s", (claim_id,)
        )
        rows = cur.fetchall()
    assert ("human", "human_approval") in rows


def test_agent_check_constraint_includes_human(clean_db: psycopg.Connection) -> None:
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'audit_log_agent_check'"
        )
        row = cur.fetchone()
    assert row is not None
    assert "'human'" in row[0]


def test_claims_status_check_includes_aborted(clean_db: psycopg.Connection) -> None:
    # A human rejection moves the claim to `aborted`; the CHECK must allow it.
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'claims_status_check'"
        )
        row = cur.fetchone()
    assert row is not None
    assert "'aborted'" in row[0]


def test_downgrade_constraint_rejects_existing_human_rows(
    clean_db: psycopg.Connection,
) -> None:
    # The documented downgrade hazard: with a `human` row present, re-adding the
    # six-value CHECK must fail rather than silently dropping audit rows.
    claim_id = _insert_claim(clean_db)
    _write_human_entry(clean_db, claim_id)
    with pytest.raises(psycopg.errors.CheckViolation), clean_db.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_agent_check")
        cur.execute(_SIX_VALUE_CHECK)
    # Roll back the aborted DDL transaction so the seven-value constraint stands.
    clean_db.rollback()
