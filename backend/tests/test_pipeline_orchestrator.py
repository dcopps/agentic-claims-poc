"""
Tests for `backend.app.orchestrator.pipeline.PipelineOrchestrator`.

The four agents are stubbed — these tests exercise the orchestrator's wiring,
not the agents (which have their own suites). The database is real (`clean_db`)
so the orchestrator's pipeline-level audit writes actually persist and can be
asserted; an inserted claim row satisfies the audit FK.

Coverage: happy path (settle), threshold escalation, guardrail-returns-fail,
each abort case (doc-parser / validator / adjuster throw), guardrail-throw
fail-closed, injected correlation id, the emit event sequence, and the
orchestrator's audit entries.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from backend.app.agents.adjuster_models import AdjusterOutput, AdjusterResult
from backend.app.agents.doc_parser_models import DocParserOutput, DocParserResult
from backend.app.agents.guardrail_models import (
    GuardrailFlag,
    GuardrailOutput,
    GuardrailResult,
)
from backend.app.agents.validator_models import (
    CitedChunk,
    RetrievedChunk,
    ValidatorResult,
    ValidatorVerdict,
)
from backend.app.escalation.policy import EscalationPolicy
from backend.app.llm.provider import LLMProviderError
from backend.app.orchestrator.models import PipelineEvent
from backend.app.orchestrator.pipeline import PipelineOrchestrator
from backend.data.market_data import MarketRange
from backend.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = EscalationPolicy.load_from_yaml(REPO_ROOT / "backend/app/escalation/policy.yaml")


# --------------------------------------------------------------------------- #
# Stub agents
# --------------------------------------------------------------------------- #


@dataclass
class _StubDocParser:
    output: DocParserOutput
    error: BaseException | None = None
    seen: list[UUID] = field(default_factory=list)

    def evaluate(self, claim_id: UUID, correlation_id: UUID) -> DocParserResult:
        self.seen.append(correlation_id)
        if self.error is not None:
            raise self.error
        return DocParserResult(
            claim_id=claim_id,
            correlation_id=correlation_id,
            output=self.output,
            model="stub",
            latency_ms=1,
        )


@dataclass
class _StubValidator:
    verdict: ValidatorVerdict
    chunks: list[RetrievedChunk]
    error: BaseException | None = None
    seen: list[UUID] = field(default_factory=list)

    def evaluate(self, claim_id: UUID, correlation_id: UUID) -> ValidatorResult:
        self.seen.append(correlation_id)
        if self.error is not None:
            raise self.error
        return ValidatorResult(
            claim_id=claim_id,
            correlation_id=correlation_id,
            verdict=self.verdict,
            retrieved_chunks=self.chunks,
            model="stub",
            latency_ms=1,
        )


@dataclass
class _StubAdjuster:
    output: AdjusterOutput
    error: BaseException | None = None
    seen: list[UUID] = field(default_factory=list)

    def evaluate(
        self,
        claim_id: UUID,
        correlation_id: UUID,
        *,
        parsed_claim: DocParserOutput,
        validator_verdict: ValidatorVerdict,
    ) -> AdjusterResult:
        self.seen.append(correlation_id)
        if self.error is not None:
            raise self.error
        market_range = _wide_market_range()
        return AdjusterResult(
            claim_id=claim_id,
            correlation_id=correlation_id,
            output=self.output,
            market_range=market_range,
            model="stub",
            latency_ms=1,
        )


@dataclass
class _StubGuardrail:
    output: GuardrailOutput
    error: BaseException | None = None
    seen: list[UUID] = field(default_factory=list)

    def evaluate(
        self,
        claim_id: UUID,
        correlation_id: UUID,
        *,
        adjuster_result: AdjusterResult,
        retrieved_chunks: list[RetrievedChunk],
    ) -> GuardrailResult:
        self.seen.append(correlation_id)
        if self.error is not None:
            raise self.error
        return GuardrailResult(
            claim_id=claim_id,
            correlation_id=correlation_id,
            output=self.output,
            model="stub",
            latency_ms=1,
        )


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _wide_market_range() -> MarketRange:
    # Wide enough to contain every settlement the tests use.
    return MarketRange(
        claim_type="water_damage",
        severity="moderate",
        floor=Decimal("1000"),
        ceiling=Decimal("2000000"),
    )


def _doc_output(claim_type: str = "water_damage") -> DocParserOutput:
    return DocParserOutput(
        loss_date=date(2026, 4, 18),
        jurisdiction="United Kingdom",
        claim_type=claim_type,
        claimed_amount=Decimal("85000.00"),
        claimant_identifier="Harborline Logistics Ltd",
        narrative_summary="Burst supply line flooded the warehouse mezzanine.",
    )


def _verdict(confidence: float = 0.9) -> ValidatorVerdict:
    return ValidatorVerdict(
        covered=True,
        confidence=confidence,
        reasoning="Sudden and accidental water discharge is covered.",
        policy_basis="Section 4 — Water Damage.",
        cited_chunks=[CitedChunk(chunk_id=uuid4(), section="Section 4")],
    )


def _chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=uuid4(),
            section="Section 4",
            content="Water damage that is sudden and accidental is covered.",
            similarity=0.91,
        )
    ]


def _adjuster_output(settlement: str = "85000.00", confidence: float = 0.9) -> AdjusterOutput:
    return AdjusterOutput(
        recommended_settlement=Decimal(settlement),
        confidence=confidence,
        reasoning="Settlement sits within the market range for the loss.",
    )


def _guardrail_output(passed: bool = True) -> GuardrailOutput:
    flags = (
        []
        if passed
        else [GuardrailFlag(kind="hallucinated_citation", detail="ghost endorsement", source="llm")]
    )
    return GuardrailOutput(
        passed=passed,
        flags=flags,
        summary="No issues found." if passed else "Hallucinated citation found.",
    )


@contextmanager
def _conn_factory(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Yield the test connection without closing it (clean_db owns it)."""
    yield conn


