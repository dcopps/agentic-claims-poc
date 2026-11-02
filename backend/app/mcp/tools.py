"""
The nine tools.

Each is a thin wrapper: validate the arguments (the schema does most of it),
call the same repository function the matching API route calls, shape the
result, and let `run_logged` record the call. Eight are read-only. The ninth,
`run_scenario`, is the one action, and it can only submit one of the three
scripted claims — or re-run one that already exists and carries that
scenario's tag.

Every tool reads its collaborators from `app.state` at call time rather than
at registration, so a test can inject a stub orchestrator factory or a
different recorder exactly as the API tests do.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar
from uuid import UUID, uuid4

import fastapi
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.concurrency import run_in_threadpool

from backend.app.api.agents_test import AgentPromptView, load_agent_prompts
from backend.app.api.claims import DEFAULT_LIST_LIMIT
from backend.app.api.pipeline import OrchestratorFactory, execute_run, make_orchestrator_factory
from backend.app.audit import AuditRepository, verify_chain
from backend.app.claims import ClaimRecord, ClaimsRepository, ClaimStatus
from backend.app.mcp.explain import agent_rows, chain_report, compose_explanation, strip_prompts
from backend.app.mcp.instrument import ToolCall, not_found, run_logged
from backend.app.mcp.models import (
    AuditTrail,
    ChainVerificationReport,
    ClaimListing,
    ClaimListItem,
    ClaimView,
    DecisionExplanation,
    RunView,
    ScenarioName,
    ScenarioRun,
    TargetRef,
)
from backend.app.mcp.scenarios import scenario_tag_for, submission_for
from backend.app.mcp.tool_log import ToolCallRecorder
from backend.app.orchestrator import PipelineEventBus, PipelineResult
from backend.app.runs import (
    RunClaimMismatchError,
    RunComparison,
    RunNotFoundError,
    RunsRepository,
)
from backend.db.connection import open_connection
from backend.settings import AgentRole, Settings

T = TypeVar("T")

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_ACTION = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)

# The pipeline variant a scenario runs under. The action tool never exposes
# the variant registry; replays with other variants stay a web-interface act.
_SCENARIO_VARIANT = "default"


class _Deps:
    """Collaborators resolved from `app.state` at call time."""

    def __init__(self, app: fastapi.FastAPI) -> None:
        self._app = app

    @property
    def settings(self) -> Settings:
        settings: Settings = self._app.state.settings
        return settings

    @property
    def recorder(self) -> ToolCallRecorder:
        recorder: ToolCallRecorder = self._app.state.mcp_recorder
        return recorder

    @property
    def event_bus(self) -> PipelineEventBus:
        bus: PipelineEventBus = self._app.state.event_bus
        return bus

    def factory(self) -> OrchestratorFactory:
        return make_orchestrator_factory(self._app)

    async def logged(self, call: ToolCall, body: Callable[[], Awaitable[T]]) -> T:
        return await run_logged(self.recorder, self.settings.mcp.token_label, call, body)


def register_tools(server: MCPServer, app: fastapi.FastAPI) -> None:
    """Attach the nine tools to `server`, bound to `app`'s state."""
    deps = _Deps(app)
    # Registration order is catalogue order (`TOOL_NAMES`).
    _register_claim_tools(server, deps)
    _register_run_tools(server, deps)
    _register_audit_tools(server, deps)
    _register_comparison_and_instruction_tools(server, deps)
    _register_action_tool(server, deps)


# --------------------------------------------------------------------------- #
# Read tools
# --------------------------------------------------------------------------- #


