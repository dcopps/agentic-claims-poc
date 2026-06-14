"""
RunsRepository — reconstructs past runs from the audit_log.

Every method is a **pure read**: the runs repository writes nothing. A run is
identified by its correlation_id, and the audit_log under that id holds enough to
rebuild the `PipelineResult` it produced — the agent-step entries carry each
agent's full output, the orchestrator entries carry the variant, the escalation
decision, and the terminal outcome. That is what makes replay non-destructive: a
re-run is just a new chain of entries under a new correlation_id, and any past run
re-projects from its own chain.

`get_run` requires a terminal entry — an in-flight run (started, no terminal) is
not a completed result and returns None. `list_runs_for_claim` tolerates in-flight
runs (status `running`, `completed_at=None`).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from backend.app.agents.adjuster_models import AdjusterOutput
from backend.app.agents.doc_parser_models import DocParserOutput
from backend.app.agents.guardrail_models import GuardrailFlag, GuardrailOutput
from backend.app.agents.validator_models import ValidatorVerdict
from backend.app.escalation.models import EscalationDecision, FiredRule
from backend.app.orchestrator.models import PipelineResult, PipelineStatus
from backend.app.runs.models import DiffSummary, RunComparison, RunStatus, RunSummary

# Terminal audit step -> the run status it implies. The three are mutually
# exclusive; exactly one appears in a completed run's chain.
_TERMINAL_STEPS: dict[str, PipelineStatus] = {
    "pipeline_settled": "settled",
    "pipeline_awaiting_human": "awaiting_human",
    "pipeline_aborted": "aborted",
}


class RunNotFoundError(ValueError):
    """A requested run has no reconstructable entries. The API maps this to 404."""


class RunClaimMismatchError(ValueError):
    """Two runs being compared target different claims. The API maps this to 400."""


class RunsRepository:
    """Pure-read reconstruction of runs from the audit_log."""

    @staticmethod
    def get_run(
        conn: psycopg.Connection, correlation_id: UUID
    ) -> PipelineResult | None:
        """Rebuild the `PipelineResult` for a completed run, or None."""
        rows = _fetch_run_rows(conn, correlation_id)
        if not rows:
            return None
        claim_id = rows[0][2]
        by_step: dict[str, Any] = {step: payload for step, payload, _claim in rows}
        terminal = _reconstruct_terminal(by_step)
        if terminal is None:
            return None  # in-flight: not a completed run
        status, aborted_agent, error_type, completed_at = terminal
        return PipelineResult(
            status=status,
            claim_id=claim_id,
            correlation_id=correlation_id,
            escalation_decision=_reconstruct_escalation(by_step),
            doc_parser_output=_doc_from(by_step.get("doc_extract")),
            validator_output=_validator_from(by_step.get("coverage_check")),
            adjuster_output=_adjuster_from(by_step.get("settlement_estimate")),
            guardrail_output=_guardrail_from(by_step.get("output_check")),
            aborted_agent=aborted_agent,
            error_type=error_type,
            completed_at=completed_at,
        )

    @staticmethod
    def list_runs_for_claim(
        conn: psycopg.Connection, claim_id: UUID
    ) -> list[RunSummary]:
        """Summarise every run that targeted the claim, most-recent-first."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT correlation_id, step, payload, created_at FROM audit_log "
                "WHERE claim_id = %s ORDER BY audit_id",
                (claim_id,),
            )
            rows = cur.fetchall()
        groups: dict[UUID, dict[str, Any]] = {}
        first_seen: dict[UUID, datetime] = {}
        for cid, step, payload, created in rows:
            groups.setdefault(cid, {})[step] = payload
            first_seen.setdefault(cid, created)
        summaries = [_summarise(cid, groups[cid], first_seen[cid]) for cid in groups]
        summaries.sort(key=lambda summary: summary.started_at, reverse=True)
        return summaries

    @staticmethod
    def is_run_active(conn: psycopg.Connection, claim_id: UUID) -> bool:
        """True if any run on the claim has started but not reached a terminal."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT correlation_id, step FROM audit_log "
                "WHERE claim_id = %s AND step IN "
                "('pipeline_started', 'pipeline_settled', "
                "'pipeline_awaiting_human', 'pipeline_aborted')",
                (claim_id,),
            )
            rows = cur.fetchall()
        started = {cid for cid, step in rows if step == "pipeline_started"}
        terminal = {cid for cid, step in rows if step != "pipeline_started"}
        return bool(started - terminal)

    @staticmethod
    def compare(
        conn: psycopg.Connection, cid_a: UUID, cid_b: UUID
    ) -> RunComparison:
        """Reconstruct both runs and diff them. Raises on missing or mismatched."""
        run_a = RunsRepository.get_run(conn, cid_a)
        run_b = RunsRepository.get_run(conn, cid_b)
        if run_a is None:
            raise RunNotFoundError(f"RunsRepository.compare: run not found: {cid_a}")
        if run_b is None:
            raise RunNotFoundError(f"RunsRepository.compare: run not found: {cid_b}")
        if run_a.claim_id != run_b.claim_id:
            raise RunClaimMismatchError(
                "RunsRepository.compare: runs target different claims; "
                f"{run_a.claim_id} vs {run_b.claim_id}"
            )
        return RunComparison(run_a=run_a, run_b=run_b, diff=compute_diff(run_a, run_b))


# --------------------------------------------------------------------------- #
# Fetch + reconstruction helpers
# --------------------------------------------------------------------------- #


def _fetch_run_rows(
    conn: psycopg.Connection, correlation_id: UUID
) -> list[tuple[str, Any, UUID]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT step, payload, claim_id FROM audit_log "
            "WHERE correlation_id = %s ORDER BY audit_id",
            (correlation_id,),
        )
        return cur.fetchall()


def _reconstruct_terminal(
    by_step: dict[str, Any],
) -> tuple[PipelineStatus, Any, Any, datetime] | None:
    """Return (status, aborted_agent, error_type, completed_at) or None if in-flight."""
    for step, status in _TERMINAL_STEPS.items():
        payload = by_step.get(step)
        if payload is not None:
            completed_at = datetime.fromisoformat(payload["completed_at"])
            return (
                status,
                payload.get("failing_agent"),
                payload.get("error_type"),
                completed_at,
            )
    return None


def _reconstruct_escalation(by_step: dict[str, Any]) -> EscalationDecision | None:
    """Rebuild the escalation decision from its entry, or synthesise for a throw."""
    entry = by_step.get("escalation_decision")
    if entry is not None:
        return EscalationDecision(
            escalate=entry["escalate"],
            fired_rules=[FiredRule.model_validate(rule) for rule in entry["fired_rules"]],
            reasoning=entry["reasoning"],
        )
    # A Guardrail throw escalates without a policy evaluation, so no
    # escalation_decision entry exists — synthesise from the terminal entry.
    terminal = by_step.get("pipeline_awaiting_human")
    if terminal is not None and terminal.get("reason") == "guardrail_threw":
        names = terminal.get("fired_rule_names", [])
        return EscalationDecision(
            escalate=True,
            fired_rules=[
                FiredRule(name=name, rule_type="hard", description=f"{name} (reconstructed)")
                for name in names
            ],
            reasoning="Guardrail evaluation failed; escalated fail-closed (reconstructed).",
        )
    return None


def _doc_from(payload: Any) -> DocParserOutput | None:
    output = _output_block(payload)
    return DocParserOutput.model_validate(output) if output is not None else None


def _validator_from(payload: Any) -> ValidatorVerdict | None:
    if payload is None:
        return None
    verdict = payload.get("verdict")
    return ValidatorVerdict.model_validate(verdict) if verdict is not None else None


def _adjuster_from(payload: Any) -> AdjusterOutput | None:
    output = _output_block(payload)
    if output is None:
        return None
    # Prefer the full reasoning (Phase 5); fall back to the excerpt for a
    # pre-Phase-5 entry that predates the full field.
    reasoning = output.get("reasoning") or output.get("reasoning_excerpt")
    return AdjusterOutput(
        recommended_settlement=Decimal(output["recommended_settlement"]),
        confidence=output["confidence"],
        reasoning=reasoning,
    )


def _guardrail_from(payload: Any) -> GuardrailOutput | None:
    output = _output_block(payload)
    if output is None:
        return None
    flags = [GuardrailFlag.model_validate(flag) for flag in output["flags"]]
    # `flag_count` in the audit payload is a denormalised convenience; rebuild
    # from the fields the model actually carries.
    return GuardrailOutput(
        passed=output["passed"], flags=flags, summary=output["summary"]
    )


def _output_block(payload: Any) -> Any:
    """Return the agent payload's `output` block, or None if absent/errored."""
    if payload is None:
        return None
    return payload.get("output")


