"""
Tests for the human-decision API.

A claim is seeded `awaiting_human` with a completed run (so there is a
correlation_id to attach the decision to). The happy paths assert the status flip
and the `agent="human"` audit entry; the guards cover not-awaiting, idempotency,
missing claim, and body validation.
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


def _insert_claim(conn: psycopg.Connection, status: str = "awaiting_human") -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO claims (claim_number, line_of_business, claimant_name,
                policy_number, loss_date, reported_date, jurisdiction, narrative,
                claim_type, reported_amount, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING claim_id
            """,
            (
                f"HUM-{uuid4().hex[:8].upper()}", "Commercial Property", "Acme Ltd",
                "POL-1", date(2026, 4, 1), date(2026, 4, 3), "United Kingdom",
                "Loss.", "fire", Decimal("850000.00"), status,
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
        ("pipeline_awaiting_human", {"status": "awaiting_human", "completed_at": now.isoformat()}),
    ):
        AuditWriter(conn).append(
            AuditEvent(
                correlation_id=cid, claim_id=claim_id, agent="orchestrator",
                step=step, payload=payload, created_at=now,
            )
        )
    return cid


def _decision(**over: object) -> dict[str, object]:
    base: dict[str, object] = {"decision": "approved", "decided_by": "A. Reviewer"}
    base.update(over)
    return base


def test_approve_settles_claim(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    cid = _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(f"/api/claims/{claim_id}/human-decision", json=_decision())
    assert resp.status_code == 200
    assert resp.json()["status"] == "settled"
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT agent, step FROM audit_log WHERE correlation_id = %s "
            "AND agent = 'human'",
            (cid,),
        )
        rows = cur.fetchall()
    assert ("human", "human_approval") in rows


def test_reject_aborts_claim(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(
            f"/api/claims/{claim_id}/human-decision",
            json=_decision(decision="rejected", comment="Insufficient evidence."),
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "aborted"


def test_decision_on_non_awaiting_claim_409(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db, status="received")
    _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(f"/api/claims/{claim_id}/human-decision", json=_decision())
    assert resp.status_code == 409
    assert "not awaiting human review" in resp.json()["detail"]


def test_decision_is_idempotent(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        first = client.post(f"/api/claims/{claim_id}/human-decision", json=_decision())
        second = client.post(f"/api/claims/{claim_id}/human-decision", json=_decision())
    assert first.status_code == 200
    assert second.status_code == 409  # now settled, cannot decide again


def test_decision_missing_claim_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(f"/api/claims/{uuid4()}/human-decision", json=_decision())
    assert resp.status_code == 404


def test_decision_rejects_blank_decided_by(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(
            f"/api/claims/{claim_id}/human-decision", json=_decision(decided_by="   ")
        )
    assert resp.status_code == 422


def test_decision_rejects_oversized_comment(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    _seed_run(clean_db, claim_id)
    with TestClient(create_app(db_settings)) as client:
        resp = client.post(
            f"/api/claims/{claim_id}/human-decision",
            json=_decision(comment="x" * 1001),
        )
    assert resp.status_code == 422
