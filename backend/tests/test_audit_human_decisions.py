"""
Tests for `AuditRepository.human_decisions` (Prompt 31): what a person decided
about each claim, read from the trail's human rows in one grouped query.
"""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import psycopg

from backend.app.audit.repository import AuditRepository
from backend.tests.mcp_fixture import (
    insert_harborline_claim,
    seed_fixture_run,
    seed_human_decision,
)


def test_no_human_row_means_no_decision(clean_db: psycopg.Connection) -> None:
    claim = insert_harborline_claim(clean_db)
    seed_fixture_run(clean_db, claim.claim_id)
    assert AuditRepository.human_decisions(clean_db, [claim.claim_id]) == {}


def test_reads_an_approval_and_a_rejection(clean_db: psycopg.Connection) -> None:
    approved = insert_harborline_claim(clean_db)
    rejected = insert_harborline_claim(clean_db)
    untouched = insert_harborline_claim(clean_db)
    run_a = seed_fixture_run(clean_db, approved.claim_id)
    run_r = seed_fixture_run(clean_db, rejected.claim_id)
    seed_human_decision(clean_db, approved.claim_id, run_a, "approved")
    seed_human_decision(clean_db, rejected.claim_id, run_r, "rejected")
    decisions = AuditRepository.human_decisions(
        clean_db, [approved.claim_id, rejected.claim_id, untouched.claim_id]
    )
    assert decisions == {approved.claim_id: "approved", rejected.claim_id: "rejected"}


def test_the_last_human_row_wins(clean_db: psycopg.Connection) -> None:
    claim = insert_harborline_claim(clean_db)
    cid = seed_fixture_run(clean_db, claim.claim_id)
    seed_human_decision(clean_db, claim.claim_id, cid, "rejected")
    seed_human_decision(clean_db, claim.claim_id, cid, "approved")
    assert AuditRepository.human_decisions(clean_db, [claim.claim_id]) == {
        claim.claim_id: "approved"
    }


def test_an_unknown_claim_is_absent(clean_db: psycopg.Connection) -> None:
    assert AuditRepository.human_decisions(clean_db, [uuid4()]) == {}


def test_an_empty_input_makes_no_query() -> None:
    # No connection is needed, and none may be used: the guard returns first.
    assert AuditRepository.human_decisions(cast(psycopg.Connection, None), []) == {}
