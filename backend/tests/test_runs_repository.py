"""
Tests for `RunsRepository` — reconstruction of past runs from the audit_log.

Reconstruction reads the *agent-step* audit entries, so these tests drive **real**
agents (with mock providers, a real `clean_db`, and a seeded chunk) — the same
posture as the scenario tests — rather than stubs, which skip the agent audit
writes. Each test runs one or more pipelines, then reconstructs from the audit
trail and asserts the round-trip.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import numpy as np
import psycopg
import pytest

from backend.app.audit import AuditEvent, AuditWriter
from backend.app.orchestrator.models import PipelineResult
from backend.app.prompts import PromptLoader
from backend.app.runs.repository import (
    RunClaimMismatchError,
    RunNotFoundError,
    RunsRepository,
)
from backend.settings import Settings

from .test_pipeline_scenarios import (
    _adjuster_json,
    _build_orchestrator,
    _doc_summary,
    _guardrail_json,
    _insert_chunk,
    _validator_json,
)

_REASONING = "Settlement sits within the market range for the loss."


def _insert_claim(
    conn: psycopg.Connection,
    *,
    claim_type: str = "water_damage",
    amount: Decimal = Decimal("85000.00"),
) -> UUID:
    """Insert a claim with a unique claim_number (tests here insert several).

    Phase 8.2: Doc-Parser sources its structured fields from this row, so the
    inserted `claim_type`/`amount` are what the pipeline actually sees — the
    market-range lookup and escalation read them, not a DocParser mock.
    """
    number = f"RUN-{uuid4().hex[:8].upper()}"
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
                number,
                "Commercial Property",
                "Harborline Logistics Ltd",
                "POL-1",
                date(2026, 4, 1),
                date(2026, 4, 3),
                "United Kingdom",
                "Burst supply line flooded the warehouse mezzanine.",
                claim_type,
                amount,
                "received",
            ),
        )
        row = cur.fetchone()
        assert row is not None
        claim_id: UUID = row[0]
    conn.commit()
    return claim_id


def _run(
    conn: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
    chunk_id: UUID,
    section: str,
    *,
    claim_id: UUID | None = None,
    claim_type: str = "water_damage",
    amount: str = "85000.00",
    settlement: str = "85000.00",
    confidence: float = 0.9,
    variant: str = "default",
    doc_text: str | None = None,
) -> tuple[UUID, PipelineResult]:
    # A fresh claim carries the requested type/amount so the record — now the
    # Doc-Parser's source of truth — drives the market lookup and escalation.
    if claim_id is None:
        claim_id = _insert_claim(conn, claim_type=claim_type, amount=Decimal(amount))
    orch = _build_orchestrator(
        conn,
        db_settings,
        prompt_loader,
        stub_embedder,
        doc_text=doc_text if doc_text is not None else _doc_summary(),
        validator_text=_validator_json(chunk_id, section, 0.9),
        adjuster_text=_adjuster_json(settlement, confidence, _REASONING),
        guardrail_text=_guardrail_json([]),
    )
    result = orch.run(claim_id, variant=variant)
    return claim_id, result


def _chunk(
    conn: psycopg.Connection,
    db_settings: Settings,
    stub_embedder: Callable[[str], np.ndarray],
) -> tuple[UUID, str]:
    return _insert_chunk(
        conn, stub_embedder, str(db_settings.retrieval.policy_source_path)
    )


# --------------------------------------------------------------------------- #
# get_run reconstruction
# --------------------------------------------------------------------------- #


def test_reconstruct_happy_run(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    _claim, result = _run(clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section)
    rebuilt = RunsRepository.get_run(clean_db, result.correlation_id)
    assert rebuilt is not None
    assert rebuilt.status == "settled"
    assert rebuilt.claim_id == result.claim_id
    assert rebuilt.doc_parser_output is not None
    assert rebuilt.validator_output is not None
    assert rebuilt.adjuster_output is not None
    assert rebuilt.guardrail_output is not None
    assert rebuilt.escalation_decision is not None
    assert rebuilt.escalation_decision.escalate is False


def test_reconstruct_full_adjuster_reasoning(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    # Amendment 1: the audit carries full reasoning → reconstruction is verbatim.
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    _claim, result = _run(clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section)
    rebuilt = RunsRepository.get_run(clean_db, result.correlation_id)
    assert rebuilt is not None and rebuilt.adjuster_output is not None
    assert rebuilt.adjuster_output.reasoning == _REASONING


def test_reconstruct_aborted_run(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    # An empty/whitespace summary → DocParser's summary guard raises → abort.
    # (Post-refactor the model returns prose, not JSON, so a malformed-JSON
    # string would be a *valid* summary; only an empty one aborts the agent.)
    _claim, result = _run(
        clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section,
        doc_text="   ",
    )
    rebuilt = RunsRepository.get_run(clean_db, result.correlation_id)
    assert rebuilt is not None
    assert rebuilt.status == "aborted"
    assert rebuilt.aborted_agent == "doc_parser"
    assert rebuilt.doc_parser_output is None
    assert rebuilt.escalation_decision is None


def test_reconstruct_threshold_escalation(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    _claim, result = _run(
        clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section,
        claim_type="fire", amount="850000.00", settlement="850000.00",
    )
    rebuilt = RunsRepository.get_run(clean_db, result.correlation_id)
    assert rebuilt is not None
    assert rebuilt.status == "awaiting_human"
    assert rebuilt.escalation_decision is not None
    names = {r.name for r in rebuilt.escalation_decision.fired_rules}
    assert "settlement_over_ceiling" in names


def test_get_run_missing_returns_none(clean_db: psycopg.Connection) -> None:
    assert RunsRepository.get_run(clean_db, uuid4()) is None


# --------------------------------------------------------------------------- #
# list + active
# --------------------------------------------------------------------------- #


def test_list_runs_orders_and_records_variant(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    claim_id, _first = _run(
        clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section,
        variant="default",
    )
    _claim, _second = _run(
        clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section,
        claim_id=claim_id, variant="v2_strict_validator",
    )
    summaries = RunsRepository.list_runs_for_claim(clean_db, claim_id)
    assert len(summaries) == 2
    assert summaries[0].variant == "v2_strict_validator"  # most-recent-first
    assert summaries[1].variant == "default"
    assert all(s.status == "settled" for s in summaries)


def test_is_run_active_false_after_completion(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    claim_id, _result = _run(clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section)
    assert RunsRepository.is_run_active(clean_db, claim_id) is False


def test_is_run_active_true_for_started_without_terminal(
    clean_db: psycopg.Connection,
) -> None:
    claim_id = _insert_claim(clean_db)
    AuditWriter(clean_db).append(
        AuditEvent(
            correlation_id=uuid4(),
            claim_id=claim_id,
            agent="orchestrator",
            step="pipeline_started",
            payload={"claim_id": str(claim_id), "variant": "default"},
            created_at=datetime.now(UTC),
        )
    )
    assert RunsRepository.is_run_active(clean_db, claim_id) is True


# --------------------------------------------------------------------------- #
# compare
# --------------------------------------------------------------------------- #


def test_compare_same_claim_reveals_diff(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    # Same claim (water_damage / $85k → moderate band [50k, 200k]), two runs.
    # Run A settles; run B returns a different in-band settlement with a low
    # adjuster confidence, tripping the adjuster-confidence floor. The structured
    # fields are now record-sourced, so the variant difference is expressed
    # through the Adjuster's confidence and in-range value, not a settlement jump
    # the record's band could never permit.
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    claim_id, run_a = _run(clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section)
    _claim, run_b = _run(
        clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section,
        claim_id=claim_id, settlement="120000.00", confidence=0.6,
    )
    comparison = RunsRepository.compare(
        clean_db, run_a.correlation_id, run_b.correlation_id
    )
    assert comparison.diff.settlement_changed is True
    assert comparison.diff.settlement_a == "85000.00"
    assert comparison.diff.settlement_b == "120000.00"
    assert comparison.diff.escalation_changed is True
    assert "adjuster_confidence_floor" in comparison.diff.fired_rules_added


def test_compare_different_claims_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    _a, run_a = _run(clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section)
    _b, run_b = _run(clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section)
    with pytest.raises(RunClaimMismatchError) as exc:
        RunsRepository.compare(clean_db, run_a.correlation_id, run_b.correlation_id)
    assert "different claims" in str(exc.value)


def test_compare_missing_run_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    chunk_id, section = _chunk(clean_db, db_settings, stub_embedder)
    _a, run_a = _run(clean_db, db_settings, prompt_loader, stub_embedder, chunk_id, section)
    with pytest.raises(RunNotFoundError) as exc:
        RunsRepository.compare(clean_db, run_a.correlation_id, uuid4())
    assert "run not found" in str(exc.value)
