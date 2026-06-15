"""
Tests for `backend.app.agents.doc_parser.DocParser`.

Phase 8.2 posture: the structured fields come from the `claims` row (the
source of truth); Haiku is asked only for `narrative_summary`. So the suite
inserts a real claim (`clean_db`), mocks the provider returning a *plain-prose
summary* (not JSON), and asserts the structured fields equal the inserted
columns. The gated `RUN_LLM_E2E_TESTS=1` test exercises the live Haiku endpoint.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest

from backend.app.agents import DocParser
from backend.app.llm.provider import LLMProviderError
from backend.app.prompts import PromptLoader
from backend.settings import Settings

from .conftest import MockProvider

# The structured columns the default `_insert_claim` writes. The refactor sources
# the Doc-Parser output from these, so the tests assert against them directly.
_CLAIM_TYPE = "water_damage"
_REPORTED_AMOUNT = Decimal("85000.00")
_CLAIMANT_NAME = "Synthetic Manufacturing Ltd."
_JURISDICTION = "United Kingdom"
_LOSS_DATE = date(2026, 4, 1)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _insert_claim(
    conn: psycopg.Connection,
    *,
    narrative: str,
    claim_number: str = "DP-TEST-0001",
    claim_type: str = _CLAIM_TYPE,
    reported_amount: Decimal = _REPORTED_AMOUNT,
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
                _CLAIMANT_NAME,
                "POL-12345",
                _LOSS_DATE,
                date(2026, 4, 3),
                _JURISDICTION,
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


@contextmanager
def _conn_factory(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Yield the test connection without closing it (clean_db owns it)."""
    yield conn


def _build_doc_parser(
    *,
    conn: psycopg.Connection,
    provider: MockProvider,
    db_settings: Settings,
    prompt_loader: PromptLoader,
) -> DocParser:
    return DocParser(
        provider=provider,
        prompt_loader=prompt_loader,
        settings=db_settings,
        connection_factory=lambda: _conn_factory(conn),
    )


def _summary_text() -> str:
    return (
        "Burst supply line flooded the warehouse mezzanine; dry-stored inventory "
        "was damaged. A plumbing report is attached."
    )


# --------------------------------------------------------------------------- #
# Happy path — structured fields from the record, summary from the model
# --------------------------------------------------------------------------- #


def test_evaluate_sources_fields_from_record(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim(
        clean_db,
        narrative="Burst supply line flooded the warehouse mezzanine.",
    )
    mock_provider.response_text = _summary_text()

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    correlation_id = uuid4()
    result = parser.evaluate(claim_id, correlation_id)

    assert result.claim_id == claim_id
    assert result.correlation_id == correlation_id
    # Structured fields come from the claim record's columns, not the model.
    assert result.output.loss_date == _LOSS_DATE
    assert result.output.jurisdiction == _JURISDICTION
    assert result.output.claim_type == _CLAIM_TYPE
    assert result.output.claimed_amount == _REPORTED_AMOUNT
    assert result.output.claimant_identifier == _CLAIMANT_NAME
    # Only the summary is model-derived.
    assert result.output.narrative_summary == _summary_text()

    # The mock received a summary prompt with system + user separation.
    assert len(mock_provider.calls) == 1
    call = mock_provider.calls[0]
    assert call.agent == "doc_parser"
    assert call.step == "doc_extract"
    assert call.response_format == "text"
    assert "Burst supply line" in call.user
    assert "summar" in call.system.lower()

    # Audit row written under the supplied correlation id, with honest provenance.
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT agent, step, payload FROM audit_log WHERE claim_id = %s",
            (claim_id,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    agent, step, payload = rows[0]
    assert agent == "doc_parser"
    assert step == "doc_extract"
    assert payload["fields_source"] == "claim_record"
    assert payload["output"]["claim_type"] == _CLAIM_TYPE
    assert payload["output"]["claimed_amount"] == "85000.00"
    assert payload["llm_call"]["provider"] == "anthropic"
    assert payload["error"] is None


# --------------------------------------------------------------------------- #
# Defensive guards
# --------------------------------------------------------------------------- #


def test_claim_not_found_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(uuid4(), uuid4())
    assert "claim not found" in str(exc_info.value)


def test_empty_narrative_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim(clean_db, narrative="   ")
    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    assert "narrative is empty" in str(exc_info.value)


def test_empty_summary_raises_and_audits(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A whitespace-only model response is a hard, audited failure."""
    claim_id = _insert_claim(clean_db, narrative="Burst supply line flooded.")
    mock_provider.response_text = "   \n  "

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    assert "empty or whitespace-only summary" in str(exc_info.value)

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "ValueError"
    assert row[0]["output"] is None


def test_oversized_summary_raises_and_audits(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A summary over the 500-char cap is rejected with the length and an excerpt."""
    claim_id = _insert_claim(clean_db, narrative="Burst supply line flooded.")
    mock_provider.response_text = "x" * 600

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    message = str(exc_info.value)
    assert "exceeds the 500-character cap" in message
    assert "600 chars" in message

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "ValueError"


def test_provider_raises_writes_audit_and_propagates(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim(clean_db, narrative="Burst supply line flooded.")
    mock_provider.raise_on_call = LLMProviderError("AnthropicProvider: timed out")

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(LLMProviderError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    assert "timed out" in str(exc_info.value)

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "LLMProviderError"
    assert row[0]["output"] is None


def test_audit_payload_truncates_long_narrative(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A 3000-char narrative appears in the audit payload as a 1000-char excerpt."""
    long_narr = "abc " * 800  # ~3200 chars
    claim_id = _insert_claim(clean_db, narrative=long_narr)
    mock_provider.response_text = _summary_text()

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    parser.evaluate(claim_id, uuid4())

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    excerpt = row[0]["input"]["narrative_excerpt"]
    assert "truncated" in excerpt
    # The excerpt body itself is 1000 chars (per the locked budget).
    assert len(excerpt) > 1000  # 1000 chars + truncation suffix.


# --------------------------------------------------------------------------- #
# Real-call test — gated.
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_E2E_TESTS") != "1"
    or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Set RUN_LLM_E2E_TESTS=1 with ANTHROPIC_API_KEY to exercise the live API.",
)
def test_doc_parser_real_call(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
) -> None:
    """End-to-end against the live Anthropic Haiku API. Opt-in."""
    from backend.app.llm import get_provider
    from backend.app.llm.factory import clear_provider_cache

    clear_provider_cache()
    provider = get_provider(db_settings, "anthropic")
    claim_id = _insert_claim(
        clean_db,
        narrative=(
            "Burst supply line under the second-floor break room flooded the "
            "warehouse mezzanine on 18 April 2026 at Harborline Logistics Ltd "
            "in the United Kingdom. Inventory loss estimated at USD 85,000."
        ),
    )
    parser = _build_doc_parser(
        conn=clean_db,
        provider=provider,  # type: ignore[arg-type]
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = parser.evaluate(claim_id, uuid4())
    # Structured fields are sourced from the record, deterministically.
    assert result.output.claimed_amount == _REPORTED_AMOUNT
    assert result.output.claim_type == _CLAIM_TYPE
    assert result.output.loss_date == _LOSS_DATE
    # The one model-derived field is a non-empty, bounded prose summary.
    assert result.output.narrative_summary.strip()
    assert len(result.output.narrative_summary) <= 500
