"""
Typed shapes for the MCP surface.

Three families:

  - **The tool-call record** (`ToolCallRecord`, `TargetRef`): one shape for the
    table row, the structured log line, the activity-bus message and the SSE
    frame, so the four can never disagree.
  - **Tool results**: what each read tool returns. Where an existing model
    already says it (`ClaimRecord`, `RunSummary`, `PipelineResult`,
    `RunComparison`, `AuditEntry`), it is embedded rather than re-described.
  - **The decision explanation** (`DecisionExplanation` and its sections): the
    composed account of one run, every statement tagged with the audit row it
    came from. Amounts are strings here because that is how the ledger holds
    them; the explanation never re-interprets a recorded value.

Every model is `extra="forbid"`: a stray key is a composer bug, not data.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.agents.guardrail_llm_flags import CountedLLMFlag, DiscardedLLMFlag
from backend.app.agents.guardrail_models import GuardrailFlag
from backend.app.audit.repository import AuditEntry
from backend.app.claims import ClaimRecord
from backend.app.escalation.models import FiredRule
from backend.app.orchestrator import PipelineResult
from backend.app.runs import RunSummary

# --------------------------------------------------------------------------- #
# The tool-call record
# --------------------------------------------------------------------------- #

ToolOutcome = Literal["ok", "error"]
TargetKind = Literal["claim", "run"]


class TargetRef(BaseModel):
    """The claim or run a call concerned — the first id when a tool takes two."""

    model_config = ConfigDict(extra="forbid")

    kind: TargetKind
    id: UUID


class ToolCallRecord(BaseModel):
    """
    One recorded tool call.

    `call_id` is None until the row is written; the recorder returns the stored
    copy with the id the table assigned, and that id is the SSE event id the
    feed deduplicates on. `arguments` are the tool's parameters as received —
    ids, a status, a flag, a scenario name — never free text and never a secret.
    `caller` is the token's label from settings, never its value.
    """

    model_config = ConfigDict(extra="forbid")

    call_id: int | None = None
    called_at: datetime
    tool: str = Field(min_length=1)
    arguments: dict[str, Any]
    target: TargetRef | None
    caller: str = Field(min_length=1)
    outcome: ToolOutcome
    error_class: str | None
    latency_ms: int = Field(ge=0)


# --------------------------------------------------------------------------- #
# Tool results
# --------------------------------------------------------------------------- #


class ClaimListItem(BaseModel):
    """One claim in a listing, with how many runs have been started on it."""

    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    claim_number: str
    claimant_name: str
    claim_type: str
    reported_amount: Decimal
    status: str
    scenario_tag: str | None
    run_count: int = Field(ge=0)


class ClaimListing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[ClaimListItem]


class ClaimView(BaseModel):
    """The claim record and every run that targeted it, most recent first."""

    model_config = ConfigDict(extra="forbid")

    claim: ClaimRecord
    runs: list[RunSummary]


class AgentRow(BaseModel):
    """
    One agent's audit row, for timing.

    The ledger records when the row was written and how long the model call
    took; it does not record an agent's wall time, so `model_latency_ms` is the
    timing the record actually holds. `demo_fixture` marks the Adjuster path
    that made no model call.
    """

    model_config = ConfigDict(extra="forbid")

    agent: str
    step: str
    audit_id: int
    recorded_at: datetime
    model_latency_ms: int | None
    provider: str | None
    model: str | None
    demo_fixture: bool


class RunView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: PipelineResult
    agents: list[AgentRow]


class AuditTrail(BaseModel):
    """
    A run's rows in chain order.

    When `prompts_included` is false each row's `llm_call.prompt` has been
    removed, so the payload shown will not re-hash to its `row_hash`; the chain
    hash is reported as stored, and `verify_chain` is the tool that checks it.
    """

    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    prompts_included: bool
    entries: list[AuditEntry]


class ChainBreak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: int
    kind: str
    expected: str
    actual: str


class ChainVerificationReport(BaseModel):
    """
    The chain check, honestly scoped.

    The hash chain links every row of the ledger in order, so a run cannot be
    verified in isolation; `scope` says so and `run_rows` says how many of the
    checked rows belong to the run asked about.
    """

    model_config = ConfigDict(extra="forbid")

    scope: Literal["whole_ledger"]
    ok: bool
    rows_checked: int = Field(ge=0)
    first_break: ChainBreak | None
    run_rows: int = Field(ge=0)


ScenarioName = Literal["harborline", "northwood", "coral_bay"]


class ScenarioRun(BaseModel):
    """What `run_scenario` returns once the pipeline has finished."""

    model_config = ConfigDict(extra="forbid")

    scenario: ScenarioName
    claim_id: UUID
    correlation_id: UUID
    status: str
    fired_rule_names: list[str]
    settlement: str | None


# --------------------------------------------------------------------------- #
# The decision explanation
# --------------------------------------------------------------------------- #


class SourceRef(BaseModel):
    """The audit row a statement came from — the evidence tag on every section."""

    model_config = ConfigDict(extra="forbid")

    audit_id: int
    agent: str
    step: str
    recorded_at: datetime
    chain_hash: str


class PassageSeen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    section: str
    similarity: float


class PassageCited(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    section: str


class CoverageExplanation(BaseModel):
    """The Validator's verdict and the policy passages it was shown."""

    model_config = ConfigDict(extra="forbid")

    covered: bool
    confidence: float
    policy_basis: str
    reasoning: str
    passages_seen: list[PassageSeen]
    passages_cited: list[PassageCited]
    source: SourceRef


class SettlementRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_type: str
    severity: str
    floor: str
    ceiling: str


class SettlementExplanation(BaseModel):
    """The Adjuster's figure, the range it was held to, and its reasoning."""

    model_config = ConfigDict(extra="forbid")

    recommended: str
    confidence: float
    range: SettlementRange | None
    reasoning: str
    demo_fixture: bool
    source: SourceRef


class GuardrailExplanation(BaseModel):
    """
    What the Guardrail found, and what the model claimed that code refused.

    `llm_verification_recorded` is false for rows written before `0.9.1.2`,
    which carry no `llm_flags_*` keys; the two lists are then empty because
    nothing was recorded, not because nothing was claimed.
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    summary: str
    rule_engine_flags: list[GuardrailFlag]
    llm_flags_counted: list[CountedLLMFlag]
    llm_flags_discarded: list[DiscardedLLMFlag]
    llm_verification_recorded: bool
    source: SourceRef


class EscalationExplanation(BaseModel):
    """
    The rules that fired. `reconstructed` is true when the Guardrail threw and
    no `escalation_decision` row exists; the account then comes from the
    terminal row, exactly as the Run page's reconstruction does.
    """

    model_config = ConfigDict(extra="forbid")

    escalate: bool
    reasoning: str
    fired_rules: list[FiredRule]
    reconstructed: bool
    source: SourceRef


OutcomeStatus = Literal["settled", "awaiting_human", "aborted", "running"]


class OutcomeExplanation(BaseModel):
    """The terminal row. `running` means no terminal row has been written yet."""

    model_config = ConfigDict(extra="forbid")

    status: OutcomeStatus
    settlement: str | None
    fired_rule_names: list[str]
    failing_agent: str | None
    error_type: str | None
    source: SourceRef | None


class HumanDecisionExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str
    decided_by: str
    comment: str | None
    decided_at: str
    source: SourceRef


class ModelUse(BaseModel):
    """Which provider and model an agent row records — `demo_fixture` records none."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    provider: str
    model: str | None
    requested_model: str | None
    latency_ms: int | None
    source: SourceRef


class DecisionExplanation(BaseModel):
    """The composed account of one run, every section tagged with its row."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    claim_id: UUID
    claim_number: str
    claimant_name: str
    variant: str
    started_at: datetime | None
    completed_at: datetime | None
    outcome: OutcomeExplanation
    coverage: CoverageExplanation | None
    settlement: SettlementExplanation | None
    guardrail: GuardrailExplanation | None
    escalation: EscalationExplanation | None
    human_decision: HumanDecisionExplanation | None
    models: list[ModelUse]
    chain: ChainVerificationReport
