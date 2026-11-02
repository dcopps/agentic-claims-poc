"""
The three scripted scenarios, by name, for `run_scenario`.

The backend already holds the scenarios' exact copy in
`backend.data.seed_claims.scripted_claims()`; this module maps the three names
an MCP client may use onto those definitions and turns one into the same
`ClaimSubmission` the Claims page would send. Nothing here invents a claim: a
name outside the three is refused before anything is looked up.
"""

from __future__ import annotations

from typing import get_args

from backend.app.claims import ClaimSubmission, ScenarioTag
from backend.app.mcp.models import ScenarioName
from backend.data.seed_claims import SyntheticClaim, scripted_claims

SCENARIO_NAMES: tuple[str, ...] = get_args(ScenarioName)

# Name → the scenario tag the seed data carries. The tag is what the pipeline
# keys on (the Coral Bay tag selects the Adjuster's demo fixture), so it is the
# join between a friendly name and the seeded definition.
_TAG_BY_NAME: dict[str, ScenarioTag] = {
    "harborline": "auto_approve",
    "northwood": "threshold_escalation",
    "coral_bay": "guardrail_escalation",
}


def scenario_tag_for(name: str) -> ScenarioTag:
    """The scenario tag for `name`; raises for any name outside the three."""
    cleaned = name.strip().lower()
    if cleaned not in _TAG_BY_NAME:
        raise ValueError(
            f"run_scenario: unknown scenario {name!r}; expected one of {list(SCENARIO_NAMES)}"
        )
    return _TAG_BY_NAME[cleaned]


def submission_for(name: str) -> ClaimSubmission:
    """The scripted claim for `name` as a fresh submission (claim number assigned on insert)."""
    tag = scenario_tag_for(name)
    claim = _scripted_claim_with_tag(tag)
    return ClaimSubmission(
        claimant_name=claim.claimant_name,
        policy_number=claim.policy_number,
        loss_date=claim.loss_date,
        reported_date=claim.reported_date,
        jurisdiction=claim.jurisdiction,
        narrative=claim.narrative,
        claim_type=claim.claim_type,  # type: ignore[arg-type]  # validated by the model
        reported_amount=claim.reported_amount,
        scenario_tag=tag,
    )


def _scripted_claim_with_tag(tag: ScenarioTag) -> SyntheticClaim:
    matches = [claim for claim in scripted_claims() if claim.scenario_tag == tag]
    # The seed data is the single definition; a missing or doubled tag there is
    # a data defect this module must not paper over.
    if len(matches) != 1:
        raise RuntimeError(
            f"run_scenario: expected exactly one scripted claim tagged {tag!r}; "
            f"found {len(matches)}"
        )
    return matches[0]
