"""
seed_claims tests — primarily generator behaviour, with one DB-backed
insert + readback to confirm the round trip.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

import psycopg

from backend.data.seed_claims import (
    JURISDICTIONS,
    SCENARIO_TAGS,
    generate_claims,
    insert_claims,
)


def test_generator_produces_nine_claims() -> None:
    claims = generate_claims()
    assert len(claims) == 9


def test_each_scripted_scenario_appears_exactly_once() -> None:
    claims = generate_claims()
    tags = Counter(c.scenario_tag for c in claims)
    for scenario in SCENARIO_TAGS:
        assert tags[scenario] == 1
    # Six untagged background claims.
    assert tags[None] == 6


def test_jurisdictions_drawn_from_locked_set() -> None:
    claims = generate_claims()
    for c in claims:
        assert c.jurisdiction in JURISDICTIONS


def test_generator_is_reproducible_byte_for_byte() -> None:
    a = generate_claims()
    b = generate_claims()
    assert [c.as_db_row() for c in a] == [c.as_db_row() for c in b]


def test_claim_numbers_are_unique() -> None:
    claims = generate_claims()
    numbers = [c.claim_number for c in claims]
    assert len(numbers) == len(set(numbers))


def test_reported_amounts_are_strictly_positive() -> None:
    for c in generate_claims():
        assert c.reported_amount > Decimal("0")


def test_insert_refuses_non_empty_table_without_truncate(
    clean_db: psycopg.Connection,
) -> None:
    claims = generate_claims()
    insert_claims(clean_db, claims, truncate_first=False)

    import pytest

    with pytest.raises(ValueError) as excinfo:
        insert_claims(clean_db, claims, truncate_first=False)
    assert "non-empty" in str(excinfo.value)


def test_insert_with_truncate_overwrites_cleanly(
    clean_db: psycopg.Connection,
) -> None:
    claims = generate_claims()
    insert_claims(clean_db, claims, truncate_first=False)
    inserted = insert_claims(clean_db, claims, truncate_first=True)
    assert inserted == 9

    with clean_db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM claims")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 9


# --------------------------------------------------------------------------- #
# Phase 8 — demo narratives embed the dollar figure (Doc-Parser extracts it).
# --------------------------------------------------------------------------- #

import pytest  # noqa: E402

_EXPECTED_AMOUNTS = {
    "auto_approve": "$85,000",
    "threshold_escalation": "$850,000",
    "guardrail_escalation": "$1,400,000",
}


@pytest.mark.parametrize(("tag", "amount"), list(_EXPECTED_AMOUNTS.items()))
def test_demo_narrative_contains_dollar_figure(tag: str, amount: str) -> None:
    claim = next(c for c in generate_claims() if c.scenario_tag == tag)
    assert amount in claim.narrative, (
        f"demo narrative for {tag} must mention {amount} so Doc-Parser can "
        f"extract claimed_amount; got: {claim.narrative!r}"
    )
