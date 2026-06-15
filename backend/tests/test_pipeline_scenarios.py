"""
End-to-end integration tests for the three locked demo scenarios.

Posture matches Phases 2 and 3: the agents are *real* (DocParser, Validator,
Adjuster, Guardrail), the database is real (`clean_db`, with a seeded claim and
one policy chunk), and only the LLM layer is mocked — one `MockProvider` per
agent, each returning that agent's canned JSON. The Validator runs its real
pgvector retrieval against the seeded chunk using the deterministic
`stub_embedder`.

The three scenarios:
  1. Auto-approve — $85k water damage → `settled`, no fired rules.
  2. Threshold escalation — $850k fire → `awaiting_human`, settlement ceiling
     fired, Guardrail passed.
  3. Guardrail escalation — $1.4M storm with a hallucinated endorsement →
     Guardrail `passed=False`, `awaiting_human`, `guardrail_failed` fired.

Plus one opt-in real-call test (gated by `RUN_LLM_E2E_TESTS=1`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import numpy as np
import psycopg
import pytest

from backend.app.agents.adjuster import Adjuster
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.validator import Validator
from backend.app.escalation.policy import EscalationPolicy
from backend.app.orchestrator.models import PipelineResult
from backend.app.orchestrator.pipeline import PipelineOrchestrator
from backend.app.prompts import PromptLoader
from backend.app.runs.repository import RunsRepository
from backend.data.market_data import load_market_data
from backend.settings import Settings

from .conftest import MockProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = EscalationPolicy.load_from_yaml(REPO_ROOT / "backend/app/escalation/policy.yaml")


# --------------------------------------------------------------------------- #
# Seeding helpers
# --------------------------------------------------------------------------- #


@contextmanager
def _conn_factory(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    yield conn


def _insert_claim(
    conn: psycopg.Connection, *, claim_type: str, amount: Decimal, narrative: str
) -> UUID:
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
                f"SCN-{claim_type[:4].upper()}-0001",
                "Commercial Property",
                "Harborline Logistics Ltd",
                "POL-1",
                date(2026, 4, 1),
                date(2026, 4, 3),
                "United Kingdom",
                narrative,
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


def _insert_chunk(
    conn: psycopg.Connection,
    embedder: Callable[[str], np.ndarray],
    source_path: str,
) -> tuple[UUID, str]:
    """Insert one policy chunk with a stub embedding; return (chunk_id, section)."""
    section = "Section 4 — Water Damage"
    content = "Water damage that is sudden and accidental is covered under this policy."
    vector = embedder(content)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO policy_chunks (
                source_path, section, chunk_index, content, token_count,
                embedding, embedding_model
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING chunk_id
            """,
            (
                source_path,
                section,
                0,
                content,
                max(1, len(content) // 4),
                vector.tolist(),
                "BAAI/bge-small-en-v1.5",
            ),
        )
        row = cur.fetchone()
        assert row is not None
        chunk_id: UUID = row[0]
    conn.commit()
    return chunk_id, section


# --------------------------------------------------------------------------- #
# Mock-response builders (one canned JSON per agent)
# --------------------------------------------------------------------------- #


def _doc_summary() -> str:
    """Doc-Parser now returns a plain-prose summary; structured fields come from
    the inserted claim row, so the canned response is just the summary text."""
    return "Loss to the insured commercial property."


def _validator_json(chunk_id: UUID, section: str, confidence: float) -> str:
    return json.dumps(
        {
            "covered": True,
            "confidence": confidence,
            "reasoning": "The loss matches a covered peril in the retrieved policy text.",
            "policy_basis": section,
            "cited_chunks": [{"chunk_id": str(chunk_id), "section": section}],
        }
    )


def _adjuster_json(settlement: str, confidence: float, reasoning: str) -> str:
    return json.dumps(
        {
            "recommended_settlement": settlement,
            "confidence": confidence,
            "reasoning": reasoning,
        }
    )


