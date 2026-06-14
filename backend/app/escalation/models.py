"""
Typed shapes for the escalation domain.

These three models are the contract between the escalation engine and its
callers:

  - `PipelineState` — the typed snapshot the engine evaluates. It carries one
    output from each of the four agents, plus the claim and correlation ids.
    The orchestrator assembles it after the Guardrail returns; the engine reads
    it but never mutates it.
  - `FiredRule` — one rule that fired during evaluation, carrying enough context
    (name, type, human description, the observed value for threshold rules) for
    the audit log and the UI to explain *why* a claim escalated.
  - `EscalationDecision` — the engine's verdict: whether to escalate, the full
    list of rules that fired (not just the first), and a composed reasoning
    string.

They live here, in the escalation package rather than the orchestrator package,
so the orchestrator can import them without the escalation engine having to
import back from the orchestrator — a one-directional dependency that avoids a
circular import. The orchestrator re-exports `PipelineState` for ergonomics.

All three lock at end of Phase 4.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.agents.adjuster_models import AdjusterOutput
from backend.app.agents.doc_parser_models import DocParserOutput
from backend.app.agents.guardrail_models import GuardrailOutput
from backend.app.agents.validator_models import ValidatorVerdict

# A rule is either an always-escalate category (`hard`) or a numeric boundary
# check (`threshold`). The distinction is surfaced in the audit log and the UI.
RuleType = Literal["hard", "threshold"]


class FiredRule(BaseModel):
    """One escalation rule that fired during evaluation."""

    model_config = ConfigDict(extra="forbid")

    name: str
    rule_type: RuleType
    description: str
    # Threshold rules record the value they observed (rendered as a string so
    # Decimal/float both serialise cleanly into the audit JSONB). Hard rules
    # have no single comparable value, so this stays None for them.
    observed_value: str | None = None


class EscalationDecision(BaseModel):
    """The escalation engine's verdict for one claim."""

    model_config = ConfigDict(extra="forbid")

    escalate: bool
    # Every rule that fired, in policy order — not just the first. An empty list
    # means no rule fired and `escalate` is False.
    fired_rules: list[FiredRule]
    reasoning: str


class PipelineState(BaseModel):
    """
    The typed snapshot the escalation engine evaluates.

    One output from each agent, assembled by the orchestrator after the
    Guardrail returns. Every field is required: a partially-populated state is
    a programming error, and the engine treats any gap reached at evaluation
    time as a fail-closed escalation rather than a silent pass.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    correlation_id: UUID
    doc_parser_output: DocParserOutput
    validator_verdict: ValidatorVerdict
    adjuster_output: AdjusterOutput
    guardrail_output: GuardrailOutput
