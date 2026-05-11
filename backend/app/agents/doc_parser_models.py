"""
Typed shapes the Doc-Parser agent exchanges with its callers.

Two layers:

  - `DocParserOutput` — the JSON-shaped model the LLM populates from
    a free-text claim narrative. Field bounds and Pydantic types are
    the contract; a model output that fails any constraint is a hard
    parse failure, not a "best effort" coercion.
  - `DocParserResult` — the agent's typed return, wrapping the
    `DocParserOutput` with the run metadata Phase 4's orchestrator
    needs (claim id, correlation id, model identifier, latency).

Both shapes lock at end of Phase 3.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocParserOutput(BaseModel):
    """
    Strict JSON contract for the Doc-Parser LLM's structured extraction.

    All bounds intentional:
      - `claimed_amount` must be strictly positive — a zero or negative
        loss value is a parser confusion, not a legitimate datum.
      - `loss_date` is a real `date` so an ISO 8601 string from the
        model is parsed and validated up front (impossible day-of-month
        rejected by Pydantic itself).
      - String length caps keep an over-eager model from dumping the
        entire narrative back as the summary or as a field value.
    """

    model_config = ConfigDict(extra="forbid")

    loss_date: date
    jurisdiction: str = Field(min_length=1, max_length=120)
    claim_type: str = Field(min_length=1, max_length=64)
    claimed_amount: Decimal = Field(gt=Decimal("0"))
    claimant_identifier: str = Field(min_length=1, max_length=200)
    narrative_summary: str = Field(min_length=1, max_length=500)


class DocParserResult(BaseModel):
    """
    Full Doc-Parser output, ready for the orchestrator and downstream
    agents. The orchestrator threads `output` through to the Adjuster
    in Phase 4; the wrapping metadata (claim id, correlation id,
    model, latency) is for traceability rather than business logic.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    correlation_id: UUID
    output: DocParserOutput
    model: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)
