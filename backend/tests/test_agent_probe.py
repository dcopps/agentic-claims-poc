"""
Tests for the agents' non-audit `probe` methods (Phase 6 test bench).

Each probe runs the agent's prompt → LLM → parse path with a mock provider and
returns the typed output plus `ProbeMetadata`, writing **no** audit entry. The
key assertion per agent is that `audit_log` stays empty after a probe — the test
bench is out-of-band by design.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import uuid4

import numpy as np
import psycopg

from backend.app.agents.adjuster import Adjuster
from backend.app.agents.adjuster_models import AdjusterOutput
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.doc_parser_models import DocParserOutput
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.validator import Validator
from backend.app.agents.validator_models import CitedChunk, RetrievedChunk, ValidatorVerdict
from backend.app.prompts import PromptLoader
from backend.data.market_data import load_market_data
from backend.settings import Settings

from .conftest import MockProvider


@contextmanager
def _conn_factory(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    yield conn


def _audit_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log")
        row = cur.fetchone()
    assert row is not None
    return int(row[0])


def _insert_chunk(
    conn: psycopg.Connection, embedder: Callable[[str], np.ndarray], source_path: str
) -> tuple[str, str]:
    section = "Section 4 — Water Damage"
    content = "Water damage that is sudden and accidental is covered."
    vector = embedder(content)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO policy_chunks (source_path, section, chunk_index, content,
                token_count, embedding, embedding_model)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING chunk_id
            """,
            (source_path, section, 0, content, 10, vector.tolist(), "BAAI/bge-small-en-v1.5"),
        )
        row = cur.fetchone()
    assert row is not None
    return str(row[0]), section


def _doc_output() -> DocParserOutput:
    return DocParserOutput(
        loss_date=date(2026, 4, 18),
        jurisdiction="United Kingdom",
        claim_type="water_damage",
        claimed_amount=Decimal("85000.00"),
        claimant_identifier="Acme Ltd",
        narrative_summary="Burst supply line flooded the floor.",
    )


def _verdict() -> ValidatorVerdict:
    return ValidatorVerdict(
        covered=True,
        confidence=0.9,
        reasoning="Covered peril.",
        policy_basis="Section 4",
        cited_chunks=[CitedChunk(chunk_id=uuid4(), section="Section 4")],
    )


def _adjuster_output() -> AdjusterOutput:
    return AdjusterOutput(
        recommended_settlement=Decimal("85000.00"),
        confidence=0.9,
        reasoning="Within the market range.",
    )


def _chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=uuid4(),
            section="Section 4",
            content="Water damage that is sudden and accidental is covered.",
            similarity=0.9,
        )
    ]


# --------------------------------------------------------------------------- #
# Probes
# --------------------------------------------------------------------------- #


def test_doc_parser_probe_no_audit(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    mock_provider.response_text = "Burst supply line flooded the floor."
    parser = DocParser(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        settings=db_settings,
        connection_factory=lambda: _conn_factory(clean_db),
    )
    output, meta = parser.parse("Burst supply line flooded the floor.")
    # The summary is the real model output; structured fields are probe sentinels
    # (no claim record exists on the probe path).
    assert output.narrative_summary == "Burst supply line flooded the floor."
    assert output.claim_type == "unknown"
    assert output.jurisdiction == "Unknown"
    assert output.claimant_identifier == "Unknown"
    assert meta.model == "mock-model-latest"
    assert _audit_count(clean_db) == 0


def test_validator_probe_no_audit(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    source_path = str(db_settings.retrieval.policy_source_path)
    chunk_id, section = _insert_chunk(clean_db, stub_embedder, source_path)
    mock_provider.response_text = json.dumps(
        {
            "covered": True,
            "confidence": 0.9,
            "reasoning": "Covered peril.",
            "policy_basis": section,
            "cited_chunks": [{"chunk_id": chunk_id, "section": section}],
        }
    )
    validator = Validator(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        embedder=stub_embedder,
        settings=db_settings,
        connection_factory=lambda: _conn_factory(clean_db),
    )
    verdict, chunks, meta = validator.assess("Burst supply line flooded the floor.")
    assert verdict.covered is True
    assert len(chunks) >= 1
    assert meta.completion_tokens == 50
    assert _audit_count(clean_db) == 0


def test_adjuster_probe_no_audit(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    mock_provider.response_text = json.dumps(
        {"recommended_settlement": "85000.00", "confidence": 0.9, "reasoning": "In range."}
    )
    adjuster = Adjuster(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        market_data=load_market_data(db_settings.adjuster.market_data_path),
        settings=db_settings,
        connection_factory=lambda: _conn_factory(clean_db),
    )
    output, meta = adjuster.estimate(_doc_output(), _verdict())
    assert output.recommended_settlement == Decimal("85000.00")
    assert meta.prompt_tokens == 100
    assert _audit_count(clean_db) == 0


def test_guardrail_probe_no_audit(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    mock_provider.response_text = json.dumps({"flags": []})
    guardrail = Guardrail(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        settings=db_settings,
        connection_factory=lambda: _conn_factory(clean_db),
    )
    output, meta = guardrail.check(_adjuster_output(), _chunks())
    assert output.passed is True
    assert meta.model == "mock-model-latest"
    assert _audit_count(clean_db) == 0
