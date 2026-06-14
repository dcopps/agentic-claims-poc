"""
Typed shapes the pipeline orchestrator produces.

Two families:

  - `PipelineResult` — the synchronous outcome of one pipeline run. It carries
    the final status, every agent's output (or None where the pipeline aborted
    before that agent ran), and the escalation decision. This is the body the
    `POST /api/pipeline/run/{claim_id}` endpoint returns and the shape Phases 5
    and 6 consume.
  - `PipelineEvent` — the SSE progress events streamed as each step completes.
    A discriminated union over `event_type`; each event's `event_type` value is
    also its SSE `event:` name.

The escalation types (`PipelineState`, `EscalationDecision`, `FiredRule`) are
re-exported from `backend.app.escalation` so a consumer has a single import
surface for everything the orchestrator deals in. They are *defined* in the
escalation package to keep the dependency one-directional (orchestrator depends
on escalation, never the reverse).

All shapes lock at end of Phase 4.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.agents.adjuster_models import AdjusterOutput
from backend.app.agents.doc_parser_models import DocParserOutput
from backend.app.agents.guardrail_models import GuardrailOutput
from backend.app.agents.validator_models import ValidatorVerdict
from backend.app.escalation.models import (
    EscalationDecision,
    FiredRule,
    PipelineState,
    RuleType,
)

__all__ = [
    "AgentCompletedEvent",
    "AgentStartedEvent",
    "EscalationDecision",
    "EscalationDecisionEvent",
    "EventEmitter",
    "FailingAgent",
    "FiredRule",
    "PipelineAbortedEvent",
    "PipelineCompletedEvent",
    "PipelineEvent",
    "PipelineResult",
    "PipelineStartedEvent",
    "PipelineState",
    "PipelineStatus",
    "RuleType",
]

# The three terminal states of a run. `settled` = auto-approved; `awaiting_human`
# = escalated (by a fired rule or a fail-closed guardrail); `aborted` = an agent
# the pipeline depends on threw and the run could not complete.
PipelineStatus = Literal["settled", "awaiting_human", "aborted"]

# The four agents that can be named as the cause of an abort. Narrower than the
# audit `AgentName` literal (which also has `system` / `orchestrator`) because
# only these four are pipeline steps that can fail mid-run.
FailingAgent = Literal["doc_parser", "validator", "adjuster", "guardrail"]


class PipelineResult(BaseModel):
    """The synchronous outcome of one pipeline run."""

    model_config = ConfigDict(extra="forbid")

    status: PipelineStatus
    claim_id: UUID
    correlation_id: UUID
    # None only when the run aborted before escalation was reached.
    escalation_decision: EscalationDecision | None
    # Each agent's output, populated as far as the pipeline got. On abort, the
    # agents that ran are present and the rest are None — the result stays
    # inspectable so a reader can see where the run stopped.
    doc_parser_output: DocParserOutput | None
    validator_output: ValidatorVerdict | None
    adjuster_output: AdjusterOutput | None
    guardrail_output: GuardrailOutput | None
    # Set only when status == "aborted".
    aborted_agent: FailingAgent | None = None
    # The failing exception's class name only — never its message. The message
    # can carry unsanitised detail, so it lives in the audit vault (the trusted
    # record), not on this object which crosses the HTTP boundary.
    error_type: str | None = None
    completed_at: datetime


# --------------------------------------------------------------------------- #
# SSE events
# --------------------------------------------------------------------------- #


class _BaseEvent(BaseModel):
    """Fields every pipeline event carries."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    timestamp: datetime


class PipelineStartedEvent(_BaseEvent):
    event_type: Literal["pipeline_started"] = "pipeline_started"
    claim_id: UUID


class AgentStartedEvent(_BaseEvent):
    event_type: Literal["agent_started"] = "agent_started"
    agent: FailingAgent


class AgentCompletedEvent(_BaseEvent):
    event_type: Literal["agent_completed"] = "agent_completed"
    agent: FailingAgent
    duration_ms: int
    # One or two headline fields for the UI, e.g. {"covered": true} for the
    # Validator or {"recommended_settlement": "85000.00"} for the Adjuster.
    summary: dict[str, Any] = Field(default_factory=dict)


class EscalationDecisionEvent(_BaseEvent):
    event_type: Literal["escalation_decision"] = "escalation_decision"
    escalate: bool
    fired_rules: list[FiredRule]


class PipelineCompletedEvent(_BaseEvent):
    event_type: Literal["pipeline_completed"] = "pipeline_completed"
    status: PipelineStatus
    summary: dict[str, Any] = Field(default_factory=dict)


class PipelineAbortedEvent(_BaseEvent):
    event_type: Literal["pipeline_aborted"] = "pipeline_aborted"
    failing_agent: FailingAgent
    error_type: str
    # Sanitised + truncated upstream; safe to stream.
    message: str


# Discriminated over `event_type`. `pipeline_completed` and `pipeline_aborted`
# are the terminal events — the bus closes the stream after either.
PipelineEvent = (
    PipelineStartedEvent
    | AgentStartedEvent
    | AgentCompletedEvent
    | EscalationDecisionEvent
    | PipelineCompletedEvent
    | PipelineAbortedEvent
)

# A synchronous sink for pipeline events. The orchestrator calls it as each step
# completes; the default is a no-op. The API layer supplies one that bridges,
# thread-safely, to the asyncio event bus — keeping all asyncio at the edge so
# the orchestrator itself stays plain and synchronous.
EventEmitter = Callable[[PipelineEvent], None]
