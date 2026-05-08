"""
AuditWriter tests — DB-backed.

Each test starts with empty tables (`clean_db` fixture). Inserts a
parent claim, exercises the writer, asserts on the persisted columns
and the chain linkage. Concurrent-write coverage uses a small thread
pair to demonstrate the advisory lock keeps the chain serialised.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest

from backend.app.audit.chain import GENESIS_CHAIN_HASH
from backend.app.audit.event import AuditEvent
from backend.app.audit.writer import AuditWriter
from backend.db.connection import open_connection
from backend.settings import Settings


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


def _make_event(claim_id: UUID, step: str = "phase_start") -> AuditEvent:
    return AuditEvent(
        correlation_id=uuid4(),
        claim_id=claim_id,
        agent="orchestrator",
        step=step,
        payload={"note": "test"},
        created_at=datetime.now(UTC),
    )


def test_first_append_uses_genesis_prev(clean_db: psycopg.Connection) -> None:
    claim_id = uuid4()
    _insert_claim(clean_db, claim_id)

    writer = AuditWriter(clean_db)
    row = writer.append(_make_event(claim_id))

    assert row.prev_chain_hash == GENESIS_CHAIN_HASH
    assert row.row_hash != GENESIS_CHAIN_HASH
    assert row.chain_hash != GENESIS_CHAIN_HASH


def test_three_appends_chain_correctly(clean_db: psycopg.Connection) -> None:
    claim_id = uuid4()
    _insert_claim(clean_db, claim_id)

    writer = AuditWriter(clean_db)
    rows = [writer.append(_make_event(claim_id, step=f"step_{i}")) for i in range(3)]

    assert rows[0].prev_chain_hash == GENESIS_CHAIN_HASH
    assert rows[1].prev_chain_hash == rows[0].chain_hash
    assert rows[2].prev_chain_hash == rows[1].chain_hash


def test_append_with_unknown_claim_id_raises_with_diagnostic(
    clean_db: psycopg.Connection,
) -> None:
    bogus = uuid4()
    writer = AuditWriter(clean_db)

    with pytest.raises(ValueError) as excinfo:
        writer.append(_make_event(bogus))

    message = str(excinfo.value)
    assert "claim_id not found" in message
    assert str(bogus) in message


def test_append_with_empty_step_raises() -> None:
    """Step validator runs at AuditEvent construction time."""
    with pytest.raises(ValueError) as excinfo:
        AuditEvent(
            correlation_id=uuid4(),
            claim_id=uuid4(),
            agent="orchestrator",
            step="",
            payload={},
            created_at=datetime.now(UTC),
        )
    assert "non-empty" in str(excinfo.value) or "at least 1" in str(excinfo.value)


def test_append_with_naive_datetime_raises() -> None:
    """Datetime validator runs at AuditEvent construction time."""
    with pytest.raises(ValueError) as excinfo:
        AuditEvent(
            correlation_id=uuid4(),
            claim_id=uuid4(),
            agent="orchestrator",
            step="phase_start",
            payload={},
            created_at=datetime(2026, 5, 8, 12, 0, 0),
        )
    assert "timezone-aware" in str(excinfo.value)


def test_append_persists_payload_as_jsonb(clean_db: psycopg.Connection) -> None:
    claim_id = uuid4()
    _insert_claim(clean_db, claim_id)

    writer = AuditWriter(clean_db)
    row = writer.append(_make_event(claim_id))

    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT payload->>'note' FROM audit_log WHERE audit_id = %s",
            (row.audit_id,),
        )
        result = cur.fetchone()
    assert result is not None
    assert result[0] == "test"


def test_concurrent_writes_serialise_through_advisory_lock(
    db_settings: Settings,
    clean_db: psycopg.Connection,
) -> None:
    """
    Two threads each append five events on their own connection. The
    advisory lock should serialise them so the resulting chain has no
    forks (every prev_chain_hash matches the previous row's chain_hash).
    """
    claim_id = uuid4()
    _insert_claim(clean_db, claim_id)

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker(label: str) -> None:
        try:
            with open_connection(db_settings) as conn:
                writer = AuditWriter(conn)
                barrier.wait()
                for i in range(5):
                    writer.append(_make_event(claim_id, step=f"{label}_{i}"))
        except Exception as exc:  # pragma: no cover - test diagnostic path
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(label,)) for label in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []

    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT audit_id, prev_chain_hash, chain_hash "
            "FROM audit_log ORDER BY audit_id ASC"
        )
        ordered = cur.fetchall()

    assert len(ordered) == 10
    assert ordered[0][1] == GENESIS_CHAIN_HASH
    for prev_row, this_row in zip(ordered[:-1], ordered[1:], strict=True):
        # prev_chain_hash on row N must equal chain_hash on row N-1.
        assert this_row[1] == prev_row[2]