def _register_claim_tools(server: MCPServer, deps: _Deps) -> None:
    @server.tool(title="List claims", annotations=_READ)
    async def list_claims(status: ClaimStatus | None = None) -> ClaimListing:
        """List the claims on record, newest first, with how many runs each has had.
        Optionally filter by status (received, settled, awaiting_human, aborted, ...)."""
        call = ToolCall("list_claims", {"status": status})
        return await deps.logged(
            call, lambda: run_in_threadpool(_read_claims, deps.settings, status)
        )

    @server.tool(title="Get a claim", annotations=_READ)
    async def get_claim(claim_id: UUID) -> ClaimView:
        """The claim record and a summary of every pipeline run made on it, newest first."""
        call = ToolCall(
            "get_claim", {"claim_id": str(claim_id)}, TargetRef(kind="claim", id=claim_id)
        )

        async def body() -> ClaimView:
            view = await run_in_threadpool(_read_claim, deps.settings, claim_id)
            if view is None:
                raise not_found("claim", claim_id)
            return view

        return await deps.logged(call, body)


def _register_run_tools(server: MCPServer, deps: _Deps) -> None:
    @server.tool(title="Get a run", annotations=_READ)
    async def get_run(correlation_id: UUID) -> RunView:
        """A completed run: its outcome, the rules that fired, each agent's recorded
        output, and the model latency each agent's audit row records."""
        call = ToolCall(
            "get_run", {"correlation_id": str(correlation_id)}, _run_target(correlation_id)
        )

        async def body() -> RunView:
            view = await run_in_threadpool(_read_run, deps.settings, correlation_id)
            if view is None:
                raise not_found("run", correlation_id)
            return view

        return await deps.logged(call, body)

    @server.tool(title="Explain a decision", annotations=_READ)
    async def explain_decision(correlation_id: UUID) -> DecisionExplanation:
        """Why a run settled or escalated, composed from its audit rows only: the Validator's
        verdict and the passages it saw, the Adjuster's figure and range, the Guardrail's
        findings including model claims that code refused and why, the escalation rules that
        fired, and the chain check. Every section names the audit row it came from."""
        call = ToolCall(
            "explain_decision", {"correlation_id": str(correlation_id)}, _run_target(correlation_id)
        )

        async def body() -> DecisionExplanation:
            explanation = await run_in_threadpool(_read_explanation, deps.settings, correlation_id)
            if explanation is None:
                raise not_found("run", correlation_id)
            return explanation

        return await deps.logged(call, body)


def _register_audit_tools(server: MCPServer, deps: _Deps) -> None:
    @server.tool(title="Get the audit trail", annotations=_READ)
    async def get_audit_trail(correlation_id: UUID, include_prompts: bool = False) -> AuditTrail:
        """A run's audit rows in chain order. With include_prompts, each agent row keeps the
        exact system and user text it sent to the model; without, that text is removed and
        the payload shown will no longer re-hash to its row hash."""
        call = ToolCall(
            "get_audit_trail",
            {"correlation_id": str(correlation_id), "include_prompts": include_prompts},
            _run_target(correlation_id),
        )

        async def body() -> AuditTrail:
            trail = await run_in_threadpool(
                _read_trail, deps.settings, correlation_id, include_prompts
            )
            if trail is None:
                raise not_found("run", correlation_id)
            return trail

        return await deps.logged(call, body)

    # Named explicitly: the function cannot be called `verify_chain` without
    # shadowing the verifier it wraps.
    @server.tool(name="verify_chain", title="Verify the audit chain", annotations=_READ)
    async def verify_chain_tool(correlation_id: UUID) -> ChainVerificationReport:
        """Check the audit ledger's hash chain. The chain links every row in the ledger, so the
        check is whole-ledger; the result says how many rows were checked and how many belong
        to the run named."""
        call = ToolCall(
            "verify_chain", {"correlation_id": str(correlation_id)}, _run_target(correlation_id)
        )

        async def body() -> ChainVerificationReport:
            report = await run_in_threadpool(_read_chain, deps.settings, correlation_id)
            if report is None:
                raise not_found("run", correlation_id)
            return report

        return await deps.logged(call, body)