# --------------------------------------------------------------------------- #
# Summary + diff helpers
# --------------------------------------------------------------------------- #


def _summarise(
    correlation_id: UUID, steps: dict[str, Any], first_seen: datetime
) -> RunSummary:
    started = steps.get("pipeline_started", {})
    started_at = (
        datetime.fromisoformat(started["started_at"])
        if "started_at" in started
        else first_seen
    )
    status, completed_at = _summary_status(steps)
    return RunSummary(
        correlation_id=correlation_id,
        variant=started.get("variant", "default"),
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        escalate=_summary_escalate(steps),
    )


def _summary_status(steps: dict[str, Any]) -> tuple[RunStatus, datetime | None]:
    for step, status in _TERMINAL_STEPS.items():
        payload = steps.get(step)
        if payload is not None:
            return status, datetime.fromisoformat(payload["completed_at"])
    return "running", None


def _summary_escalate(steps: dict[str, Any]) -> bool | None:
    entry = steps.get("escalation_decision")
    if entry is not None:
        escalate: bool = entry["escalate"]
        return escalate
    for step in ("pipeline_settled", "pipeline_awaiting_human"):
        payload = steps.get(step)
        if payload is not None and "escalate" in payload:
            value: bool = payload["escalate"]
            return value
    return None


def compute_diff(run_a: PipelineResult, run_b: PipelineResult) -> DiffSummary:
    """Diff two reconstructed runs on the fields the comparison surfaces."""
    settlement_a, settlement_b = _settlement(run_a), _settlement(run_b)
    escalate_a, escalate_b = _escalate(run_a), _escalate(run_b)
    fired_a, fired_b = _fired_names(run_a), _fired_names(run_b)
    guard_a, guard_b = _guardrail_passed(run_a), _guardrail_passed(run_b)
    return DiffSummary(
        settlement_changed=settlement_a != settlement_b,
        settlement_a=settlement_a,
        settlement_b=settlement_b,
        escalation_changed=escalate_a != escalate_b,
        escalate_a=escalate_a,
        escalate_b=escalate_b,
        fired_rules_added=sorted(fired_b - fired_a),
        fired_rules_removed=sorted(fired_a - fired_b),
        guardrail_changed=guard_a != guard_b,
        guardrail_passed_a=guard_a,
        guardrail_passed_b=guard_b,
    )


def _settlement(run: PipelineResult) -> str | None:
    output = run.adjuster_output
    return str(output.recommended_settlement) if output is not None else None


def _escalate(run: PipelineResult) -> bool | None:
    decision = run.escalation_decision
    return decision.escalate if decision is not None else None


def _fired_names(run: PipelineResult) -> set[str]:
    decision = run.escalation_decision
    return {rule.name for rule in decision.fired_rules} if decision is not None else set()


def _guardrail_passed(run: PipelineResult) -> bool | None:
    output = run.guardrail_output
    return output.passed if output is not None else None
