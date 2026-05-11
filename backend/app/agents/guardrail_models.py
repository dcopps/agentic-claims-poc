"""
Typed shapes the Guardrail agent exchanges with its callers.

  - `GuardrailFlagKind` — locked Literal of the three checks the
    Guardrail performs: PII leakage, hallucinated policy citation,
    biased reasoning.
  - `GuardrailFlag` — one finding with a free-text detail string and
    a `source` indicating which detector raised it (the deterministic
    rule engine, or the LLM check). Phase 4 routes a non-empty flag
    list straight to the escalation engine.
  - `GuardrailOutput` — the LLM-populated structured response; the
    fail-closed invariant (`flags non-empty implies passed=False`)
    is enforced by a model validator.
  - `GuardrailResult` — the agent's full typed return.

All four shapes lock at end of Phase 3.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

GuardrailFlagKind = Literal["pii", "bias", "hallucinated_citation"]
GuardrailFlagSource = Literal["rule", "llm"]


class GuardrailFlag(BaseModel):
    """One finding from the rule engine or the LLM check."""

    model_config = ConfigDict(extra="forbid")

    kind: GuardrailFlagKind
    detail: str = Field(min_length=1, max_length=300)
    source: GuardrailFlagSource


class GuardrailOutput(BaseModel):
    """
    Strict combined output. `passed` is the headline boolean Phase 4's
    escalation engine reads; `flags` is the diagnostic list. The
    cross-validator enforces fail-closed: if any flag is present,
    `passed` MUST be `False`.
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    flags: list[GuardrailFlag] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _fail_closed(self) -> GuardrailOutput:
        if self.flags and self.passed:
            raise ValueError(
                "GuardrailOutput: flags present but passed=True — fail-closed "
                f"contract violated; flag_count={len(self.flags)}"
            )
        if not self.flags and not self.passed:
            # Symmetric guard. If the flag list is empty there is
            # nothing for the escalation engine to act on; passed
            # should reflect that. A direct caller that wants to set
            # passed=False without a flag must supply one.
            raise ValueError(
                "GuardrailOutput: passed=False with no flags — supply at "
                "least one flag explaining the failure"
            )
        return self


class GuardrailResult(BaseModel):
    """Full Guardrail output, ready for the orchestrator."""

    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    correlation_id: UUID
    output: GuardrailOutput
    model: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)
