"""
Tests for `backend.app.agents.validator.Validator`.

Strategy: the provider is mocked (`MockProvider` fixture); the
embedder is stubbed (`stub_embedder` fixture); the database is the
real Phase 1 fixture (`clean_db`). This exercises the validator's
SQL, the AuditWriter integration, and the JSON-parsing logic against
a real Postgres while keeping the LLM out of CI.

A separate `test_validator_real_call` is gated by
`RUN_LLM_E2E_TESTS=1` and a populated `MISTRAL_API_KEY`; it exercises
the full flow against the live Mistral API.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import numpy as np
import psycopg
import pytest

from backend.app.agents import Validator
from backend.app.llm.provider import LLMProviderError
from backend.app.prompts import PromptLoader
from backend.settings import Settings

from .conftest import MockProvider

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _insert_claim(
    conn: psycopg.Connection,
    *,
    narrative: str,
    claim_number: str = "SEED-0001",
    claim_type: str = "water_damage",
    reported_amount: Decimal = Decimal("85000.00"),
) -> UUID:
    """Insert one claim row and return its claim_id."""
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
                claim_number,
                "Commercial Property",
                "Synthetic Manufacturing Ltd.",
                "POL-12345",
                date(2026, 4, 1),
                date(2026, 4, 3),
                "Bermuda",
                narrative,
                claim_type,
                reported_amount,
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
    *,
    section: str,
    content: str,
    chunk_index: int,
    vector: np.ndarray,
    source_path: str = "backend/data/sample_policy.txt",
) -> UUID:
    """Insert one policy_chunks row and return its chunk_id."""
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
                chunk_index,
                content,
                max(1, len(content) // 4),  # rough token count, just non-zero
                vector.tolist(),
                "BAAI/bge-small-en-v1.5",
            ),
        )
        row = cur.fetchone()
        assert row is not None
        chunk_id: UUID = row[0]
    conn.commit()
    return chunk_id


def _seed_chunks(
    conn: psycopg.Connection, stub_embedder: Callable[[str], np.ndarray]
) -> list[UUID]:
    """Seed three policy chunks using the stub embedder for vectors."""
    chunks = [
        ("Named Perils Covered", "Fire, lightning, windstorm, water damage."),
        ("Exclusions", "Flood and earthquake are excluded."),
        ("Sub-Limits", "Debris removal: 25% of direct damage."),
    ]
    ids: list[UUID] = []
    for idx, (section, content) in enumerate(chunks):
        vec = stub_embedder(content)
        ids.append(
            _insert_chunk(
                conn,
                section=section,
                content=content,
                chunk_index=idx,
                vector=vec,
            )
        )
    return ids


@contextmanager
def _conn_factory(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Yield the test connection without closing it (clean_db owns it)."""
    yield conn


def _build_validator(
    *,
    conn: psycopg.Connection,
    provider: MockProvider,
    embedder: Callable[[str], np.ndarray],
    db_settings: Settings,
    prompt_loader: PromptLoader,
) -> Validator:
    return Validator(
        provider=provider,
        prompt_loader=prompt_loader,
        embedder=embedder,
        settings=db_settings,
        connection_factory=lambda: _conn_factory(conn),
    )


