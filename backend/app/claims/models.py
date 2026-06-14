"""
Typed shapes for the claims domain.

Two request/response layers plus three locked enumerations:

  - `ClaimStatus` — the seven lifecycle values, matching the `claims.status`
    CHECK constraint exactly. The orchestrator advances a claim through these as
    the pipeline runs.
  - `ClaimType` — the six claim types the pipeline can actually process. It is a
    strict subset of what the DB allows: a submitted claim must map to a cell in
    `market_data.yaml`, or the Adjuster would abort. (Seeded background claims use
    other types but are never submitted through this path.)
  - `ScenarioTag` — the three demo-scenario tags, matching the CHECK constraint.
  - `ClaimSubmission` — the request body for `POST /api/claims`: the minimum fields
    needed to drive the pipeline. `claim_id` and `claim_number` are generated
    server-side, so they are absent here.
  - `ClaimRecord` — the full persisted row, returned by every claims endpoint.

`ClaimSubmission` validates defensively; `ClaimRecord` types the DB row. They lock
at end of Phase 5.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ClaimStatus = Literal[
    "received",
    "extracted",
    "coverage_verified",
    "estimated",
    "guardrail_checked",
    "settled",
    "awaiting_human",
]

# The six claim types with a cell in market_data.yaml. A drift guard test asserts
# this Literal matches the market-data keys so the two cannot diverge silently.
ClaimType = Literal[
    "water_damage",
    "fire",
    "wind",
    "theft",
    "flood",
    "storm_complex",
]

ScenarioTag = Literal[
    "auto_approve",
    "threshold_escalation",
    "guardrail_escalation",
]


class ClaimSubmission(BaseModel):
    """Request body for `POST /api/claims` — the pipeline-driving fields only."""

    model_config = ConfigDict(extra="forbid")

    claimant_name: str = Field(min_length=1, max_length=200)
    policy_number: str = Field(min_length=1, max_length=60)
    loss_date: date
    reported_date: date
    jurisdiction: str = Field(min_length=1, max_length=120)
    narrative: str = Field(min_length=1, max_length=5000)
    claim_type: ClaimType
    reported_amount: Decimal = Field(gt=Decimal("0"))
    scenario_tag: ScenarioTag | None = None

    @field_validator(
        "claimant_name", "policy_number", "jurisdiction", "narrative", mode="after"
    )
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        # Reject whitespace-only input: the length bound alone would pass "   ".
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty or whitespace after stripping")
        return cleaned

    @model_validator(mode="after")
    def _dates_ordered(self) -> ClaimSubmission:
        # A loss cannot be reported before it occurred. Catching it here keeps a
        # transposed pair out of the pipeline and the audit record.
        if self.loss_date > self.reported_date:
            raise ValueError(
                f"loss_date {self.loss_date.isoformat()} must be on or before "
                f"reported_date {self.reported_date.isoformat()}"
            )
        return self


class ClaimRecord(BaseModel):
    """The full persisted `claims` row, returned by every claims endpoint."""

    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    claim_number: str
    line_of_business: str
    claimant_name: str
    policy_number: str
    loss_date: date
    reported_date: date
    jurisdiction: str
    narrative: str
    # `str`, not `ClaimType`: the table also holds seeded background claims whose
    # types sit outside the processable set, and the list endpoint returns them.
    claim_type: str
    reported_amount: Decimal
    status: ClaimStatus
    scenario_tag: ScenarioTag | None
    created_at: datetime
    updated_at: datetime
