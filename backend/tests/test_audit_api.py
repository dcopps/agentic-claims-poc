"""
Tests for the audit API (list + whole-ledger chain verification).

Audit entries are seeded directly via `AuditWriter` (correct hashes), then the API
is hit over a TestClient. The chain-break test tampers a row's payload via SQL so
the verifier reports the first break.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

from backend.app.audit import AuditEvent, AuditWriter
from backend.app.main import create_app
from backend.settings import Settings


def _insert_claim(conn: psycopg.Connection) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO claims (claim_number, line_of_business, claimant_name,
                policy_number, loss_date, reported_date, jurisdiction, narrative,
                claim_type, reported_amount, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING claim_id
            """,
            (
                f"AUD-{uuid4().hex[:8].upper()}", "Commercial Property", "Acme Ltd",
                "POL-1", date(2026, 4, 1), date(2026, 4, 3), "United Kingdom",
                "Loss.", "water_damage", Decimal("85000.00"), "received",
            ),
        )
        row = cur.fetchone()
    assert row is not None
    conn.commit()
    claim_id: UUID = row[0]
    return claim_id


def _seed_run(conn: psycopg.Connection, claim_id: UUID) -> UUID:
    cid = uuid4()
    now = datetime.now(UTC)
    for step, payload in (
        ("pipeline_started", {"claim_id": str(claim_id), "variant": "default"}),
        ("pipeline_settled", {"status": "settled", "completed_at": now.isoformat()}),
    ):
        AuditWriter(conn).append(
            AuditEvent(
                correlation_id=cid, claim_id=claim_id, agent="orchestrator",
                step=step, payload=payload, created_at=now,
            )
        )
    return cid


def test_list_audit_entries(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    claim_id = _insert_claim(clean_db)
    cid = _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        resp = client.get(f"/api/audit?correlation_id={cid}")
    assert resp.status_code == 200
    entries = resp.json()
    assert [e["step"] for e in entries] == ["pipeline_started", "pipeline_settled"]
    assert all("chain_hash" in e for e in entries)


def test_list_audit_missing_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get(f"/api/audit?correlation_id={uuid4()}")
    assert resp.status_code == 404


def test_verify_chain_ok(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    claim_id = _insert_claim(clean_db)
    cid = _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        resp = client.get(f"/api/audit/verify/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["first_break"] is None
    assert body["rows_checked"] == 2


def test_verify_chain_detects_break(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    cid = _seed_run(clean_db, claim_id)
    # Tamper the first row's payload — its row_hash no longer matches.
    with clean_db.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET payload = %s WHERE correlation_id = %s "
            "AND step = 'pipeline_started'",
            (psycopg.types.json.Jsonb({"tampered": True}), cid),
        )
    clean_db.commit()
    with TestClient(create_app(db_settings)) as client:
        resp = client.get(f"/api/audit/verify/{cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["first_break"]["kind"] == "row_hash_mismatch"


def test_verify_missing_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get(f"/api/audit/verify/{uuid4()}")
    assert resp.status_code == 404