def _insert_claim(conn: psycopg.Connection) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO claims (
                claim_number, line_of_business, claimant_name, policy_number,
                loss_date, reported_date, jurisdiction, narrative, claim_type,
                reported_amount, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING claim_id
            """,
            (
                "ORCH-TEST-0001",
                "Commercial Property",
                "Harborline Logistics Ltd",
                "POL-1",
                date(2026, 4, 1),
                date(2026, 4, 3),
                "United Kingdom",
                "Burst supply line flooded the warehouse mezzanine.",
                "water_damage",
                Decimal("85000.00"),
                "received",
            ),
        )
        row = cur.fetchone()
        assert row is not None
        claim_id: UUID = row[0]
    conn.commit()
    return claim_id


def _build(
    conn: psycopg.Connection,
    db_settings: Settings,
    *,
    doc: _StubDocParser | None = None,
    validator: _StubValidator | None = None,
    adjuster: _StubAdjuster | None = None,
    guardrail: _StubGuardrail | None = None,
) -> PipelineOrchestrator:
    return PipelineOrchestrator(
        doc_parser=doc or _StubDocParser(output=_doc_output()),
        validator=validator or _StubValidator(verdict=_verdict(), chunks=_chunks()),
        adjuster=adjuster or _StubAdjuster(output=_adjuster_output()),
        guardrail=guardrail or _StubGuardrail(output=_guardrail_output()),
        policy=POLICY,
        settings=db_settings,
        connection_factory=lambda: _conn_factory(conn),
    )


def _orchestrator_steps(conn: psycopg.Connection, claim_id: UUID) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT step FROM audit_log WHERE claim_id = %s AND agent = 'orchestrator' "
            "ORDER BY audit_id",
            (claim_id,),
        )
        return [row[0] for row in cur.fetchall()]


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_clean_claim_settles(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    orch = _build(clean_db, db_settings)
    result = orch.run(claim_id)

    assert result.status == "settled"
    assert result.escalation_decision is not None
    assert result.escalation_decision.escalate is False
    assert result.doc_parser_output is not None
    assert result.guardrail_output is not None
    assert result.aborted_agent is None
    assert _orchestrator_steps(clean_db, claim_id) == [
        "pipeline_started",
        "escalation_decision",
        "pipeline_settled",
    ]


def test_correlation_id_threaded_to_every_agent(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    doc = _StubDocParser(output=_doc_output())
    validator = _StubValidator(verdict=_verdict(), chunks=_chunks())
    adjuster = _StubAdjuster(output=_adjuster_output())
    guardrail = _StubGuardrail(output=_guardrail_output())
    orch = _build(
        clean_db, db_settings, doc=doc, validator=validator, adjuster=adjuster, guardrail=guardrail
    )
    cid = uuid4()
    result = orch.run(claim_id, correlation_id=cid)

    assert result.correlation_id == cid
    # Every agent saw the same injected correlation id.
    assert doc.seen == [cid]
    assert validator.seen == [cid]
    assert adjuster.seen == [cid]
    assert guardrail.seen == [cid]


# --------------------------------------------------------------------------- #
# Escalation paths
# --------------------------------------------------------------------------- #


def test_threshold_escalation_awaits_human(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    adjuster = _StubAdjuster(output=_adjuster_output(settlement="850000.00"))
    orch = _build(clean_db, db_settings, adjuster=adjuster)
    result = orch.run(claim_id)

    assert result.status == "awaiting_human"
    assert result.escalation_decision is not None
    names = {r.name for r in result.escalation_decision.fired_rules}
    assert "settlement_over_ceiling" in names
    assert _orchestrator_steps(clean_db, claim_id)[-1] == "pipeline_awaiting_human"


def test_guardrail_fail_escalates(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    guardrail = _StubGuardrail(output=_guardrail_output(passed=False))
    orch = _build(clean_db, db_settings, guardrail=guardrail)
    result = orch.run(claim_id)

    assert result.status == "awaiting_human"
    assert result.escalation_decision is not None
    names = {r.name for r in result.escalation_decision.fired_rules}
    assert "guardrail_failed" in names


# --------------------------------------------------------------------------- #
# Abort matrix
# --------------------------------------------------------------------------- #


def _build_with_failure(
    conn: psycopg.Connection, db_settings: Settings, failing: str
) -> PipelineOrchestrator:
    """Build an orchestrator whose `failing` agent throws."""
    if failing == "doc_parser":
        return _build(
            conn, db_settings, doc=_StubDocParser(output=_doc_output(), error=ValueError("boom"))
        )
    if failing == "validator":
        broken_validator = _StubValidator(
            verdict=_verdict(), chunks=_chunks(), error=ValueError("boom")
        )
        return _build(conn, db_settings, validator=broken_validator)
    return _build(
        conn,
        db_settings,
        adjuster=_StubAdjuster(output=_adjuster_output(), error=LLMProviderError("boom")),
    )


@pytest.mark.parametrize("failing", ["doc_parser", "validator", "adjuster"])
def test_agent_throw_aborts(
    clean_db: psycopg.Connection, db_settings: Settings, failing: str
) -> None:
    claim_id = _insert_claim(clean_db)
    orch = _build_with_failure(clean_db, db_settings, failing)
    result = orch.run(claim_id)

    assert result.status == "aborted"
    assert result.aborted_agent == failing
    assert result.error_type in {"ValueError", "LLMProviderError"}
    assert result.escalation_decision is None
    assert _orchestrator_steps(clean_db, claim_id) == [
        "pipeline_started",
        "pipeline_aborted",
    ]


def test_guardrail_throw_fails_closed(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    guardrail = _StubGuardrail(output=_guardrail_output(), error=ValueError("guardrail boom"))
    orch = _build(clean_db, db_settings, guardrail=guardrail)
    result = orch.run(claim_id)

    # A Guardrail throw escalates fail-closed — never aborts, never settles.
    assert result.status == "awaiting_human"
    assert result.guardrail_output is None  # it threw before producing output
    assert result.escalation_decision is not None
    names = {r.name for r in result.escalation_decision.fired_rules}
    assert names == {"guardrail_failed"}
    assert _orchestrator_steps(clean_db, claim_id)[-1] == "pipeline_awaiting_human"


# --------------------------------------------------------------------------- #
# Emit sequence
# --------------------------------------------------------------------------- #


def test_emit_event_sequence(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    orch = _build(clean_db, db_settings)
    events: list[PipelineEvent] = []
    orch.run(claim_id, emit=events.append)

    assert [e.event_type for e in events] == [
        "pipeline_started",
        "agent_started",
        "agent_completed",
        "agent_started",
        "agent_completed",
        "agent_started",
        "agent_completed",
        "agent_started",
        "agent_completed",
        "escalation_decision",
        "pipeline_completed",
    ]


def test_emit_sequence_on_abort(
    clean_db: psycopg.Connection, db_settings: Settings
) -> None:
    claim_id = _insert_claim(clean_db)
    doc = _StubDocParser(output=_doc_output(), error=ValueError("boom"))
    orch = _build(clean_db, db_settings, doc=doc)
    events: list[PipelineEvent] = []
    orch.run(claim_id, emit=events.append)

    # Started, the doc-parser started, then the abort — no further agents.
    assert [e.event_type for e in events] == [
        "pipeline_started",
        "agent_started",
        "pipeline_aborted",
    ]
