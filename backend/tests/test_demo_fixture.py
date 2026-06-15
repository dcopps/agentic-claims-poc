"""
Tests for the scenario-3 deterministic demo fixture (Phase 7).

The seeded `guardrail_escalation` claim returns a fixture Adjuster output (a
planted hallucinated endorsement) instead of calling the LLM, so the guardrail
escalation reproduces deterministically — caught by the Guardrail's regex, not by
model luck. These tests cover the fixture's schema, the fail-closed loader guards,
and the end-to-end deterministic path (asserting the Adjuster LLM is never called
and the audit records `demo_fixture: true`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import numpy as np
import psycopg
import pytest

from backend.app.agents.adjuster import Adjuster, _load_fixture_output
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.validator import Validator
from backend.app.orchestrator.pipeline import PipelineOrchestrator
from backend.app.prompts import PromptLoader
from backend.data.market_data import load_market_data
from backend.settings import Settings

from .conftest import MockProvider
from .test_pipeline_scenarios import (
    POLICY,
    _doc_summary,
    _guardrail_json,
    _insert_chunk,
    _validator_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "backend/data/demo_fixtures/guardrail_adjuster.json"


@contextmanager
def _conn_factory(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    yield conn


# --------------------------------------------------------------------------- #
# Schema + fail-closed loader
# --------------------------------------------------------------------------- #


def test_fixture_deserialises_into_adjuster_output() -> None:
    output = _load_fixture_output(FIXTURE_PATH)
    assert output.recommended_settlement == Decimal("1400000.00")
    assert "Coastal Surge Rider" in output.reasoning  # the planted endorsement


def test_loader_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        _load_fixture_output(tmp_path / "nope.json")
    assert "not found" in str(exc.value)


def test_loader_non_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json at all", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        _load_fixture_output(path)
    assert "not valid JSON" in str(exc.value)


def test_loader_schema_failure_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"recommended_settlement": "-1", "confidence": 0.5, "reasoning": "x"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        _load_fixture_output(path)
    assert "validation" in str(exc.value)


# --------------------------------------------------------------------------- #
# End-to-end deterministic guardrail escalation
# --------------------------------------------------------------------------- #


def _insert_guardrail_claim(conn: psycopg.Connection) -> UUID:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO claims (claim_number, line_of_business, claimant_name,
                policy_number, loss_date, reported_date, jurisdiction, narrative,
                claim_type, reported_amount, status, scenario_tag)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING claim_id
            """,
            (
                "CLM-2026-0003", "Commercial Property", "Coral Bay Holdings",
                "CP-2026-9003", date(2026, 2, 28), date(2026, 3, 1), "Bermuda",
                "Severe storm; claimant references an unlisted endorsement.",
                "storm_complex", Decimal("1400000.00"), "received",
                "guardrail_escalation",
            ),
        )
        row = cur.fetchone()
    assert row is not None
    conn.commit()
    claim_id: UUID = row[0]
    return claim_id


def test_guardrail_escalation_reproduces_deterministically(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    source_path = str(db_settings.retrieval.policy_source_path)
    chunk_id, section = _insert_chunk(clean_db, stub_embedder, source_path)
    claim_id = _insert_guardrail_claim(clean_db)
    factory = lambda: _conn_factory(clean_db)  # noqa: E731

    # The Adjuster's provider raises if called — proving the fixture path skips
    # the live LLM entirely.
    adjuster_provider = MockProvider(
        raise_on_call=AssertionError("Adjuster LLM must not be called for the demo fixture")
    )
    orch = PipelineOrchestrator(
        doc_parser=DocParser(
            provider=MockProvider(response_text=_doc_summary()),
            prompt_loader=prompt_loader, settings=db_settings, connection_factory=factory,
        ),
        validator=Validator(
            provider=MockProvider(response_text=_validator_json(chunk_id, section, 0.85)),
            prompt_loader=prompt_loader, embedder=stub_embedder,
            settings=db_settings, connection_factory=factory,
        ),
        adjuster=Adjuster(
            provider=adjuster_provider, prompt_loader=prompt_loader,
            market_data=load_market_data(db_settings.adjuster.market_data_path),
            settings=db_settings, connection_factory=factory,
        ),
        guardrail=Guardrail(
            provider=MockProvider(response_text=_guardrail_json([])),  # rule engine catches it
            prompt_loader=prompt_loader, settings=db_settings, connection_factory=factory,
        ),
        policy=POLICY, settings=db_settings, connection_factory=factory,
    )
    result = orch.run(claim_id)

    assert result.status == "awaiting_human"
    assert result.guardrail_output is not None and result.guardrail_output.passed is False
    assert result.escalation_decision is not None
    assert "guardrail_failed" in {r.name for r in result.escalation_decision.fired_rules}
    # The Adjuster LLM was never called.
    assert adjuster_provider.calls == []
    # The audit trail is truthful: the Adjuster output came from a fixture.
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT payload FROM audit_log WHERE claim_id = %s AND step = 'settlement_estimate'",
            (claim_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0]["demo_fixture"] is True
    assert row[0]["llm_call"]["provider"] == "demo_fixture"
