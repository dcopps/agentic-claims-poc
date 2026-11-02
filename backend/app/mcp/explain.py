"""
Compose the account of one run from its audit rows — nothing else.

`compose_explanation` is a pure function over the claim record, the run's
rows in chain order and the chain-check result. Every section it produces is
tagged with the row it came from, so a reader can go from any statement to the
ledger entry behind it. It never calls a model, never re-evaluates a rule and
never fills a gap: a section whose row is absent is `None`, a verification the
row does not record is reported as not recorded.

`strip_prompts` is the one transformation `get_audit_trail` applies by default:
the literal prompts each agent sent are large and are the only part of a row a
casual reader does not need; removing them changes the payload, so the trail
says so.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any
from uuid import UUID

from backend.app.agents.guardrail_llm_flags import CountedLLMFlag, DiscardedLLMFlag
from backend.app.agents.guardrail_models import GuardrailFlag
from backend.app.audit.repository import AuditEntry
from backend.app.audit.verify import ChainVerification
from backend.app.claims import ClaimRecord
from backend.app.escalation.models import FiredRule
from backend.app.mcp.models import (
    AgentRow,
    ChainBreak,
    ChainVerificationReport,
    CoverageExplanation,
    DecisionExplanation,
    EscalationExplanation,
    GuardrailExplanation,
    HumanDecisionExplanation,
    ModelUse,
    OutcomeExplanation,
    OutcomeStatus,
    PassageCited,
    PassageSeen,
    SettlementExplanation,
    SettlementRange,
    SourceRef,
)

# Terminal step → the outcome it records. Mirrors `RunsRepository._TERMINAL_STEPS`.
_TERMINAL_STATUS: dict[str, OutcomeStatus] = {
    "pipeline_settled": "settled",
    "pipeline_awaiting_human": "awaiting_human",
    "pipeline_aborted": "aborted",
}
_AGENT_STEPS = ("doc_extract", "coverage_check", "settlement_estimate", "output_check")
_HUMAN_STEPS = ("human_approval", "human_rejection")


def compose_explanation(
    correlation_id: UUID,
    claim: ClaimRecord,
    entries: list[AuditEntry],
    verification: ChainVerification,
) -> DecisionExplanation:
    """Build the explanation. `entries` must be the run's rows in chain order, non-empty."""
    if not entries:
        raise ValueError(f"compose_explanation: run {correlation_id} has no audit rows to explain")
    by_step = {entry.step: entry for entry in entries}
    started = by_step.get("pipeline_started")
    terminal = _terminal_entry(by_step)
    return DecisionExplanation(
        correlation_id=correlation_id,
        claim_id=claim.claim_id,
        claim_number=claim.claim_number,
        claimant_name=claim.claimant_name,
        variant=started.payload.get("variant", "default") if started else "default",
        started_at=_timestamp(started.payload.get("started_at")) if started else None,
        completed_at=_timestamp(terminal.payload.get("completed_at")) if terminal else None,
        outcome=_outcome(terminal),
        coverage=_coverage(by_step.get("coverage_check")),
        settlement=_settlement(by_step.get("settlement_estimate")),
        guardrail=_guardrail(by_step.get("output_check")),
        escalation=_escalation(by_step.get("escalation_decision"), terminal),
        human_decision=_human_decision(by_step),
        models=[use for entry in entries if (use := _model_use(entry)) is not None],
        chain=chain_report(verification, run_rows=len(entries)),
    )


def chain_report(verification: ChainVerification, *, run_rows: int) -> ChainVerificationReport:
    """The verifier's result under the honest scope label."""
    first_break = (
        ChainBreak(
            audit_id=verification.first_break.audit_id,
            kind=verification.first_break.kind,
            expected=verification.first_break.expected,
            actual=verification.first_break.actual,
        )
        if verification.first_break is not None
        else None
    )
    return ChainVerificationReport(
        scope="whole_ledger",
        ok=verification.ok,
        rows_checked=verification.rows_checked,
        first_break=first_break,
        run_rows=run_rows,
    )


def agent_rows(entries: list[AuditEntry]) -> list[AgentRow]:
    """The timing each agent row records, for `get_run`."""
    rows = []
    for entry in entries:
        if entry.step not in _AGENT_STEPS:
            continue
        call = entry.payload.get("llm_call") or {}
        rows.append(
            AgentRow(
                agent=entry.agent,
                step=entry.step,
                audit_id=entry.audit_id,
                recorded_at=entry.created_at,
                model_latency_ms=call.get("latency_ms"),
                provider=call.get("provider"),
                model=call.get("model"),
                demo_fixture=bool(entry.payload.get("demo_fixture", False)),
            )
        )
    return rows


def strip_prompts(payload: dict[str, Any]) -> dict[str, Any]:
    """A copy of `payload` without `llm_call.prompt`; the original is untouched."""
    stripped = copy.deepcopy(payload)
    call = stripped.get("llm_call")
    if isinstance(call, dict):
        call.pop("prompt", None)
    return stripped


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _source(entry: AuditEntry) -> SourceRef:
    return SourceRef(
        audit_id=entry.audit_id,
        agent=entry.agent,
        step=entry.step,
        recorded_at=entry.created_at,
        chain_hash=entry.chain_hash,
    )


