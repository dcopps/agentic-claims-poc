"""
verify_chain tests — DB-backed.

Confirms the verifier:
  - reports `ok=True` against an empty table.
  - reports `ok=True` against a clean three-row chain.
  - reports a row_hash break when the payload is tampered directly.
  - reports a chain_hash break when the chain hash of a middle row is
    tampered (the divergence appears at the *next* row, because that
    row's stored prev pointer no longer matches the recomputed chain).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from backend.app.audit.event import AuditEvent
from backend.app.audit.verify import verify_chain
from backend.app.audit.writer import AuditWriter


def _insert_claim(conn: psycopg.Connection, claim_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO claims (
                claim_id, claim_number, claimant_name, policy_number,
                loss_date, reported_date, jurisdiction, narrative,
                claim_type, reported_amount, status
            ) VALUES (
                %s, %s, 'Test Claimant', 'CP-TEST-1',
                '2026-04-01', '2026-04-02', 'United Kingdom',
                'Test narrative.', 'water_damage', %s, 'received'
            )
            """,
            (claim_id, f"CLM-TEST-{claim_id.hex[:8]}", Decimal("10000.00")),
        )
    conn.commit()


def _make_event(claim_id: UUID, step: str) -> AuditEvent:
    return AuditEvent(
        correlation_id=uuid4(),
        claim_id=claim_id,
        agent="orchestrator",
        step=step,
        payload={"step": step},
        created_at=datetime.now(UTC),
    )


def test_empty_table_verifies_ok(clean_db: psycopg.Connection) -> None:
    result = verify_chain(clean_db)
    assert result.ok is True
    assert result.rows_checked == 0
    assert result.first_break is None


def test_clean_chain_verifies_ok(clean_db: psycopg.Connection) -> None:
    claim_id = uuid4()
    _insert_claim(clean_db, claim_id)

    writer = AuditWriter(clean_db)
    for i in range(3):
        writer.append(_make_event(claim_id, f"step_{i}"))

    result = verify_chain(clean_db)
    assert result.ok is True
    assert result.rows_checked == 3
    assert result.first_break is None


def test_row_hash_break_detected_when_payload_tampered(
    clean_db: psycopg.Connection,
) -> None:
    claim_id = uuid4()
    _insert_claim(clean_db, claim_id)

    writer = AuditWriter(clean_db)
    rows = [writer.append(_make_event(claim_id, f"step_{i}")) for i in range(3)]

    # Tamper with the middle row's payload directly via SQL — the row
    # hash and the chain hash stored on disk are now divorced from the
    # canonical bytes the verifier will reconstruct.
    target = rows[1].audit_id
    with clean_db.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET payload = %s WHERE audit_id = %s",
            (Jsonb({"step": "TAMPERED"}), target),
        )
    clean_db.commit()

    result = verify_chain(clean_db)
    assert result.ok is False
    assert result.first_break is not None
    assert result.first_break.audit_id == target
    assert result.first_break.kind == "row_hash_mismatch"


def test_chain_hash_break_detected_when_middle_chain_hash_tampered(
    clean_db: psycopg.Connection,
) -> None:
    claim_id = uuid4()
    _insert_claim(clean_db, claim_id)

    writer = AuditWriter(clean_db)
    rows = [writer.append(_make_event(claim_id, f"step_{i}")) for i in range(3)]

    # Tampering the chain_hash on row 1 leaves row 1 looking internally
    # consistent (its row_hash still matches its content) but breaks
    # row 2, whose stored prev_chain_hash no longer agrees with the
    # recomputed chain. The verifier reports the break at row 2.
    middle = rows[1].audit_id
    with clean_db.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET chain_hash = %s WHERE audit_id = %s",
            ("f" * 64, middle),
        )
    clean_db.commit()

    result = verify_chain(clean_db)
    assert result.ok is False
    assert result.first_break is not None
    assert result.first_break.kind == "chain_hash_mismatch"
    assert result.first_break.audit_id in {middle, rows[2].audit_id}