def _register_comparison_and_instruction_tools(server: MCPServer, deps: _Deps) -> None:
    @server.tool(title="Compare two runs", annotations=_READ)
    async def compare_runs(correlation_id_a: UUID, correlation_id_b: UUID) -> RunComparison:
        """Two completed runs of the same claim side by side, with the fields that differ:
        settlement, escalation, fired rules, guardrail result."""
        call = ToolCall(
            "compare_runs",
            {"correlation_id_a": str(correlation_id_a), "correlation_id_b": str(correlation_id_b)},
            _run_target(correlation_id_a),
        )
        return await deps.logged(
            call,
            lambda: run_in_threadpool(
                _read_comparison, deps.settings, correlation_id_a, correlation_id_b
            ),
        )

    @server.tool(title="Get an agent's instructions", annotations=_READ)
    async def get_agent_instructions(agent: AgentRole) -> AgentPromptView:
        """The system prompt and user-message template an agent currently runs under
        (doc_parser, validator, adjuster or guardrail), as the files on disk read."""
        call = ToolCall("get_agent_instructions", {"agent": agent})

        async def body() -> AgentPromptView:
            registry = deps._app.state.variant_registry
            return load_agent_prompts(agent, _SCENARIO_VARIANT, registry)

        return await deps.logged(call, body)


# --------------------------------------------------------------------------- #
# The action tool
# --------------------------------------------------------------------------- #


def _register_action_tool(server: MCPServer, deps: _Deps) -> None:
    @server.tool(title="Run a scripted scenario", annotations=_ACTION)
    async def run_scenario(name: ScenarioName, claim_id: UUID | None = None) -> ScenarioRun:
        """Submit one of the three scripted claims (harborline: should settle; northwood:
        should escalate over the settlement ceiling; coral_bay: should escalate on the
        Guardrail) and run the pipeline on it, returning the outcome and the run's
        correlation id. Pass claim_id to re-run an existing claim that carries that
        scenario's tag instead of submitting a new one. The only tool that changes anything."""
        call = ToolCall("run_scenario", {"name": name, "claim_id": _optional_id(claim_id)})

        async def body() -> ScenarioRun:
            claim = await run_in_threadpool(_prepare_scenario_claim, deps.settings, name, claim_id)
            correlation_id = uuid4()
            call.target = _run_target(correlation_id)
            result = await execute_run(
                deps.factory()(_SCENARIO_VARIANT),
                claim.claim_id,
                correlation_id,
                _SCENARIO_VARIANT,
                deps.event_bus,
            )
            return _scenario_run(name, result)

        return await deps.logged(call, body)


def _prepare_scenario_claim(settings: Settings, name: str, claim_id: UUID | None) -> ClaimRecord:
    """Insert the scripted claim, or validate the existing one the caller named."""
    tag = scenario_tag_for(name)  # refuses any name outside the three
    with open_connection(settings) as conn:
        if claim_id is None:
            return ClaimsRepository.insert(conn, submission_for(name))
        existing = ClaimsRepository.get(conn, claim_id)
        if existing is None:
            raise not_found("claim", claim_id)
        # The action is limited to the scripted scenarios: an arbitrary claim,
        # even an existing one, is not a scenario and may not be run from here.
        if existing.scenario_tag != tag:
            raise ToolError(
                f"not_a_scripted_claim: claim {claim_id} carries scenario_tag "
                f"{existing.scenario_tag!r}, not {tag!r}"
            )
        if RunsRepository.is_run_active(conn, claim_id):
            raise ToolError(f"run_in_flight: claim {claim_id} already has a run in progress")
        return existing


def _scenario_run(name: str, result: PipelineResult) -> ScenarioRun:
    decision = result.escalation_decision
    adjuster = result.adjuster_output
    return ScenarioRun(
        scenario=name,  # type: ignore[arg-type]  # validated by scenario_tag_for
        claim_id=result.claim_id,
        correlation_id=result.correlation_id,
        status=result.status,
        fired_rule_names=[rule.name for rule in decision.fired_rules] if decision else [],
        settlement=str(adjuster.recommended_settlement) if adjuster is not None else None,
    )


# --------------------------------------------------------------------------- #
# Blocking reads — each opens a short-lived connection, as the routers do.
# --------------------------------------------------------------------------- #


