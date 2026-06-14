"""
Pipeline orchestrator — runs the four agents as one composed flow.

`run(...)` reads as a sequence of named helper calls — extract, validate, adjust,
guard, decide, finalise — each delegating to one collaborator and emitting the
right progress event and audit entry. The orchestrator owns three things the
individual agents do not:

  1. **One correlation id end-to-end.** Generated at entry (or injected so an SSE
     client can subscribe first), threaded explicitly into every agent's
     `evaluate(...)` and stamped on every audit entry the orchestrator writes.
  2. **The failure matrix.** Doc-Parser, Validator, or Adjuster throwing aborts
     the run (`aborted`) — the pipeline cannot proceed without their output. The
     Guardrail throwing escalates to a human (`awaiting_human`), because the
     Guardrail's entire contract is fail-closed: a broken safety check must
     never auto-approve. Agent exceptions are never silently converted to
     escalation; only a Guardrail *throw* maps that way, by design.
  3. **The escalation decision.** After the Guardrail returns, the assembled
     `PipelineState` goes to the `EscalationPolicy`, whose typed decision drives
     the terminal status (`settled` vs `awaiting_human`).

The orchestrator is plain and synchronous. It emits progress through an injected
`emit` callback (default no-op); all asyncio lives at the API edge. Collaborators
are typed as Protocols so the real agents satisfy them structurally and tests
pass lightweight stubs.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import psycopg

from backend.app.agents._shared import new_correlation_id
from backend.app.agents.adjuster import Adjuster
from backend.app.agents.adjuster_models import AdjusterOutput, AdjusterResult
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.doc_parser_models import DocParserOutput, DocParserResult
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.guardrail_models import GuardrailOutput, GuardrailResult
from backend.app.agents.validator import Validator
from backend.app.agents.validator_models import (
    RetrievedChunk,
    ValidatorResult,
    ValidatorVerdict,
)
from backend.app.audit import AuditEvent, AuditWriter
from backend.app.claims.repository import ClaimsRepository
from backend.app.escalation import EscalationDecision, EscalationPolicy, PipelineState
from backend.app.escalation.models import FiredRule
from backend.app.llm import get_provider
from backend.app.llm.provider import LLMProviderError
from backend.app.orchestrator.models import (
    AgentCompletedEvent,
    AgentStartedEvent,
    EscalationDecisionEvent,
    EventEmitter,
    FailingAgent,
    PipelineAbortedEvent,
    PipelineCompletedEvent,
    PipelineResult,
    PipelineStartedEvent,
    PipelineStatus,
)
from backend.db.connection import open_connection
from backend.settings import Settings

_logger = logging.getLogger(__name__)

# Exceptions raised by an agent that the orchestrator treats as a step failure.
# Both are audited by the agent itself before it raises; the orchestrator's job
# is to map them onto a pipeline outcome.
_AGENT_ERRORS = (ValueError, LLMProviderError)

# Maximum characters of an exception message we stream / audit. The full content
# already lives in the failing agent's own audit entry; this is a triage excerpt.
_ERROR_MESSAGE_CHARS = 500

# Audit step identifiers written by the orchestrator (agent="orchestrator").
# Locked so downstream queries against the audit log have stable identifiers.
_STEP_STARTED = "pipeline_started"
_STEP_ESCALATION = "escalation_decision"
_STEP_SETTLED = "pipeline_settled"
_STEP_AWAITING = "pipeline_awaiting_human"
_STEP_ABORTED = "pipeline_aborted"

# Claim-status values written as the pipeline progresses (Phase 5). Each mirrors a
# value in the `claims.status` CHECK constraint; the orchestrator advances the
# claim one step per agent completion plus the terminal state at finalisation.
_STATUS_EXTRACTED = "extracted"
_STATUS_COVERAGE_VERIFIED = "coverage_verified"
_STATUS_ESTIMATED = "estimated"
_STATUS_GUARDRAIL_CHECKED = "guardrail_checked"
_STATUS_SETTLED = "settled"
_STATUS_AWAITING_HUMAN = "awaiting_human"

# A sink for claim-status updates: (claim_id, status) -> None. Injected so the
# "status write failure does not abort the pipeline" behaviour is testable, and so
# the orchestrator stays decoupled from the claims repository's connection choice.
StatusWriter = Callable[[UUID, str], None]


# --------------------------------------------------------------------------- #
# Collaborator protocols — the real agents satisfy these structurally.
# --------------------------------------------------------------------------- #


class _DocParserLike(Protocol):
    def evaluate(self, claim_id: UUID, correlation_id: UUID) -> DocParserResult: ...


class _ValidatorLike(Protocol):
    def evaluate(self, claim_id: UUID, correlation_id: UUID) -> ValidatorResult: ...


class _AdjusterLike(Protocol):
    def evaluate(
        self,
        claim_id: UUID,
        correlation_id: UUID,
        *,
        parsed_claim: DocParserOutput,
        validator_verdict: ValidatorVerdict,
    ) -> AdjusterResult: ...


class _GuardrailLike(Protocol):
    def evaluate(
        self,
        claim_id: UUID,
        correlation_id: UUID,
        *,
        adjuster_result: AdjusterResult,
        retrieved_chunks: list[RetrievedChunk],
    ) -> GuardrailResult: ...


# --------------------------------------------------------------------------- #
# Internal control-flow exceptions
# --------------------------------------------------------------------------- #


class _AgentFailure(Exception):
    """An abort-causing agent threw. Carries which agent and the original error."""

    def __init__(self, agent: FailingAgent, original: BaseException) -> None:
        self.agent = agent
        self.original = original
        super().__init__(f"{agent} failed: {type(original).__name__}")


class _GuardrailFailure(Exception):
    """The Guardrail threw — escalate fail-closed rather than abort."""

    def __init__(self, original: BaseException) -> None:
        self.original = original
        super().__init__(f"guardrail failed: {type(original).__name__}")


@dataclass
class _Collected:
    """Mutable accumulator of agent outputs as the pipeline progresses."""

    doc_parser: DocParserOutput | None = None
    validator: ValidatorVerdict | None = None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    adjuster: AdjusterOutput | None = None
    guardrail: GuardrailOutput | None = None


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #


class PipelineOrchestrator:
    """Runs Doc-Parser -> Validator -> Adjuster -> Guardrail -> Escalation."""

    def __init__(
        self,
        *,
        doc_parser: _DocParserLike,
        validator: _ValidatorLike,
        adjuster: _AdjusterLike,
        guardrail: _GuardrailLike,
        policy: EscalationPolicy,
        settings: Settings,
        connection_factory: (
            Callable[[], AbstractContextManager[psycopg.Connection]] | None
        ) = None,
        status_writer: StatusWriter | None = None,
    ) -> None:
        self._doc_parser = doc_parser
        self._validator = validator
        self._adjuster = adjuster
        self._guardrail = guardrail
        self._policy = policy
        self._settings = settings
        self._connection_factory = connection_factory or self._default_connection_factory
        self._status_writer: StatusWriter = status_writer or self._default_status_writer

    @classmethod
    def with_defaults(
        cls,
        settings: Settings,
        *,
        policy: EscalationPolicy,
        status_writer: StatusWriter | None = None,
    ) -> PipelineOrchestrator:
        """Wire the production agent graph from settings and the shared policy."""
        anthropic = get_provider(settings, "anthropic")
        mistral = get_provider(settings, "mistral")
        return cls(
            doc_parser=DocParser.with_defaults(settings, provider=anthropic),
            validator=Validator.with_defaults(settings, provider=mistral),
            adjuster=Adjuster.with_defaults(settings, provider=mistral),
            guardrail=Guardrail.with_defaults(settings, provider=anthropic),
            policy=policy,
            settings=settings,
            status_writer=status_writer,
        )

    def run(
        self,
        claim_id: UUID,
        *,
        correlation_id: UUID | None = None,
        emit: EventEmitter | None = None,
        variant: str = "default",
    ) -> PipelineResult:
        """
        Run the full pipeline synchronously and return the typed outcome.

        `correlation_id` is generated if not supplied; injecting it lets an SSE
        client subscribe before triggering the run. `emit` receives a progress
        event as each step completes; the default discards them. `variant` is
        recorded in the `pipeline_started` audit entry and SSE event so a replay's
        configuration is part of its permanent record — the agent swapping itself
        is done at construction time, not here.
        """
        cid = correlation_id or new_correlation_id()
        sink: EventEmitter = emit or _noop_emit
        collected = _Collected()
        self._start(claim_id, cid, variant, sink)
        try:
            collected.doc_parser = self._extract(claim_id, cid, sink)
            validated = self._validate(claim_id, cid, sink)
            collected.validator = validated.verdict
            collected.chunks = validated.retrieved_chunks
            adjusted = self._adjust(claim_id, cid, collected.doc_parser, validated.verdict, sink)
            collected.adjuster = adjusted.output
            guarded = self._guard(claim_id, cid, adjusted, validated.retrieved_chunks, sink)
            collected.guardrail = guarded.output
        except _GuardrailFailure as exc:
            return self._finalise_guardrail_throw(claim_id, cid, collected, exc, sink)
        except _AgentFailure as exc:
            return self._finalise_abort(claim_id, cid, collected, exc, sink)
        state = self._assemble_state(claim_id, cid, collected)
        decision = self._decide_escalation(state, claim_id, cid, sink)
        return self._finalise(claim_id, cid, collected, decision, sink)

    # ------------------------------------------------------------------ #
    # Pipeline steps
    # ------------------------------------------------------------------ #

    def _extract(self, claim_id: UUID, cid: UUID, sink: EventEmitter) -> DocParserOutput:
        sink(_agent_started("doc_parser", cid))
        t0 = time.perf_counter()
        try:
            result = self._doc_parser.evaluate(claim_id, cid)
        except _AGENT_ERRORS as exc:
            raise _AgentFailure("doc_parser", exc) from exc
        sink(_agent_completed("doc_parser", cid, t0, {"claim_type": result.output.claim_type}))
        self._update_status(claim_id, _STATUS_EXTRACTED)
        return result.output

    def _validate(self, claim_id: UUID, cid: UUID, sink: EventEmitter) -> ValidatorResult:
        sink(_agent_started("validator", cid))
        t0 = time.perf_counter()
        try:
            result = self._validator.evaluate(claim_id, cid)
        except _AGENT_ERRORS as exc:
            raise _AgentFailure("validator", exc) from exc
        sink(_agent_completed("validator", cid, t0, {"covered": result.verdict.covered}))
        self._update_status(claim_id, _STATUS_COVERAGE_VERIFIED)
        return result

    def _adjust(
        self,
        claim_id: UUID,
        cid: UUID,
        parsed: DocParserOutput,
        verdict: ValidatorVerdict,
        sink: EventEmitter,
    ) -> AdjusterResult:
        sink(_agent_started("adjuster", cid))
        t0 = time.perf_counter()
        try:
            result = self._adjuster.evaluate(
                claim_id, cid, parsed_claim=parsed, validator_verdict=verdict
            )
        except _AGENT_ERRORS as exc:
            raise _AgentFailure("adjuster", exc) from exc
        settlement = str(result.output.recommended_settlement)
        sink(_agent_completed("adjuster", cid, t0, {"recommended_settlement": settlement}))
        self._update_status(claim_id, _STATUS_ESTIMATED)
        return result

    def _guard(
        self,
        claim_id: UUID,
        cid: UUID,
        adjuster_result: AdjusterResult,
        chunks: list[RetrievedChunk],
        sink: EventEmitter,
    ) -> GuardrailResult:
        sink(_agent_started("guardrail", cid))
        t0 = time.perf_counter()
        try:
            result = self._guardrail.evaluate(
                claim_id, cid, adjuster_result=adjuster_result, retrieved_chunks=chunks
            )
        except _AGENT_ERRORS as exc:
            # Fail-closed: a broken guardrail escalates, never aborts or approves.
            raise _GuardrailFailure(exc) from exc
        sink(_agent_completed("guardrail", cid, t0, {"passed": result.output.passed}))
        self._update_status(claim_id, _STATUS_GUARDRAIL_CHECKED)
        return result

    def _decide_escalation(
        self, state: PipelineState, claim_id: UUID, cid: UUID, sink: EventEmitter
    ) -> EscalationDecision:
        decision = self._policy.evaluate(state)
        sink(
            EscalationDecisionEvent(
                correlation_id=cid,
                timestamp=_now(),
                escalate=decision.escalate,
                fired_rules=decision.fired_rules,
            )
        )
        self._audit(
            cid,
            claim_id,
            _STEP_ESCALATION,
            {
                "escalate": decision.escalate,
                "fired_rules": [r.model_dump(mode="json") for r in decision.fired_rules],
                "reasoning": decision.reasoning,
            },
        )
        return decision

    # ------------------------------------------------------------------ #
    # Terminal handling
    # ------------------------------------------------------------------ #

    def _finalise(
        self,
        claim_id: UUID,
        cid: UUID,
        collected: _Collected,
        decision: EscalationDecision,
        sink: EventEmitter,
    ) -> PipelineResult:
        status: PipelineStatus = "awaiting_human" if decision.escalate else "settled"
        completed_at = _now()
        step = _STEP_AWAITING if decision.escalate else _STEP_SETTLED
        self._update_status(
            claim_id, _STATUS_AWAITING_HUMAN if decision.escalate else _STATUS_SETTLED
        )
        names = [r.name for r in decision.fired_rules]
        settlement = (
            str(collected.adjuster.recommended_settlement) if collected.adjuster else None
        )
        self._audit(
            cid,
            claim_id,
            step,
            {
                "status": status,
                "escalate": decision.escalate,
                "fired_rule_names": names,
                "settlement": settlement,
                "completed_at": completed_at.isoformat(),
            },
        )
        sink(
            PipelineCompletedEvent(
                correlation_id=cid,
                timestamp=completed_at,
                status=status,
                summary={"escalate": decision.escalate, "fired_rules": names},
            )
        )
        return self._result(status, claim_id, cid, collected, decision, completed_at)

    def _finalise_guardrail_throw(
        self,
        claim_id: UUID,
        cid: UUID,
        collected: _Collected,
        exc: _GuardrailFailure,
        sink: EventEmitter,
    ) -> PipelineResult:
        completed_at = _now()
        message = _sanitise(str(exc.original))
        decision = _fail_closed_guardrail_decision()
        self._update_status(claim_id, _STATUS_AWAITING_HUMAN)
        self._audit(
            cid,
            claim_id,
            _STEP_AWAITING,
            {
                "status": "awaiting_human",
                "escalate": True,
                "fired_rule_names": ["guardrail_failed"],
                "reason": "guardrail_threw",
                "error_type": type(exc.original).__name__,
                "error_message": message,
                "completed_at": completed_at.isoformat(),
            },
        )
        sink(
            PipelineCompletedEvent(
                correlation_id=cid,
                timestamp=completed_at,
                status="awaiting_human",
                summary={"escalate": True, "reason": "guardrail_threw"},
            )
        )
        return self._result("awaiting_human", claim_id, cid, collected, decision, completed_at)

    def _finalise_abort(
        self,
        claim_id: UUID,
        cid: UUID,
        collected: _Collected,
        exc: _AgentFailure,
        sink: EventEmitter,
    ) -> PipelineResult:
        completed_at = _now()
        error_type = type(exc.original).__name__
        message = _sanitise(str(exc.original))
        self._audit(
            cid,
            claim_id,
            _STEP_ABORTED,
            {
                "status": "aborted",
                "failing_agent": exc.agent,
                "error_type": error_type,
                "error_message": message,
                "completed_at": completed_at.isoformat(),
            },
        )
        sink(
            PipelineAbortedEvent(
                correlation_id=cid,
                timestamp=completed_at,
                failing_agent=exc.agent,
                error_type=error_type,
                message=message,
            )
        )
        return self._result(
            "aborted",
            claim_id,
            cid,
            collected,
            None,
            completed_at,
            aborted_agent=exc.agent,
            error_type=error_type,
        )

    # ------------------------------------------------------------------ #
    # Shared builders / plumbing
    # ------------------------------------------------------------------ #

    def _start(
        self, claim_id: UUID, cid: UUID, variant: str, sink: EventEmitter
    ) -> None:
        started_at = _now()
        sink(
            PipelineStartedEvent(
                correlation_id=cid,
                timestamp=started_at,
                claim_id=claim_id,
                variant=variant,
            )
        )
        self._audit(
            cid,
            claim_id,
            _STEP_STARTED,
            {
                "claim_id": str(claim_id),
                "correlation_id": str(cid),
                "variant": variant,
                "started_at": started_at.isoformat(),
            },
        )

    def _assemble_state(
        self, claim_id: UUID, cid: UUID, collected: _Collected
    ) -> PipelineState:
        # All four outputs are guaranteed present here — the try-block in `run`
        # reaches this point only after every agent returned successfully.
        assert collected.doc_parser is not None
        assert collected.validator is not None
        assert collected.adjuster is not None
        assert collected.guardrail is not None
        return PipelineState(
            claim_id=claim_id,
            correlation_id=cid,
            doc_parser_output=collected.doc_parser,
            validator_verdict=collected.validator,
            adjuster_output=collected.adjuster,
            guardrail_output=collected.guardrail,
        )

    def _result(
        self,
        status: PipelineStatus,
        claim_id: UUID,
        cid: UUID,
        collected: _Collected,
        decision: EscalationDecision | None,
        completed_at: datetime,
        *,
        aborted_agent: FailingAgent | None = None,
        error_type: str | None = None,
    ) -> PipelineResult:
        return PipelineResult(
            status=status,
            claim_id=claim_id,
            correlation_id=cid,
            escalation_decision=decision,
            doc_parser_output=collected.doc_parser,
            validator_output=collected.validator,
            adjuster_output=collected.adjuster,
            guardrail_output=collected.guardrail,
            aborted_agent=aborted_agent,
            error_type=error_type,
            completed_at=completed_at,
        )

    def _audit(
        self, cid: UUID, claim_id: UUID, step: str, payload: dict[str, Any]
    ) -> None:
        event = AuditEvent(
            correlation_id=cid,
            claim_id=claim_id,
            agent="orchestrator",
            step=step,
            payload=payload,
            created_at=_now(),
        )
        with self._connection_factory() as conn:
            AuditWriter(conn).append(event)

    def _update_status(self, claim_id: UUID, status: str) -> None:
        """
        Advance the claim's denormalised status. Non-fatal by design.

        The audit_log is the trusted record; `claims.status` is a UI convenience.
        A status-write failure (DB hiccup mid-pipeline) is logged and swallowed so
        a transient denormalisation problem never aborts a run whose audit trail is
        already intact.
        """
        try:
            self._status_writer(claim_id, status)
        except Exception as exc:  # noqa: BLE001 — status is best-effort, see docstring
            _logger.warning(
                "PipelineOrchestrator: status update to %r failed for claim_id=%s "
                "(%s: %s); continuing — audit_log is authoritative",
                status,
                claim_id,
                type(exc).__name__,
                exc,
            )

    def _default_status_writer(self, claim_id: UUID, status: str) -> None:
        """Write the status via `ClaimsRepository`, opening a short-lived connection."""
        with self._connection_factory() as conn:
            ClaimsRepository.update_status(conn, claim_id, status)

    def _default_connection_factory(
        self,
    ) -> AbstractContextManager[psycopg.Connection]:
        return open_connection(self._settings)


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #


def _now() -> datetime:
    return datetime.now(UTC)


def _noop_emit(_event: object) -> None:
    """Default event sink — discards everything."""


def _sanitise(message: str) -> str:
    """Collapse whitespace and truncate so the message is SSE-safe and bounded."""
    collapsed = " ".join(message.split())
    if len(collapsed) <= _ERROR_MESSAGE_CHARS:
        return collapsed
    return collapsed[:_ERROR_MESSAGE_CHARS] + "…"


def _agent_started(agent: FailingAgent, cid: UUID) -> AgentStartedEvent:
    return AgentStartedEvent(correlation_id=cid, timestamp=_now(), agent=agent)


def _agent_completed(
    agent: FailingAgent, cid: UUID, t0: float, summary: dict[str, Any]
) -> AgentCompletedEvent:
    duration_ms = int((time.perf_counter() - t0) * 1000)
    return AgentCompletedEvent(
        correlation_id=cid,
        timestamp=_now(),
        agent=agent,
        duration_ms=duration_ms,
        summary=summary,
    )


def _fail_closed_guardrail_decision() -> EscalationDecision:
    """The synthetic decision recorded when the Guardrail itself threw."""
    return EscalationDecision(
        escalate=True,
        fired_rules=[
            FiredRule(
                name="guardrail_failed",
                rule_type="hard",
                description="Guardrail check raised an exception; failing closed",
            )
        ],
        reasoning="Guardrail evaluation failed; escalating to a human (fail-closed).",
    )
