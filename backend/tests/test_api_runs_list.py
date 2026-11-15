"""
Tests for `GET /api/runs` (Prompt 32): the latest runs across every claim, each
named by its claim, and the short-id prefix match the Audit page relies on.

Runs are seeded through `AuditWriter` with chosen correlation ids, so the prefix
cases can be arranged (one match, several, none); a human decision is seeded
under one claim to show the field comes from the trail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.audit import AuditEvent, AuditWriter
from backend.app.main import create_app
from backend.app.runs import RunsRepository
from backend.settings import Settings
from backend.tests.mcp_fixture import insert_harborline_claim, seed_human_decision
from backend.tests.test_api_claims_runs import _insert_claim

RUN_A = UUID("aaaaaaaa-1111-4000-8000-000000000001")
RUN_B = UUID("aaaaaaaa-2222-4000-8000-000000000002")
RUN_C = UUID("cccccccc-0000-4000-8000-000000000003")


def _seed_run(conn: psycopg.Connection, claim_id: UUID, cid: UUID, *, settled: bool) -> None:
    """A started run, and its settled terminal row when asked for."""
    now = datetime.now(UTC)
    writer = AuditWriter(conn)
    writer.append(
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
    if settled:
        writer.append(
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


def _seed_three_runs(conn: psycopg.Connection) -> tuple[UUID, UUID]:
    """Two claims, three runs in the order A, B, C; claim one approved."""
    acme = _insert_claim(conn)
    harborline = insert_harborline_claim(conn).claim_id
    _seed_run(conn, acme, RUN_A, settled=True)
    _seed_run(conn, acme, RUN_B, settled=True)
    _seed_run(conn, harborline, RUN_C, settled=False)
    seed_human_decision(conn, acme, RUN_B, "approved")
    conn.commit()
    return acme, harborline


def test_lists_runs_newest_first_named_by_their_claims(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    acme, harborline = _seed_three_runs(clean_db)
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 200
    items = resp.json()
    assert [item["correlation_id"] for item in items] == [str(RUN_C), str(RUN_B), str(RUN_A)]
    newest = items[0]
    assert newest["claim_id"] == str(harborline)
    assert newest["claimant_name"] == "Harborline Logistics Ltd"
    assert newest["claim_number"].startswith("CLM-")
    assert newest["status"] == "running"
    assert newest["completed_at"] is None
    assert newest["human_decision"] is None
    # The decision is the claim's, read from the trail: both of Acme's runs carry it.
    assert [item["human_decision"] for item in items[1:]] == ["approved", "approved"]
    assert items[1]["claim_id"] == str(acme)
    assert items[1]["status"] == "settled"
    assert items[1]["variant"] == "default"


def test_limit_takes_the_newest(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    _seed_three_runs(clean_db)
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/runs?limit=1")
    assert resp.status_code == 200
    assert [item["correlation_id"] for item in resp.json()] == [str(RUN_C)]


def test_prefix_resolves_one_several_or_none(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    _seed_three_runs(clean_db)
    with TestClient(create_app(db_settings)) as client:
        one = client.get("/api/runs?prefix=cccccccc").json()
        several = client.get("/api/runs?prefix=aaaaaaaa").json()
        none = client.get("/api/runs?prefix=00000000").json()
        longer = client.get("/api/runs?prefix=aaaaaaaa-2222").json()
    assert [item["correlation_id"] for item in one] == [str(RUN_C)]
    assert [item["correlation_id"] for item in several] == [str(RUN_B), str(RUN_A)]
    assert none == []
    assert [item["correlation_id"] for item in longer] == [str(RUN_B)]


def test_prefix_is_lower_cased(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    _seed_three_runs(clean_db)
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/runs?prefix=CCCCCCCC")
    assert [item["correlation_id"] for item in resp.json()] == [str(RUN_C)]


@pytest.mark.parametrize(
    "query",
    ["prefix=cccccc", "prefix=ccccccczz", "prefix=cccccccc%25", "limit=0", "limit=101"],
)
def test_bad_prefix_or_limit_422(
    clean_db: psycopg.Connection, db_settings: Settings, query: str
) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get(f"/api/runs?{query}")
    assert resp.status_code == 422


def test_empty_ledger_lists_nothing(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    with TestClient(create_app(db_settings)) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_repository_rejects_an_unsafe_prefix(clean_db: psycopg.Connection) -> None:
    """The API validates first, but the repository guards the LIKE pattern itself."""
    with pytest.raises(ValueError, match="prefix must be 8 to 36 lower-case hex"):
        RunsRepository.list_recent_runs(clean_db, 20, "cccc%")
    with pytest.raises(ValueError, match="limit must be in"):
        RunsRepository.list_recent_runs(clean_db, 0)


def test_unknown_run_id_still_404s(clean_db: psycopg.Connection, db_settings: Settings) -> None:
    """The literal `/runs` route does not shadow `/runs/{correlation_id}`."""
    with TestClient(create_app(db_settings)) as client:
        resp = client.get(f"/api/runs/{uuid4()}")
    assert resp.status_code == 404