def _guardrail_json(flags: list[dict[str, str]]) -> str:
    return json.dumps({"flags": flags})


# --------------------------------------------------------------------------- #
# Orchestrator wiring with real agents + mock providers
# --------------------------------------------------------------------------- #


def _build_orchestrator(
    conn: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
    *,
    doc_text: str,
    validator_text: str,
    adjuster_text: str,
    guardrail_text: str,
    validator_template: str = "validator_template",
) -> PipelineOrchestrator:
    factory = lambda: _conn_factory(conn)  # noqa: E731 — terse on purpose
    doc = DocParser(
        provider=MockProvider(response_text=doc_text),
        prompt_loader=prompt_loader,
        settings=db_settings,
        connection_factory=factory,
    )
    validator = Validator(
        provider=MockProvider(response_text=validator_text),
        prompt_loader=prompt_loader,
        embedder=stub_embedder,
        settings=db_settings,
        connection_factory=factory,
        user_template_name=validator_template,
    )
    adjuster = Adjuster(
        provider=MockProvider(response_text=adjuster_text),
        prompt_loader=prompt_loader,
        market_data=load_market_data(db_settings.adjuster.market_data_path),
        settings=db_settings,
        connection_factory=factory,
    )
    guardrail = Guardrail(
        provider=MockProvider(response_text=guardrail_text),
        prompt_loader=prompt_loader,
        settings=db_settings,
        connection_factory=factory,
    )
    return PipelineOrchestrator(
        doc_parser=doc,
        validator=validator,
        adjuster=adjuster,
        guardrail=guardrail,
        policy=POLICY,
        settings=db_settings,
        connection_factory=factory,
    )


def _audit_steps(conn: psycopg.Connection, claim_id: UUID) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT step FROM audit_log WHERE claim_id = %s ORDER BY audit_id",
            (claim_id,),
        )
        return [row[0] for row in cur.fetchall()]


def _guardrail_passed(conn: psycopg.Connection, claim_id: UUID) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT payload FROM audit_log WHERE claim_id = %s AND step = 'output_check'",
            (claim_id,),
        )
        row = cur.fetchone()
    assert row is not None
    passed: bool = row[0]["output"]["passed"]
    return passed


# --------------------------------------------------------------------------- #
# Scenario 1 — auto-approve
# --------------------------------------------------------------------------- #


