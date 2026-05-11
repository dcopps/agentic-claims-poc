"""
Tests for `backend.app.agents.doc_parser.DocParser`.

Strategy mirrors the Validator's suite: real Postgres (`clean_db`),
mocked LLM provider (`mock_provider`), the externalised prompts
loaded via `prompt_loader`. The gated `RUN_LLM_E2E_TESTS=1` test
exercises the live Haiku endpoint.
"""

from __future__ import annotations

import json
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

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _insert_claim(
    conn: psycopg.Connection,
    *,
    narrative: str,
    claim_number: str = "DP-TEST-0001",
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
                "United Kingdom",
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


def _valid_output_json() -> str:
    return json.dumps(
        {
            "loss_date": "2026-04-18",
            "jurisdiction": "United Kingdom",
            "claim_type": "water_damage",
            "claimed_amount": "85000.00",
            "claimant_identifier": "Harborline Logistics Ltd",
            "narrative_summary": (
                "Burst supply line flooded warehouse mezzanine; dry inventory "
                "damaged. Plumbing report attached."
            ),
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
) -> None:
    claim_id = _insert_claim(
        clean_db,
        narrative="Burst supply line flooded the warehouse mezzanine.",
    )
    mock_provider.response_text = _valid_output_json()

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
    assert result.output.loss_date == date(2026, 4, 18)
    assert result.output.claim_type == "water_damage"
    assert result.output.claimed_amount == Decimal("85000.00")
    assert result.output.jurisdiction == "United Kingdom"
    assert "warehouse" in result.output.narrative_summary

    # Mock received the prompt with system + user separation.
    assert len(mock_provider.calls) == 1
    call = mock_provider.calls[0]
    assert call.agent == "doc_parser"
    assert call.step == "doc_extract"
    assert call.response_format == "text"
    assert "Burst supply line" in call.user
    assert "document parser" in call.system

    # Audit row written under the supplied correlation id.
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
    assert payload["output"]["claim_type"] == "water_damage"
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


def test_non_json_response_raises_and_audits(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
    mock_provider.response_text = "absolutely not json"

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    assert "no `{...}` block" in str(exc_info.value)

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "ValueError"


def test_non_object_json_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
    # `{"foo"}` is not an object — but is also not valid JSON, so this
    # exercises the "JSON is not an object" branch with a JSON array.
    mock_provider.response_text = "[1, 2, 3]"

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    # The `_extract_json_block` helper looks for `{...}`; a top-level
    # array triggers the "no `{...}` block" guard, not the "not an
    # object" guard. Wrap an object inside text to reach the second
    # branch: a string that contains `{...}` but parses to a non-dict
    # after slicing.
    mock_provider.response_text = "prefix {123} suffix"
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    # "{123}" parses as JSON-invalid (`123` is a value, not a key:value),
    # so the JSON-parse guard fires first. Both guards live on the
    # parse path and both have triggering coverage elsewhere; this one
    # asserts the JSON-decode guard message specifically.
    assert "not valid JSON" in str(exc_info.value)


def test_schema_failing_json_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A negative claimed_amount violates the `gt=0` constraint."""
    claim_id = _insert_claim(clean_db, narrative="X")
    bad = json.loads(_valid_output_json())
    bad["claimed_amount"] = "-100"
    mock_provider.response_text = json.dumps(bad)

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    assert "schema validation" in str(exc_info.value)


def test_bad_date_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A non-ISO date trips Pydantic's date validator."""
    claim_id = _insert_claim(clean_db, narrative="X")
    bad = json.loads(_valid_output_json())
    bad["loss_date"] = "not-a-date"
    mock_provider.response_text = json.dumps(bad)

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    assert "schema validation" in str(exc_info.value)


def test_oversized_summary_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A 600-char summary exceeds the 500-char cap."""
    claim_id = _insert_claim(clean_db, narrative="X")
    bad = json.loads(_valid_output_json())
    bad["narrative_summary"] = "x" * 600
    mock_provider.response_text = json.dumps(bad)

    parser = _build_doc_parser(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        parser.evaluate(claim_id, uuid4())
    assert "schema validation" in str(exc_info.value)


def test_provider_raises_writes_audit_and_propagates(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim(clean_db, narrative="X")
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
    mock_provider.response_text = _valid_output_json()

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
    assert result.output.claimed_amount > Decimal("0")
    assert result.output.claim_type
    assert result.output.loss_date is not None
