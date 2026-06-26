"""
Phase 8.4 regression tests — audit rows survive the agent's own connection close.

These tests exist because the 331-test suite missed a production-only data-loss
bug: Doc-Parser, Validator, and Adjuster each ran a SELECT before the audit write,
which (under the old `autocommit=False`) opened an implicit transaction that
demoted `AuditWriter`'s `conn.transaction()` to a nested SAVEPOINT. The savepoint
"committed" but the enclosing implicit transaction was never committed, so closing
the connection rolled the audit INSERT back. Three of every four agent audit rows
vanished in production while every test stayed green.

The discriminator is the **two-connection design**. Each test:
  1. Seeds and commits a claim so the audit FK resolves on any connection.
  2. Wires the agent with the **unmodified production `open_connection`** — no
     autocommit override, no commit-in-fixture — so `evaluate` opens, writes, and
     closes a real connection exactly as production does.
  3. Opens a **separate second connection** after `evaluate` returns and reads the
     audit row through it.

A test that read the row through the same connection that wrote it would see the
row inside its own transaction and mask the rollback — which is exactly why the
existing agent suites (they share the writing connection via `clean_db`) never
caught this. Run against the pre-fix code, the first three tests fail (no row);
the Guardrail test passes either way and documents that the always-working path
stays working.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import psycopg

from backend.app.agents import (
    Adjuster,
    AdjusterOutput,
    AdjusterResult,
    CitedChunk,
    DocParser,
    DocParserOutput,
    Guardrail,
    RetrievedChunk,
    Validator,
    ValidatorVerdict,
)
from backend.app.prompts import PromptLoader
from backend.data.market_data import MarketRange, clear_market_data_cache, load_market_data
from backend.db.connection import open_connection
from backend.settings import Settings

from .conftest import MockProvider

_MARKET_DATA_PATH = Path("backend/data/market_data.yaml")


# --------------------------------------------------------------------------- #
# Shared helpers — the two-connection discriminator lives here.
# --------------------------------------------------------------------------- #


def _insert_claim(conn: psycopg.Connection, *, claim_number: str) -> UUID:
    """Insert and commit one claim row; return its claim_id.

    Commits explicitly so the claim is visible to the *separate* connection the
    agent opens via the production factory. Under autocommit the INSERT commits
    on execute; the helper stays correct either way.
    """
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
                "United Kingdom",
                "Burst supply line flooded warehouse mezzanine.",
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


def _insert_chunk(
    conn: psycopg.Connection, *, section: str, content: str, chunk_index: int
) -> UUID:
    """Insert and commit one policy_chunks row with a stub embedding."""
    vector = _stub_vector(content)
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
                "backend/data/sample_policy.txt",
                section,
                chunk_index,
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
    return chunk_id


def _stub_vector(text: str) -> np.ndarray:
    """A deterministic, correctly-dimensioned (384) unit vector for `text`."""
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    repeated = (digest * 12)[:384]
    vector = np.frombuffer(repeated, dtype=np.uint8).astype(np.float32) - 127.5
    norm = float(np.linalg.norm(vector))
    assert norm != 0.0
    return (vector / norm).astype(np.float32)


def _prod_factory(
    db_settings: Settings,
) -> Callable[[], AbstractContextManager[psycopg.Connection]]:
    """The production connection factory — a fresh `open_connection` per call.

    This is the whole point: the agent opens and *closes* its own connection,
    so the test only passes if the audit write is durable after that close.
    """
    return lambda: open_connection(db_settings)


def _fetch_audit_step(
    db_settings: Settings, correlation_id: UUID
) -> tuple[str, str] | None:
    """Read `(agent, step)` for `correlation_id` through a brand-new connection.

    Returns None if no row exists — which is the pre-fix failure signature for
    the three SELECT-before-write agents.
    """
    with open_connection(db_settings) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT agent, step FROM audit_log WHERE correlation_id = %s",
            (correlation_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return row[0], row[1]


# --------------------------------------------------------------------------- #
# One test per agent.
# --------------------------------------------------------------------------- #


def test_doc_parser_audit_persists_across_connection(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """Doc-Parser's `doc_extract` row survives its connection close."""
    claim_id = _insert_claim(clean_db, claim_number="AP-DP-0001")
    mock_provider.response_text = "Burst supply line flooded the mezzanine; stock damaged."

    parser = DocParser(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        settings=db_settings,
        connection_factory=_prod_factory(db_settings),
    )
    correlation_id = uuid4()
    parser.evaluate(claim_id, correlation_id)

    assert _fetch_audit_step(db_settings, correlation_id) == ("doc_parser", "doc_extract")


