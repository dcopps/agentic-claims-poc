"""
Tests for the claims, runs, and replay API surface (Phase 5).

Claim submission and reads use a real `clean_db`. The replay/run guards are
exercised with a stub orchestrator (so no providers/embedder) plus audit entries
seeded directly via `AuditWriter` to represent prior or in-flight runs. The
runs/compare happy paths are covered end-to-end in the integration scenarios.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

from backend.app.api.pipeline import get_orchestrator_factory
from backend.app.audit import AuditEvent, AuditWriter
from backend.app.claims import ClaimsRepository, ClaimSubmission
from backend.app.main import create_app
from backend.settings import Settings

from .test_api_pipeline import _StubOrchestrator


def _body(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "claimant_name": "Acme Logistics Ltd",
        "policy_number": "POL-9001",
        "loss_date": "2026-04-01",
        "reported_date": "2026-04-03",
        "jurisdiction": "United Kingdom",
        "narrative": "Burst supply line flooded the warehouse floor.",
        "claim_type": "water_damage",
        "reported_amount": "85000.00",
    }
    base.update(overrides)
    return base


def _insert_claim(conn: psycopg.Connection) -> UUID:
    record = ClaimsRepository.insert(
        conn,
        ClaimSubmission(
            claimant_name="Acme Logistics Ltd",
            policy_number="POL-9001",
            loss_date=date(2026, 4, 1),
            reported_date=date(2026, 4, 3),
            jurisdiction="United Kingdom",
            narrative="Burst supply line flooded the warehouse floor.",
            claim_type="water_damage",
            reported_amount=Decimal("85000.00"),
        ),
    )
    return record.claim_id


def _seed_started(conn: psycopg.Connection, claim_id: UUID) -> UUID:
    cid = uuid4()
    now = datetime.now(UTC)
    AuditWriter(conn).append(
        AuditEvent(
            correlation_id=cid,
            claim_id=claim_id,
            agent="orchestrator",
            step="pipeline_started",
            payload={
                "claim_id": str(claim_id),
                "variant": "default",
                "started_at": now.isoformat(),
            },
            created_at=now,
        )
    )
    return cid


def _seed_completed(conn: psycopg.Connection, claim_id: UUID) -> UUID:
    cid = _seed_started(conn, claim_id)
    now = datetime.now(UTC)
    AuditWriter(conn).append(
        AuditEvent(
            correlation_id=cid,
            claim_id=claim_id,
            agent="orchestrator",
            step="pipeline_settled",
            payload={
                "status": "settled",
                "escalate": False,
                "fired_rule_names": [],
                "settlement": "85000.00",
                "completed_at": now.isoformat(),
            },
            created_at=now,
        )
    )
    return cid


def _client(db_settings: Settings, orchestrator: _StubOrchestrator | None = None) -> TestClient:
    app = create_app(db_settings)
    if orchestrator is not None:
        app.dependency_overrides[get_orchestrator_factory] = lambda: (
            lambda _variant: orchestrator
        )
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Claims API
# --------------------------------------------------------------------------- #


def test_submit_claim_returns_201(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with _client(db_settings) as client:
        resp = client.post("/api/claims", json=_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "received"
    assert body["claim_number"].startswith("CLM-2026-")


def test_submit_rejects_reversed_dates(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with _client(db_settings) as client:
        resp = client.post(
            "/api/claims", json=_body(loss_date="2026-04-05", reported_date="2026-04-03")
        )
    assert resp.status_code == 422


def test_submit_rejects_unknown_claim_type(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with _client(db_settings) as client:
        resp = client.post("/api/claims", json=_body(claim_type="meteor_strike"))
    assert resp.status_code == 422


def test_list_and_get_claim(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    with _client(db_settings) as client:
        listed = client.get("/api/claims?limit=10")
        one = client.get(f"/api/claims/{claim_id}")
    assert listed.status_code == 200
    assert any(c["claim_id"] == str(claim_id) for c in listed.json())
    assert one.status_code == 200
    assert one.json()["claim_id"] == str(claim_id)


def test_get_missing_claim_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with _client(db_settings) as client:
        resp = client.get(f"/api/claims/{uuid4()}")
    assert resp.status_code == 404


def test_list_claim_runs_empty_then_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    with _client(db_settings) as client:
        empty = client.get(f"/api/claims/{claim_id}/runs")
        missing = client.get(f"/api/claims/{uuid4()}/runs")
    assert empty.status_code == 200
    assert empty.json() == []
    assert missing.status_code == 404


# --------------------------------------------------------------------------- #
# Replay / run guards
# --------------------------------------------------------------------------- #


def test_replay_unknown_variant_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    _seed_completed(clean_db, claim_id)
    with _client(db_settings, _StubOrchestrator()) as client:
        resp = client.post(f"/api/pipeline/replay/{claim_id}?variant=v9_unreal")
    assert resp.status_code == 404


def test_replay_missing_claim_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with _client(db_settings, _StubOrchestrator()) as client:
        resp = client.post(f"/api/pipeline/replay/{uuid4()}")
    assert resp.status_code == 404


def test_replay_without_prior_run_409(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)  # no runs yet
    with _client(db_settings, _StubOrchestrator()) as client:
        resp = client.post(f"/api/pipeline/replay/{claim_id}")
    assert resp.status_code == 409
    assert "nothing to replay" in resp.json()["detail"]


def test_run_rejected_when_active_409(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    _seed_started(clean_db, claim_id)  # started, no terminal => active
    with _client(db_settings, _StubOrchestrator()) as client:
        resp = client.post(f"/api/pipeline/run/{claim_id}")
    assert resp.status_code == 409
    assert "already in flight" in resp.json()["detail"]


def test_replay_happy_returns_result(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    _seed_completed(clean_db, claim_id)  # a prior terminal run exists
    with _client(db_settings, _StubOrchestrator(status="awaiting_human")) as client:
        resp = client.post(f"/api/pipeline/replay/{claim_id}?variant=v2_strict_validator")
    assert resp.status_code == 200
    assert resp.json()["status"] == "awaiting_human"


# --------------------------------------------------------------------------- #
# Runs API
# --------------------------------------------------------------------------- #


def test_get_run_missing_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with _client(db_settings) as client:
        resp = client.get(f"/api/runs/{uuid4()}")
    assert resp.status_code == 404