def test_scenario_auto_approve(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    source_path = str(db_settings.retrieval.policy_source_path)
    chunk_id, section = _insert_chunk(clean_db, stub_embedder, source_path)
    claim_id = _insert_claim(
        clean_db,
        claim_type="water_damage",
        amount=Decimal("85000.00"),
        narrative="Burst supply line flooded the warehouse mezzanine.",
    )
    orch = _build_orchestrator(
        clean_db,
        db_settings,
        prompt_loader,
        stub_embedder,
        doc_text=_doc_summary(),
        validator_text=_validator_json(chunk_id, section, 0.92),
        adjuster_text=_adjuster_json(
            "85000.00", 0.9, "Settlement sits within the market range for the loss."
        ),
        guardrail_text=_guardrail_json([]),
    )
    result = orch.run(claim_id)

    assert result.status == "settled"
    assert result.escalation_decision is not None
    assert result.escalation_decision.fired_rules == []
    # The complete audit trail: every agent ran, then escalation, then settled.
    assert _audit_steps(clean_db, claim_id) == [
        "pipeline_started",
        "doc_extract",
        "coverage_check",
        "settlement_estimate",
        "output_check",
        "escalation_decision",
        "pipeline_settled",
    ]


# --------------------------------------------------------------------------- #
# Scenario 2 — threshold escalation
# --------------------------------------------------------------------------- #


def test_scenario_threshold_escalation(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    source_path = str(db_settings.retrieval.policy_source_path)
    chunk_id, section = _insert_chunk(clean_db, stub_embedder, source_path)
    claim_id = _insert_claim(
        clean_db,
        claim_type="fire",
        amount=Decimal("850000.00"),
        narrative="Overnight electrical fire destroyed the finishing line.",
    )
    orch = _build_orchestrator(
        clean_db,
        db_settings,
        prompt_loader,
        stub_embedder,
        doc_text=_doc_summary(),
        validator_text=_validator_json(chunk_id, section, 0.88),
        adjuster_text=_adjuster_json(
            "850000.00", 0.85, "Settlement sits within the severe fire range."
        ),
        guardrail_text=_guardrail_json([]),
    )
    result = orch.run(claim_id)

    assert result.status == "awaiting_human"
    assert result.escalation_decision is not None
    names = {r.name for r in result.escalation_decision.fired_rules}
    assert "settlement_over_ceiling" in names
    # Guardrail passed; the escalation was the threshold, not a safety failure.
    assert _guardrail_passed(clean_db, claim_id) is True
    assert _audit_steps(clean_db, claim_id)[-1] == "pipeline_awaiting_human"


# --------------------------------------------------------------------------- #
# Scenario 3 — guardrail escalation
# --------------------------------------------------------------------------- #


def test_scenario_guardrail_escalation(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    source_path = str(db_settings.retrieval.policy_source_path)
    chunk_id, section = _insert_chunk(clean_db, stub_embedder, source_path)
    claim_id = _insert_claim(
        clean_db,
        claim_type="storm_complex",
        amount=Decimal("1400000.00"),
        narrative="Severe storm; claimant references an unlisted endorsement.",
    )
    # The Adjuster reasoning carries the hallucinated endorsement; the Guardrail
    # LLM flags it, driving passed=False deterministically.
    orch = _build_orchestrator(
        clean_db,
        db_settings,
        prompt_loader,
        stub_embedder,
        doc_text=_doc_summary(),
        validator_text=_validator_json(chunk_id, section, 0.8),
        adjuster_text=_adjuster_json(
            "1400000.00",
            0.82,
            "Coverage extended under Endorsement 7 referenced by the claimant.",
        ),
        guardrail_text=_guardrail_json(
            [
                {
                    "kind": "hallucinated_citation",
                    "detail": "References Endorsement 7, absent from the retrieved policy.",
                }
            ]
        ),
    )
    result = orch.run(claim_id)

    assert result.status == "awaiting_human"
    assert _guardrail_passed(clean_db, claim_id) is False
    assert result.escalation_decision is not None
    names = {r.name for r in result.escalation_decision.fired_rules}
    # guardrail_failed fires regardless of the (also-true) settlement threshold.
    assert "guardrail_failed" in names


# --------------------------------------------------------------------------- #
# Opt-in real-call test
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_E2E_TESTS") != "1"
    or not os.environ.get("ANTHROPIC_API_KEY")
    or not os.environ.get("MISTRAL_API_KEY"),
    reason="Set RUN_LLM_E2E_TESTS=1 with both API keys to exercise the live pipeline.",
)
def test_scenario_auto_approve_real_call(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
) -> None:
    """End-to-end against live Anthropic + Mistral endpoints. Opt-in."""
    from backend.app.agents.validator import default_embedder
    from backend.app.llm import get_provider
    from backend.app.llm.factory import clear_provider_cache

    clear_provider_cache()
    real_embedder = default_embedder(db_settings)
    source_path = str(db_settings.retrieval.policy_source_path)
    _insert_chunk(clean_db, real_embedder, source_path)
    claim_id = _insert_claim(
        clean_db,
        claim_type="water_damage",
        amount=Decimal("85000.00"),
        narrative=(
            "Burst supply line under the break room flooded the warehouse "
            "mezzanine; dry-stored inventory damaged. Sudden and accidental."
        ),
    )
    # Wire real providers + embedder, but pin every collaborator to the test
    # connection so the run reads the seeded claim and writes to the same DB.
    factory = lambda: _conn_factory(clean_db)  # noqa: E731
    anthropic = get_provider(db_settings, "anthropic")
    mistral = get_provider(db_settings, "mistral")
    orch = PipelineOrchestrator(
        doc_parser=DocParser(
            provider=anthropic, prompt_loader=prompt_loader,
            settings=db_settings, connection_factory=factory,
        ),
        validator=Validator(
            provider=mistral, prompt_loader=prompt_loader, embedder=real_embedder,
            settings=db_settings, connection_factory=factory,
        ),
        adjuster=Adjuster(
            provider=mistral, prompt_loader=prompt_loader,
            market_data=load_market_data(db_settings.adjuster.market_data_path),
            settings=db_settings, connection_factory=factory,
        ),
        guardrail=Guardrail(
            provider=anthropic, prompt_loader=prompt_loader,
            settings=db_settings, connection_factory=factory,
        ),
        policy=POLICY,
        settings=db_settings,
        connection_factory=factory,
    )
    result: PipelineResult = orch.run(claim_id)

    # Live model output is non-deterministic; assert the pipeline completed
    # cleanly and produced a typed result rather than aborting.
    assert result.status in {"settled", "awaiting_human"}
    assert result.doc_parser_output is not None
    assert result.adjuster_output is not None


# --------------------------------------------------------------------------- #
# Phase 5 — submit -> run -> replay -> compare
# --------------------------------------------------------------------------- #


def test_submit_run_replay_compare(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    """The decoupling story end-to-end: one claim, two runs, a comparison.

    Run 1 (default) auto-approves a confident verdict; the replay under
    `v2_strict_validator` uses the strict template and a lower-confidence verdict,
    which trips the validator-confidence floor and escalates. Both runs land in
    the audit vault under distinct correlation ids; the comparison attributes the
    escalation to the variant.
    """
    source_path = str(db_settings.retrieval.policy_source_path)
    chunk_id, section = _insert_chunk(clean_db, stub_embedder, source_path)
    claim_id = _insert_claim(
        clean_db,
        claim_type="water_damage",
        amount=Decimal("85000.00"),
        narrative="Burst supply line flooded the warehouse mezzanine.",
    )

    orch_default = _build_orchestrator(
        clean_db, db_settings, prompt_loader, stub_embedder,
        doc_text=_doc_summary(),
        validator_text=_validator_json(chunk_id, section, 0.92),
        adjuster_text=_adjuster_json("85000.00", 0.9, "Within the market range."),
        guardrail_text=_guardrail_json([]),
    )
    run_default = orch_default.run(claim_id, variant="default")
    assert run_default.status == "settled"

    orch_strict = _build_orchestrator(
        clean_db, db_settings, prompt_loader, stub_embedder,
        doc_text=_doc_summary(),
        validator_text=_validator_json(chunk_id, section, 0.5),  # below the floor
        adjuster_text=_adjuster_json("85000.00", 0.9, "Within the market range."),
        guardrail_text=_guardrail_json([]),
        validator_template="validator_strict",
    )
    run_strict = orch_strict.run(claim_id, variant="v2_strict_validator")
    assert run_strict.status == "awaiting_human"

    # Both runs are in the vault, recorded under their variants.
    summaries = RunsRepository.list_runs_for_claim(clean_db, claim_id)
    assert len(summaries) == 2
    assert {s.variant for s in summaries} == {"default", "v2_strict_validator"}

    # The comparison surfaces the escalation the strict validator caused.
    comparison = RunsRepository.compare(
        clean_db, run_default.correlation_id, run_strict.correlation_id
    )
    assert comparison.diff.escalation_changed is True
    assert comparison.diff.escalate_a is False
    assert comparison.diff.escalate_b is True
    assert "validator_confidence_floor" in comparison.diff.fired_rules_added
