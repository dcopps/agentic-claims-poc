"""The scenario names map onto the seeded definitions, and nothing else is accepted."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.mcp.scenarios import SCENARIO_NAMES, scenario_tag_for, submission_for


def test_the_three_names() -> None:
    assert SCENARIO_NAMES == ("harborline", "northwood", "coral_bay")


@pytest.mark.parametrize(
    ("name", "tag", "claimant", "amount"),
    [
        ("harborline", "auto_approve", "Harborline Logistics Ltd", Decimal("85000.00")),
        ("northwood", "threshold_escalation", "Northwood Manufacturing Inc", Decimal("850000.00")),
        ("coral_bay", "guardrail_escalation", "Coral Bay Holdings", Decimal("1400000.00")),
    ],
)
def test_submission_matches_the_seed(name: str, tag: str, claimant: str, amount: Decimal) -> None:
    submission = submission_for(name)
    assert scenario_tag_for(name) == tag
    assert submission.scenario_tag == tag
    assert submission.claimant_name == claimant
    assert submission.reported_amount == amount


def test_name_is_sanitised() -> None:
    assert scenario_tag_for("  Harborline ") == "auto_approve"


@pytest.mark.parametrize("bad", ["", "northwood-2", "background_claim_01", "*"])
def test_unknown_name_is_refused_with_the_valid_set(bad: str) -> None:
    with pytest.raises(
        ValueError, match="expected one of \\['harborline', 'northwood', 'coral_bay'\\]"
    ):
        submission_for(bad)