def test_validator_audit_persists_across_connection(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """Validator's `coverage_check` row survives — it SELECTs (pgvector) first."""
    claim_id = _insert_claim(clean_db, claim_number="AP-VL-0001")
    chunk_ids = [
        _insert_chunk(
            clean_db,
            section="Named Perils Covered",
            content="Fire, lightning, windstorm, water damage.",
            chunk_index=0,
        ),
        _insert_chunk(
            clean_db,
            section="Exclusions",
            content="Flood and earthquake are excluded.",
            chunk_index=1,
        ),
    ]
    mock_provider.response_text = json.dumps(
        {
            "covered": True,
            "confidence": 0.83,
            "reasoning": "Water damage maps to the named perils language.",
            "policy_basis": "Named Perils Covered",
            "cited_chunks": [
                {"chunk_id": str(chunk_ids[0]), "section": "Named Perils Covered"}
            ],
        }
    )

    validator = Validator(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        embedder=_stub_vector,
        settings=db_settings,
        connection_factory=_prod_factory(db_settings),
    )
    correlation_id = uuid4()
    validator.evaluate(claim_id, correlation_id)

    assert _fetch_audit_step(db_settings, correlation_id) == (
        "validator",
        "coverage_check",
    )


def test_adjuster_audit_persists_across_connection(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """Adjuster's `settlement_estimate` row survives — it SELECTs the fixture first."""
    clear_market_data_cache()
    claim_id = _insert_claim(clean_db, claim_number="AP-AD-0001")
    mock_provider.response_text = json.dumps(
        {
            "recommended_settlement": "85000.00",
            "confidence": 0.82,
            "reasoning": "Mid-range moderate water_damage.",
        }
    )

    adjuster = Adjuster(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        market_data=load_market_data(_MARKET_DATA_PATH),
        settings=db_settings,
        connection_factory=_prod_factory(db_settings),
    )
    correlation_id = uuid4()
    adjuster.evaluate(
        claim_id,
        correlation_id,
        parsed_claim=_parsed_claim(),
        validator_verdict=_validator_verdict(),
    )

    assert _fetch_audit_step(db_settings, correlation_id) == (
        "adjuster",
        "settlement_estimate",
    )


def test_guardrail_audit_persists_across_connection(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """Guardrail's `output_check` row persists — it does no pre-write SQL.

    This path always worked; the test documents that the fix does not regress it.
    """
    claim_id = _insert_claim(clean_db, claim_number="AP-GR-0001")
    mock_provider.response_text = json.dumps({"flags": [], "summary": "No issues."})

    guardrail = Guardrail(
        provider=mock_provider,
        prompt_loader=prompt_loader,
        settings=db_settings,
        connection_factory=_prod_factory(db_settings),
    )
    correlation_id = uuid4()
    guardrail.evaluate(
        claim_id,
        correlation_id,
        adjuster_result=_adjuster_result(),
        retrieved_chunks=_retrieved_chunks(),
    )

    assert _fetch_audit_step(db_settings, correlation_id) == ("guardrail", "output_check")


# --------------------------------------------------------------------------- #
# Minimal in-memory inputs for the Adjuster and Guardrail (no DB).
# --------------------------------------------------------------------------- #


def _parsed_claim() -> DocParserOutput:
    return DocParserOutput(
        loss_date=date(2026, 4, 18),
        jurisdiction="United Kingdom",
        claim_type="water_damage",
        claimed_amount=Decimal("85000.00"),
        claimant_identifier="Harborline Logistics Ltd",
        narrative_summary="Burst supply line flooded warehouse mezzanine.",
    )


def _validator_verdict() -> ValidatorVerdict:
    return ValidatorVerdict(
        covered=True,
        confidence=0.88,
        reasoning="Water damage maps cleanly to the named-perils list.",
        policy_basis="Named Perils Covered",
        cited_chunks=[CitedChunk(chunk_id=uuid4(), section="Named Perils Covered")],
    )


def _adjuster_result() -> AdjusterResult:
    return AdjusterResult(
        claim_id=uuid4(),
        correlation_id=uuid4(),
        output=AdjusterOutput(
            recommended_settlement=Decimal("85000.00"),
            confidence=0.82,
            reasoning="Mid-range water_damage settlement; scope supports the value.",
        ),
        market_range=MarketRange(
            claim_type="water_damage",
            severity="moderate",
            floor=Decimal("50000"),
            ceiling=Decimal("200000"),
        ),
        model="mock-model-latest",
        latency_ms=12,
    )


def _retrieved_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=uuid4(),
            section="Named Perils Covered",
            content="Fire, lightning, windstorm, water damage.",
            similarity=0.85,
        ),
    ]