def _outcome(terminal: AuditEntry | None) -> OutcomeExplanation:
    if terminal is None:
        return OutcomeExplanation(
            status="running",
            settlement=None,
            fired_rule_names=[],
            failing_agent=None,
            error_type=None,
            source=None,
        )
    payload = terminal.payload
    return OutcomeExplanation(
        status=_TERMINAL_STATUS[terminal.step],
        settlement=_optional_str(payload.get("settlement")),
        fired_rule_names=list(payload.get("fired_rule_names", [])),
        failing_agent=payload.get("failing_agent"),
        error_type=payload.get("error_type"),
        source=_source(terminal),
    )


def _coverage(entry: AuditEntry | None) -> CoverageExplanation | None:
    verdict = entry.payload.get("verdict") if entry is not None else None
    if entry is None or verdict is None:
        return None
    chunks = (entry.payload.get("retrieval") or {}).get("chunks", [])
    return CoverageExplanation(
        covered=verdict["covered"],
        confidence=verdict["confidence"],
        policy_basis=verdict.get("policy_basis", ""),
        reasoning=verdict.get("reasoning", ""),
        passages_seen=[
            PassageSeen(
                chunk_id=str(chunk["chunk_id"]),
                section=chunk["section"],
                similarity=chunk["similarity"],
            )
            for chunk in chunks
        ],
        passages_cited=[
            PassageCited(chunk_id=str(cited["chunk_id"]), section=cited["section"])
            for cited in verdict.get("cited_chunks", [])
        ],
        source=_source(entry),
    )


def _settlement(entry: AuditEntry | None) -> SettlementExplanation | None:
    output = entry.payload.get("output") if entry is not None else None
    if entry is None or output is None:
        return None
    market = entry.payload.get("market_data")
    return SettlementExplanation(
        recommended=str(output["recommended_settlement"]),
        confidence=output["confidence"],
        range=SettlementRange(
            claim_type=str(market["claim_type"]),
            severity=str(market["severity"]),
            floor=str(market["floor"]),
            ceiling=str(market["ceiling"]),
        )
        if market is not None
        else None,
        # The full reasoning since Phase 5; the excerpt only for older rows.
        reasoning=output.get("reasoning") or output.get("reasoning_excerpt", ""),
        demo_fixture=bool(entry.payload.get("demo_fixture", False)),
        source=_source(entry),
    )


def _guardrail(entry: AuditEntry | None) -> GuardrailExplanation | None:
    output = entry.payload.get("output") if entry is not None else None
    if entry is None or output is None:
        return None
    payload = entry.payload
    # Rows before 0.9.1.2 carry neither key: absence means no verification was
    # performed, which is a different fact from "nothing was claimed".
    recorded = "llm_flags_counted" in payload and "llm_flags_discarded" in payload
    rule_flags = (payload.get("rule_checks") or {}).get("flags", [])
    return GuardrailExplanation(
        passed=output["passed"],
        summary=output.get("summary", ""),
        rule_engine_flags=[GuardrailFlag.model_validate(flag) for flag in rule_flags],
        llm_flags_counted=[
            CountedLLMFlag.model_validate(flag) for flag in payload.get("llm_flags_counted", [])
        ],
        llm_flags_discarded=[
            DiscardedLLMFlag.model_validate(flag) for flag in payload.get("llm_flags_discarded", [])
        ],
        llm_verification_recorded=recorded,
        source=_source(entry),
    )


def _escalation(
    decision: AuditEntry | None, terminal: AuditEntry | None
) -> EscalationExplanation | None:
    if decision is not None:
        payload = decision.payload
        return EscalationExplanation(
            escalate=payload["escalate"],
            reasoning=payload.get("reasoning", ""),
            fired_rules=[FiredRule.model_validate(rule) for rule in payload.get("fired_rules", [])],
            reconstructed=False,
            source=_source(decision),
        )
    # A Guardrail throw escalates fail-closed without a policy evaluation, so no
    # decision row exists; the terminal row is the only record, as on the Run page.
    if terminal is not None and terminal.payload.get("reason") == "guardrail_threw":
        names = terminal.payload.get("fired_rule_names", [])
        return EscalationExplanation(
            escalate=True,
            reasoning="Guardrail evaluation failed; escalated fail-closed (reconstructed).",
            fired_rules=[
                FiredRule(name=name, rule_type="hard", description=f"{name} (reconstructed)")
                for name in names
            ],
            reconstructed=True,
            source=_source(terminal),
        )
    return None


def _human_decision(by_step: dict[str, AuditEntry]) -> HumanDecisionExplanation | None:
    for step in _HUMAN_STEPS:
        entry = by_step.get(step)
        if entry is None:
            continue
        payload = entry.payload
        return HumanDecisionExplanation(
            decision=str(payload.get("decision", step)),
            decided_by=str(payload.get("decided_by", "")),
            comment=payload.get("comment"),
            decided_at=str(payload.get("decided_at", entry.created_at.isoformat())),
            source=_source(entry),
        )
    return None


def _model_use(entry: AuditEntry) -> ModelUse | None:
    if entry.step not in _AGENT_STEPS:
        return None
    call = entry.payload.get("llm_call")
    if not isinstance(call, dict) or "provider" not in call:
        return None
    return ModelUse(
        agent=entry.agent,
        provider=str(call["provider"]),
        model=call.get("model"),
        requested_model=call.get("requested_model"),
        latency_ms=call.get("latency_ms"),
        source=_source(entry),
    )


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _terminal_entry(by_step: dict[str, AuditEntry]) -> AuditEntry | None:
    for step in _TERMINAL_STATUS:
        if step in by_step:
            return by_step[step]
    return None


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