def _read_claims(settings: Settings, status: ClaimStatus | None) -> ClaimListing:
    with open_connection(settings) as conn:
        records = ClaimsRepository.list_claims(conn, limit=DEFAULT_LIST_LIMIT, status=status)
        counts = RunsRepository.count_runs_by_claim(conn, [record.claim_id for record in records])
    return ClaimListing(
        claims=[
            ClaimListItem(
                claim_id=record.claim_id,
                claim_number=record.claim_number,
                claimant_name=record.claimant_name,
                claim_type=record.claim_type,
                reported_amount=record.reported_amount,
                status=record.status,
                scenario_tag=record.scenario_tag,
                run_count=counts.get(record.claim_id, 0),
            )
            for record in records
        ]
    )


def _read_claim(settings: Settings, claim_id: UUID) -> ClaimView | None:
    with open_connection(settings) as conn:
        record = ClaimsRepository.get(conn, claim_id)
        if record is None:
            return None
        runs = RunsRepository.list_runs_for_claim(conn, claim_id)
    return ClaimView(claim=record, runs=runs)


def _read_run(settings: Settings, correlation_id: UUID) -> RunView | None:
    with open_connection(settings) as conn:
        result = RunsRepository.get_run(conn, correlation_id)
        if result is None:
            return None
        entries = AuditRepository.list_entries(conn, correlation_id)
    return RunView(result=result, agents=agent_rows(entries))


def _read_explanation(settings: Settings, correlation_id: UUID) -> DecisionExplanation | None:
    with open_connection(settings) as conn:
        entries = AuditRepository.list_entries(conn, correlation_id)
        if not entries:
            return None
        claim = ClaimsRepository.get(conn, _claim_id_of(entries[0].payload, correlation_id))
        if claim is None:
            return None
        verification = verify_chain(conn)
    return compose_explanation(correlation_id, claim, entries, verification)


def _read_trail(
    settings: Settings, correlation_id: UUID, include_prompts: bool
) -> AuditTrail | None:
    with open_connection(settings) as conn:
        entries = AuditRepository.list_entries(conn, correlation_id)
    if not entries:
        return None
    if not include_prompts:
        entries = [
            entry.model_copy(update={"payload": strip_prompts(entry.payload)}) for entry in entries
        ]
    return AuditTrail(
        correlation_id=correlation_id, prompts_included=include_prompts, entries=entries
    )


def _read_chain(settings: Settings, correlation_id: UUID) -> ChainVerificationReport | None:
    with open_connection(settings) as conn:
        entries = AuditRepository.list_entries(conn, correlation_id)
        if not entries:
            return None
        verification = verify_chain(conn)
    return chain_report(verification, run_rows=len(entries))


def _read_comparison(settings: Settings, cid_a: UUID, cid_b: UUID) -> RunComparison:
    with open_connection(settings) as conn:
        try:
            return RunsRepository.compare(conn, cid_a, cid_b)
        except RunNotFoundError as exc:
            raise ToolError(f"not_found: {exc}") from exc
        except RunClaimMismatchError as exc:
            raise ToolError(f"claim_mismatch: {exc}") from exc


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _run_target(correlation_id: UUID) -> TargetRef:
    return TargetRef(kind="run", id=correlation_id)


def _optional_id(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _claim_id_of(payload: dict[str, Any], correlation_id: UUID) -> UUID:
    """The claim a run's first row names; every orchestrator row carries it."""
    raw = payload.get("claim_id")
    if raw is None:
        raise ValueError(
            f"explain_decision: the first audit row of run {correlation_id} names no claim_id"
        )
    return UUID(str(raw))


# Exposed for the catalogue endpoint's tests: the tool names in registration order.
TOOL_NAMES: tuple[str, ...] = (
    "list_claims",
    "get_claim",
    "get_run",
    "explain_decision",
    "get_audit_trail",
    "verify_chain",
    "compare_runs",
    "get_agent_instructions",
    "run_scenario",
)

ReadOrAction = Literal["read", "action"]
