"""
Typed shapes the Adjuster agent exchanges with its callers.

Two layers:

  - `AdjusterOutput` — the JSON-shaped model the LLM populates. The
    model is instructed to pick a settlement value *within* a range
    the Adjuster has already looked up in the market-data table.
  - `AdjusterResult` — the agent's full typed return, wrapping the
    `AdjusterOutput` with the `MarketRange` used, the run metadata,
    and a `model_validator` that re-asserts the within-range
    invariant. Defence-in-depth: Phase 4 may construct
    `AdjusterResult` directly when replaying from the audit log;
    the cross-validator guarantees the invariant survives that path.

Both shapes lock at end of Phase 3.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.data.market_data import MarketRange


class AdjusterOutput(BaseModel):
    """
    Strict JSON contract for the Adjuster LLM's structured response.

    The model is asked for a single settlement value, a confidence
    score, and a reasoning paragraph. The reasoning is *not* asked to
    cite policy — that constraint is in the system prompt, and the
    Guardrail re-checks it downstream.
    """

    model_config = ConfigDict(extra="forbid")

    recommended_settlement: Decimal = Field(gt=Decimal("0"))
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=2000)


class AdjusterResult(BaseModel):
    """
    Full Adjuster output: the LLM's structured response, the
    `MarketRange` it was constrained to, plus run metadata. Phase 4
    consumes this shape directly; the orchestrator threads it to the
    Guardrail.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    correlation_id: UUID
    output: AdjusterOutput
    market_range: MarketRange
    model: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _settlement_within_range(self) -> AdjusterResult:
        # The Adjuster's parse step already enforces this invariant
        # when the model's value comes back. Re-asserting here covers
        # the case where `AdjusterResult` is constructed by a future
        # caller (e.g. an audit-log replay) — direct construction is
        # not allowed to break the contract.
        if not self.market_range.contains(self.output.recommended_settlement):
            raise ValueError(
                "AdjusterResult: recommended_settlement "
                f"{self.output.recommended_settlement} falls outside the "
                f"market range [{self.market_range.floor}, "
                f"{self.market_range.ceiling}] for "
                f"({self.market_range.claim_type}, "
                f"{self.market_range.severity})"
            )
        return self
