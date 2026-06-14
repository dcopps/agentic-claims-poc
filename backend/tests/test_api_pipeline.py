"""
Tests for the pipeline API (`backend.app.api.pipeline`).

The orchestrator is stubbed via a dependency override so these tests touch
neither the LLM providers nor the embedder. The pre-flight claim check is left
real (it hits the database), so the happy path inserts a claim and the
unknown-claim path relies on the truncated table. The SSE endpoint is exercised
with a fake bus that yields a fixed event list, isolating the endpoint's
formatting from the real asyncio queue.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

from backend.app.api.pipeline import get_event_bus, get_orchestrator
from backend.app.escalation.models import EscalationDecision
from backend.app.main import create_app
from backend.app.orchestrator.models import (
    EventEmitter,
    PipelineCompletedEvent,
    PipelineEvent,
    PipelineResult,
    PipelineStartedEvent,
    PipelineStatus,
)
from backend.settings import Settings


def _now() -> datetime:
    return datetime.now(UTC)


def _decision(escalate: bool) -> EscalationDecision:
    return EscalationDecision(escalate=escalate, fired_rules=[], reasoning="stub")


@dataclass
class _StubOrchestrator:
    """Returns a canned result reflecting the claim id and correlation id."""

    status: PipelineStatus = "settled"

    def run(
        self,
        claim_id: UUID,
        *,
        correlation_id: UUID | None = None,
        emit: EventEmitter | None = None,
    ) -> PipelineResult:
        cid = correlation_id or uuid4()
        return PipelineResult(
            status=self.status,
            claim_id=claim_id,
            correlation_id=cid,
            escalation_decision=_decision(self.status != "settled"),
            doc_parser_output=None,
            validator_output=None,
            adjuster_output=None,
            guardrail_output=None,
            completed_at=_now(),
        )


@dataclass
class _FakeBus:
    """A bus whose subscribe yields a fixed list then ends the stream."""

    events: list[PipelineEvent] = field(default_factory=list)

    async def subscribe(self, correlation_id: UUID) -> AsyncIterator[PipelineEvent]:
        for event in self.events:
            yield event


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
                "API-TEST-0001",
                "Commercial Property",
                "Harborline Logistics Ltd",
                "POL-1",
                date(2026, 4, 1),
                date(2026, 4, 3),
                "United Kingdom",
                "Burst supply line flooded the warehouse mezzanine.",
                "water_damage",
                Decimal("85000.00"),
                "received",
            ),
        )
        row = cur.fetchone()
        assert row is not None
        claim_id: UUID = row[0]
    conn.commit()
    return claim_id


def _client(db_settings: Settings, orchestrator: _StubOrchestrator) -> TestClient:
    app = create_app(db_settings)
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    return TestClient(app)


# --------------------------------------------------------------------------- #
# POST /api/pipeline/run/{claim_id}
# --------------------------------------------------------------------------- #


def test_run_settled_returns_result(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    with _client(db_settings, _StubOrchestrator(status="settled")) as client:
        resp = client.post(f"/api/pipeline/run/{claim_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "settled"
    assert body["claim_id"] == str(claim_id)
    assert body["escalation_decision"]["escalate"] is False


def test_run_uses_injected_correlation_id(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    cid = uuid4()
    with _client(db_settings, _StubOrchestrator()) as client:
        resp = client.post(f"/api/pipeline/run/{claim_id}?correlation_id={cid}")
    assert resp.status_code == 200
    assert resp.json()["correlation_id"] == str(cid)


def test_run_awaiting_human_body(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    with _client(db_settings, _StubOrchestrator(status="awaiting_human")) as client:
        resp = client.post(f"/api/pipeline/run/{claim_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "awaiting_human"
    assert body["escalation_decision"]["escalate"] is True


def test_run_unknown_claim_returns_404(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    # clean_db truncated the claims table, so a random id is genuinely absent.
    with _client(db_settings, _StubOrchestrator()) as client:
        resp = client.post(f"/api/pipeline/run/{uuid4()}")
    assert resp.status_code == 404
    assert "claim not found" in resp.json()["detail"]


def test_run_malformed_uuid_returns_422(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    with _client(db_settings, _StubOrchestrator()) as client:
        resp = client.post("/api/pipeline/run/not-a-uuid")
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# GET /api/pipeline/stream/{correlation_id}
# --------------------------------------------------------------------------- #


def test_stream_emits_event_sequence(db_settings: Settings) -> None:
    cid = uuid4()
    events: list[PipelineEvent] = [
        PipelineStartedEvent(correlation_id=cid, timestamp=_now(), claim_id=uuid4()),
        PipelineCompletedEvent(correlation_id=cid, timestamp=_now(), status="settled"),
    ]
    app = create_app(db_settings)
    app.dependency_overrides[get_event_bus] = lambda: _FakeBus(events)
    with TestClient(app) as client:
        resp = client.get(f"/api/pipeline/stream/{cid}")
    assert resp.status_code == 200
    # Each event renders as `event: <name>` + a `data:` JSON line.
    assert "event: pipeline_started" in resp.text
    assert "event: pipeline_completed" in resp.text
    assert str(cid) in resp.text
