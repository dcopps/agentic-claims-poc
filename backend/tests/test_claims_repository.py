"""
Tests for the claims domain — `ClaimsRepository` and `ClaimSubmission`.

The repository tests use a real `clean_db` connection. The submission-validation
tests are pure Pydantic. One drift guard pins `ClaimType` to the market-data keys
so a submittable claim is always processable by the Adjuster.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args
from uuid import uuid4

import psycopg
import pytest
import yaml

from backend.app.claims.models import ClaimSubmission, ClaimType
from backend.app.claims.repository import ClaimsRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKET_DATA_PATH = REPO_ROOT / "backend/data/market_data.yaml"


def _submission(**overrides: Any) -> ClaimSubmission:
    base: dict[str, Any] = {
        "claimant_name": "Acme Logistics Ltd",
        "policy_number": "POL-9001",
        "loss_date": date(2026, 4, 1),
        "reported_date": date(2026, 4, 3),
        "jurisdiction": "United Kingdom",
        "narrative": "Burst supply line flooded the warehouse floor.",
        "claim_type": "water_damage",
        "reported_amount": Decimal("85000.00"),
        "scenario_tag": None,
    }
    base.update(overrides)
    return ClaimSubmission(**base)


# --------------------------------------------------------------------------- #
# Repository
# --------------------------------------------------------------------------- #


def test_insert_and_read_back(clean_db: psycopg.Connection) -> None:
    record = ClaimsRepository.insert(clean_db, _submission())
    assert record.status == "received"
    assert record.claim_type == "water_damage"
    assert record.reported_amount == Decimal("85000.00")
    assert record.claim_number.startswith("CLM-2026-")
    assert record.line_of_business == "Commercial Property"  # DB default applied

    fetched = ClaimsRepository.get(clean_db, record.claim_id)
    assert fetched is not None
    assert fetched.claim_id == record.claim_id
    assert fetched.claim_number == record.claim_number


def test_insert_accepts_scenario_tag(clean_db: psycopg.Connection) -> None:
    record = ClaimsRepository.insert(clean_db, _submission(scenario_tag="auto_approve"))
    assert record.scenario_tag == "auto_approve"


def test_get_missing_returns_none(clean_db: psycopg.Connection) -> None:
    assert ClaimsRepository.get(clean_db, uuid4()) is None


def test_update_status_transitions(clean_db: psycopg.Connection) -> None:
    record = ClaimsRepository.insert(clean_db, _submission())
    for status in ("extracted", "coverage_verified", "estimated", "settled"):
        ClaimsRepository.update_status(clean_db, record.claim_id, status)
        fetched = ClaimsRepository.get(clean_db, record.claim_id)
        assert fetched is not None
        assert fetched.status == status


def test_update_status_rejects_unknown_value(clean_db: psycopg.Connection) -> None:
    record = ClaimsRepository.insert(clean_db, _submission())
    with pytest.raises(ValueError) as exc:
        ClaimsRepository.update_status(clean_db, record.claim_id, "in_progress")
    assert "unknown status" in str(exc.value)


def test_update_status_missing_claim_raises(clean_db: psycopg.Connection) -> None:
    with pytest.raises(ValueError) as exc:
        ClaimsRepository.update_status(clean_db, uuid4(), "settled")
    assert "claim not found" in str(exc.value)


def test_list_orders_most_recent_first(clean_db: psycopg.Connection) -> None:
    first = ClaimsRepository.insert(clean_db, _submission(policy_number="POL-1"))
    second = ClaimsRepository.insert(clean_db, _submission(policy_number="POL-2"))
    records = ClaimsRepository.list_claims(clean_db, limit=50)
    assert [r.claim_id for r in records[:2]] == [second.claim_id, first.claim_id]


def test_list_filters_by_status(clean_db: psycopg.Connection) -> None:
    kept = ClaimsRepository.insert(clean_db, _submission())
    other = ClaimsRepository.insert(clean_db, _submission())
    ClaimsRepository.update_status(clean_db, kept.claim_id, "settled")
    settled = ClaimsRepository.list_claims(clean_db, limit=50, status="settled")
    ids = {r.claim_id for r in settled}
    assert kept.claim_id in ids
    assert other.claim_id not in ids


def test_list_rejects_out_of_range_limit(clean_db: psycopg.Connection) -> None:
    with pytest.raises(ValueError) as exc:
        ClaimsRepository.list_claims(clean_db, limit=0)
    assert "limit must be in" in str(exc.value)


# --------------------------------------------------------------------------- #
# ClaimSubmission validation
# --------------------------------------------------------------------------- #


def test_submission_rejects_reversed_dates() -> None:
    with pytest.raises(ValueError) as exc:
        _submission(loss_date=date(2026, 4, 5), reported_date=date(2026, 4, 3))
    assert "must be on or before" in str(exc.value)


def test_submission_rejects_whitespace_jurisdiction() -> None:
    with pytest.raises(ValueError) as exc:
        _submission(jurisdiction="   ")
    assert "empty or whitespace" in str(exc.value)


def test_submission_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError):
        _submission(reported_amount=Decimal("0"))


# --------------------------------------------------------------------------- #
# Drift guard — submittable types must be processable
# --------------------------------------------------------------------------- #


def test_claim_type_literal_matches_market_data_keys() -> None:
    market = yaml.safe_load(MARKET_DATA_PATH.read_text(encoding="utf-8"))
    market_keys = set(market["claim_types"].keys())
    literal_values = set(get_args(ClaimType))
    assert literal_values == market_keys, (
        "ClaimType must match market_data.yaml keys exactly so every submittable "
        f"claim is processable; literal={sorted(literal_values)} "
        f"market={sorted(market_keys)}"
    )