def _verdict_json(cited_ids: list[UUID]) -> str:
    """Build a valid Mistral verdict JSON referencing the given chunk ids."""
    return json.dumps(
        {
            "covered": True,
            "confidence": 0.83,
            "reasoning": "Water damage maps to the named perils language.",
            "policy_basis": "Named Perils Covered",
            "cited_chunks": [
                {"chunk_id": str(cid), "section": "Named Perils Covered"}
                for cid in cited_ids[:2]
            ],
        }
    )


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_evaluate_returns_typed_result(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    claim_id = _insert_claim(
        clean_db, narrative="Sprinkler discharge caused water damage at the facility."
    )
    chunk_ids = _seed_chunks(clean_db, stub_embedder)
    mock_provider.response_text = _verdict_json(chunk_ids)

    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )

    correlation_id = uuid4()
    result = validator.evaluate(claim_id, correlation_id)

    assert result.claim_id == claim_id
    assert result.correlation_id == correlation_id
    assert result.verdict.covered is True
    assert len(result.retrieved_chunks) == 3
    assert all(rc.chunk_id in set(chunk_ids) for rc in result.retrieved_chunks)
    assert result.model == "mock-model-latest"

    # Mock received the prompts with system + user separation.
    assert len(mock_provider.calls) == 1
    call = mock_provider.calls[0]
    assert call.agent == "validator"
    assert call.step == "coverage_check"
    assert call.response_format == "json"
    assert "Sprinkler discharge" in call.user
    assert "coverage validator" in call.system

    # Audit log row written.
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT agent, step, payload FROM audit_log WHERE claim_id = %s",
            (claim_id,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    agent, step, payload = rows[0]
    assert agent == "validator"
    assert step == "coverage_check"
    assert payload["verdict"]["covered"] is True
    assert payload["retrieval"]["top_k"] == 3
    assert len(payload["retrieval"]["chunks"]) == 3
    # The audit reflects the *actual* provider in use (its `vendor`), not a
    # hardcoded vendor — so a variant that substitutes the provider records the
    # substitution truthfully. Here the injected MockProvider reports "mock".
    assert payload["llm_call"]["provider"] == mock_provider.vendor == "mock"
    assert payload["error"] is None


def test_evaluate_captures_prompt_with_substituted_chunks(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    """Phase 8.3: the captured user prompt holds the retrieved chunks, substituted."""
    claim_id = _insert_claim(
        clean_db, narrative="Sprinkler discharge caused water damage at the facility."
    )
    chunk_ids = _seed_chunks(clean_db, stub_embedder)
    mock_provider.response_text = _verdict_json(chunk_ids)
    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    validator.evaluate(claim_id, uuid4())

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    prompt = row[0]["llm_call"]["prompt"]
    assert isinstance(prompt["system"], str) and prompt["system"]
    # Substitution proof: a retrieved chunk's content appears verbatim in the user
    # prompt, and no template placeholder survives.
    assert "Fire, lightning, windstorm, water damage." in prompt["user"]
    assert "{retrieved_chunks}" not in prompt["user"]
    assert prompt["user"] == mock_provider.calls[0].user


# --------------------------------------------------------------------------- #
# Defensive guards — each maps to one raise inside the validator pipeline.
# --------------------------------------------------------------------------- #


def test_claim_not_found_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        validator.evaluate(uuid4(), uuid4())
    assert "claim not found" in str(exc_info.value)


def test_empty_narrative_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    claim_id = _insert_claim(clean_db, narrative="   ")
    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        validator.evaluate(claim_id, uuid4())
    assert "narrative is empty" in str(exc_info.value)


def test_no_chunks_indexed_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    claim_id = _insert_claim(clean_db, narrative="Some narrative")
    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        validator.evaluate(claim_id, uuid4())
    assert "no policy chunks retrieved" in str(exc_info.value)


def test_embedder_wrong_dimension_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
    bad_embedder = lambda _text: np.zeros(128, dtype=np.float32)  # noqa: E731
    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=bad_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        validator.evaluate(claim_id, uuid4())
    assert "unexpected shape" in str(exc_info.value)


def test_model_returns_non_json_raises_and_audits(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
    _seed_chunks(clean_db, stub_embedder)
    mock_provider.response_text = "this is not JSON at all"

    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        validator.evaluate(claim_id, uuid4())
    assert "no `{...}` block" in str(exc_info.value)

    # Audit row was still written with `error` populated.
    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "ValueError"


def test_model_returns_schema_failing_json_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
    chunk_ids = _seed_chunks(clean_db, stub_embedder)
    # `confidence` > 1 violates the schema bound.
    mock_provider.response_text = json.dumps(
        {
            "covered": True,
            "confidence": 1.5,
            "reasoning": "fine",
            "policy_basis": "Named Perils Covered",
            "cited_chunks": [
                {"chunk_id": str(chunk_ids[0]), "section": "Named Perils Covered"}
            ],
        }
    )
    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        validator.evaluate(claim_id, uuid4())
    assert "schema validation" in str(exc_info.value)


def test_model_cites_unknown_chunk_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
    _seed_chunks(clean_db, stub_embedder)
    # Citation refers to a UUID never produced by the retrieval set.
    rogue = uuid4()
    mock_provider.response_text = json.dumps(
        {
            "covered": True,
            "confidence": 0.5,
            "reasoning": "fine",
            "policy_basis": "Named Perils Covered",
            "cited_chunks": [
                {"chunk_id": str(rogue), "section": "Named Perils Covered"}
            ],
        }
    )
    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        validator.evaluate(claim_id, uuid4())
    assert "anti-hallucination" in str(exc_info.value)
    assert str(rogue) in str(exc_info.value)


def test_provider_raises_writes_audit_and_propagates(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
    _seed_chunks(clean_db, stub_embedder)
    mock_provider.raise_on_call = LLMProviderError("MistralProvider: rate limited")

    validator = _build_validator(
        conn=clean_db,
        provider=mock_provider,
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(LLMProviderError) as exc_info:
        validator.evaluate(claim_id, uuid4())
    assert "rate limited" in str(exc_info.value)

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "LLMProviderError"
    assert row[0]["verdict"] is None


# --------------------------------------------------------------------------- #
# Real-call test — gated.
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_E2E_TESTS") != "1"
    or not os.environ.get("MISTRAL_API_KEY"),
    reason="Set RUN_LLM_E2E_TESTS=1 with MISTRAL_API_KEY to exercise the live API.",
)
def test_validator_real_call(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    stub_embedder: Callable[[str], np.ndarray],
) -> None:
    """End-to-end against the live Mistral API. Opt-in."""
    from backend.app.llm import get_provider
    from backend.app.llm.factory import clear_provider_cache

    clear_provider_cache()
    provider = get_provider(db_settings, "mistral")
    claim_id = _insert_claim(
        clean_db, narrative="Sprinkler system discharged and caused water damage."
    )
    _seed_chunks(clean_db, stub_embedder)

    validator = _build_validator(
        conn=clean_db,
        provider=provider,  # type: ignore[arg-type]
        embedder=stub_embedder,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = validator.evaluate(claim_id, uuid4())
    assert isinstance(result.verdict.covered, bool)
    assert 0.0 <= result.verdict.confidence <= 1.0
    assert result.verdict.cited_chunks
