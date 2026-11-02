"""
Shared helpers for the Phase 10 MCP tests.

The fixture `fixtures/mcp/run_0cdfa114.json` holds the real rows of the
Harborline run the plan uses as its worked example, read from the Render
deployment on 2 November 2026 with each agent row's prompts removed. The
helpers below load it as typed entries, and re-seed it into the test database
through `AuditWriter` (so the rows carry hashes the verifier accepts) under a
fresh claim and correlation id.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg

from backend.app.audit import AuditEvent, AuditWriter
from backend.app.audit.repository import AuditEntry
from backend.app.claims import ClaimsRepository, ClaimSubmission
from backend.app.claims.models import ClaimRecord

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mcp" / "run_0cdfa114.json"

# The refused claim the fixture records, quoted by the plan's worked example.
FIXTURE_DISCARDED_QUOTE = "inventory valuation and depreciation"


def load_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data


def fixture_entries() -> list[AuditEntry]:
    """The run's seven rows as `AuditEntry` objects, in chain order."""
    return [AuditEntry.model_validate(row) for row in load_fixture()["entries"]]


def fixture_claim() -> ClaimRecord:
    return ClaimRecord.model_validate(load_fixture()["claim"])


def harborline_submission() -> ClaimSubmission:
    return ClaimSubmission(
        claimant_name="Harborline Logistics Ltd",
        policy_number="CP-2026-9001",
        loss_date=datetime(2026, 4, 18, tzinfo=UTC).date(),
        reported_date=datetime(2026, 4, 19, tzinfo=UTC).date(),
        jurisdiction="United Kingdom",
        narrative="Burst supply line under the second-floor break room flooded the mezzanine.",
        claim_type="water_damage",
        reported_amount=Decimal("85000.00"),
        scenario_tag="auto_approve",
    )


def insert_harborline_claim(conn: psycopg.Connection) -> ClaimRecord:
    return ClaimsRepository.insert(conn, harborline_submission())


def seed_fixture_run(
    conn: psycopg.Connection,
    claim_id: UUID,
    correlation_id: UUID | None = None,
    *,
    steps: tuple[str, ...] | None = None,
) -> UUID:
    """
    Write the fixture's rows under `claim_id` / `correlation_id` through the writer.

    `steps` restricts which rows are written (an in-flight run is the fixture
    without its terminal row). The orchestrator rows' embedded ids are rewritten
    to the new claim and run so the reconstruction code sees a consistent chain.
    """
    cid = correlation_id or uuid4()
    writer = AuditWriter(conn)
    for row in load_fixture()["entries"]:
        if steps is not None and row["step"] not in steps:
            continue
        payload = _rebind_ids(dict(row["payload"]), claim_id, cid)
        writer.append(
            AuditEvent(
                correlation_id=cid,
                claim_id=claim_id,
                agent=row["agent"],
                step=row["step"],
                payload=payload,
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        )
    return cid


def _rebind_ids(payload: dict[str, Any], claim_id: UUID, cid: UUID) -> dict[str, Any]:
    if "claim_id" in payload:
        payload["claim_id"] = str(claim_id)
    if "correlation_id" in payload:
        payload["correlation_id"] = str(cid)
    inner = payload.get("input")
    if isinstance(inner, dict) and "claim_id" in inner:
        inner["claim_id"] = str(claim_id)
    return payload
