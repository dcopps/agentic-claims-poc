"""
Tests for `backend.app.agents.adjuster.Adjuster`.

Strategy: real Postgres (`clean_db`) for the audit-write integration,
mocked LLM provider, the committed `backend/data/market_data.yaml`
for the lookup table. The gated `RUN_LLM_E2E_TESTS=1` test exercises
the live Mistral endpoint with the range-enforcement guard active.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import ValidationError

from backend.app.agents import (
    Adjuster,
    AdjusterResult,
    CitedChunk,
    DocParserOutput,
    ValidatorVerdict,
)
from backend.app.llm.provider import LLMProviderError
from backend.app.prompts import PromptLoader
from backend.data.market_data import (
    MarketRange,
    clear_market_data_cache,
    load_market_data,
)
from backend.settings import Settings

from .conftest import MockProvider

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clear_market_data_cache() -> None:
    clear_market_data_cache()


@pytest.fixture()
def market_data_table() -> object:
    return load_market_data(Path("backend/data/market_data.yaml"))


@pytest.fixture()
def parsed_claim() -> DocParserOutput:
    return DocParserOutput(
        loss_date=date(2026, 4, 18),
        jurisdiction="United Kingdom",
        claim_type="water_damage",
        claimed_amount=Decimal("85000.00"),
        claimant_identifier="Harborline Logistics Ltd",
        narrative_summary=(
            "Burst supply line flooded warehouse mezzanine; dry stored "
            "inventory damaged."
        ),
    )


@pytest.fixture()
def validator_verdict() -> ValidatorVerdict:
    return ValidatorVerdict(
        covered=True,
        confidence=0.88,
        reasoning="Water damage maps cleanly to the named-perils list.",
        policy_basis="Named Perils Covered",
        cited_chunks=[
            CitedChunk(chunk_id=uuid4(), section="Named Perils Covered"),
        ],
    )


def _insert_claim_stub(conn: psycopg.Connection) -> UUID:
    """Insert a minimal claim row so the FK in audit_log resolves."""
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
                "ADJ-TEST-0001",
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


@contextmanager
def _conn_factory(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    yield conn


def _build_adjuster(
    *,
    conn: psycopg.Connection,
    provider: MockProvider,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    market_data_table: object,
) -> Adjuster:
    return Adjuster(
        provider=provider,
        prompt_loader=prompt_loader,
        market_data=market_data_table,  # type: ignore[arg-type]
        settings=db_settings,
        connection_factory=lambda: _conn_factory(conn),
    )


def _valid_output_json(value: str = "85000.00") -> str:
    return json.dumps(
        {
            "recommended_settlement": value,
            "confidence": 0.82,
            "reasoning": (
                "Damage scope (flooded mezzanine, dry inventory) sits "
                "mid-range for moderate water_damage."
            ),
        }
    )


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_evaluate_returns_typed_result_inside_range(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    # 85_000 lands in water_damage / moderate (50_000..200_000); the
    # model returns 85_000 — inside the range.
    mock_provider.response_text = _valid_output_json("85000.00")

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    result = adjuster.evaluate(
        claim_id,
        uuid4(),
        parsed_claim=parsed_claim,
        validator_verdict=validator_verdict,
    )

    assert isinstance(result, AdjusterResult)
    assert result.output.recommended_settlement == Decimal("85000.00")
    assert result.market_range.severity == "moderate"
    assert result.market_range.contains(result.output.recommended_settlement)

    # Mock received the prompt with system + user separation.
    assert len(mock_provider.calls) == 1
    call = mock_provider.calls[0]
    assert call.agent == "adjuster"
    assert call.step == "settlement_estimate"
    assert call.response_format == "json"
    assert "50000" in call.user  # range floor in the user prompt
    assert "200000" in call.user  # range ceiling
    assert "settlement adjuster" in call.system

    # Audit row written.
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT payload FROM audit_log WHERE claim_id = %s",
            (claim_id,),
        )
        row = cur.fetchone()
    assert row is not None
    payload = row[0]
    assert payload["market_data"]["claim_type"] == "water_damage"
    assert payload["market_data"]["severity"] == "moderate"
    assert payload["market_data"]["floor"] == "50000"
    assert payload["market_data"]["ceiling"] == "200000"
    assert payload["output"]["recommended_settlement"] == "85000.00"
    assert payload["llm_call"]["provider"] == "mistral"
    # The audit carries the full reasoning (Phase 5 runs reconstruction reads it).
    # For a short demo reasoning it equals the excerpt — i.e. nothing truncated.
    assert payload["output"]["reasoning"] == payload["output"]["reasoning_excerpt"]
    assert len(payload["output"]["reasoning"]) > 0


def test_evaluate_captures_literal_prompt_in_audit(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    """Phase 8.3: the live path records the literal prompt under llm_call.prompt."""
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _valid_output_json("85000.00")
    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    adjuster.evaluate(
        claim_id,
        uuid4(),
        parsed_claim=parsed_claim,
        validator_verdict=validator_verdict,
    )

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    prompt = row[0]["llm_call"]["prompt"]
    assert isinstance(prompt["system"], str) and prompt["system"]
    # The market range was substituted into the user prompt (no placeholder left).
    assert "50000" in prompt["user"] and "200000" in prompt["user"]
    assert "{range_floor}" not in prompt["user"]
    assert prompt["user"] == mock_provider.calls[0].user


# --------------------------------------------------------------------------- #
# Range-enforcement guard — the headline Adjuster contract.
# --------------------------------------------------------------------------- #


def test_out_of_range_value_above_ceiling_raises_and_audits(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    # 250_000 is above the moderate water_damage ceiling (200_000).
    mock_provider.response_text = _valid_output_json("250000.00")

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    with pytest.raises(ValueError) as exc_info:
        adjuster.evaluate(
            claim_id,
            uuid4(),
            parsed_claim=parsed_claim,
            validator_verdict=validator_verdict,
        )
    assert "outside the market range" in str(exc_info.value)
    assert "refusing to silently clamp" in str(exc_info.value)

    # The audit log records the failure under the same correlation id.
    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "ValueError"
    assert row[0]["output"] is None


def test_out_of_range_value_below_floor_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    # 1_000 is below the moderate water_damage floor (50_000).
    mock_provider.response_text = _valid_output_json("1000.00")

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    with pytest.raises(ValueError) as exc_info:
        adjuster.evaluate(
            claim_id,
            uuid4(),
            parsed_claim=parsed_claim,
            validator_verdict=validator_verdict,
        )
    assert "outside the market range" in str(exc_info.value)


def test_adjuster_result_direct_construction_revalidates(
    parsed_claim: DocParserOutput, validator_verdict: ValidatorVerdict
) -> None:
    """`AdjusterResult` re-asserts within-range on direct construction."""
    from backend.app.agents.adjuster_models import AdjusterOutput

    bad_output = AdjusterOutput(
        recommended_settlement=Decimal("9999999"),
        confidence=0.8,
        reasoning="oversized value for the demo range",
    )
    bad_range = MarketRange(
        claim_type="water_damage",
        severity="moderate",
        floor=Decimal("50000"),
        ceiling=Decimal("200000"),
    )
    with pytest.raises(ValidationError) as exc_info:
        AdjusterResult(
            claim_id=uuid4(),
            correlation_id=uuid4(),
            output=bad_output,
            market_range=bad_range,
            model="mock-model",
            latency_ms=10,
        )
    assert "outside the market range" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Defensive guards
# --------------------------------------------------------------------------- #


def test_unknown_claim_type_raises_on_lookup(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    validator_verdict: ValidatorVerdict,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    parsed = DocParserOutput(
        loss_date=date(2026, 4, 18),
        jurisdiction="United Kingdom",
        claim_type="meteor_strike",
        claimed_amount=Decimal("85000.00"),
        claimant_identifier="Harborline Logistics Ltd",
        narrative_summary="Burst supply line.",
    )
    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    with pytest.raises(ValueError) as exc_info:
        adjuster.evaluate(
            claim_id,
            uuid4(),
            parsed_claim=parsed,
            validator_verdict=validator_verdict,
        )
    assert "unknown claim_type" in str(exc_info.value)


def test_non_json_response_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = "definitely not json"

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    with pytest.raises(ValueError) as exc_info:
        adjuster.evaluate(
            claim_id,
            uuid4(),
            parsed_claim=parsed_claim,
            validator_verdict=validator_verdict,
        )
    assert "no `{...}` block" in str(exc_info.value)


def test_schema_failing_json_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    # Confidence > 1 violates schema bound.
    mock_provider.response_text = json.dumps(
        {
            "recommended_settlement": "85000.00",
            "confidence": 1.5,
            "reasoning": "fine",
        }
    )

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    with pytest.raises(ValueError) as exc_info:
        adjuster.evaluate(
            claim_id,
            uuid4(),
            parsed_claim=parsed_claim,
            validator_verdict=validator_verdict,
        )
    assert "schema validation" in str(exc_info.value)


def test_provider_raises_writes_audit_and_propagates(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.raise_on_call = LLMProviderError("MistralProvider: rate limited")

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    with pytest.raises(LLMProviderError):
        adjuster.evaluate(
            claim_id,
            uuid4(),
            parsed_claim=parsed_claim,
            validator_verdict=validator_verdict,
        )

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "LLMProviderError"


# --------------------------------------------------------------------------- #
# Market-data integration
# --------------------------------------------------------------------------- #


def test_lookup_threads_correct_range_for_fire_severe(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    market_data_table: object,
    validator_verdict: ValidatorVerdict,
) -> None:
    """A fire claim at $850k routes to fire / severe (500k..1.5M)."""
    claim_id = _insert_claim_stub(clean_db)
    parsed = DocParserOutput(
        loss_date=date(2026, 3, 12),
        jurisdiction="United States — New York",
        claim_type="fire",
        claimed_amount=Decimal("850000.00"),
        claimant_identifier="Northwood Manufacturing Inc",
        narrative_summary="Electrical-panel fire destroyed finishing line.",
    )
    mock_provider.response_text = json.dumps(
        {
            "recommended_settlement": "850000.00",
            "confidence": 0.85,
            "reasoning": "Severe fire range; substantial equipment loss.",
        }
    )

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    result = adjuster.evaluate(
        claim_id,
        uuid4(),
        parsed_claim=parsed,
        validator_verdict=validator_verdict,
    )
    assert result.market_range.claim_type == "fire"
    assert result.market_range.severity == "severe"
    assert result.market_range.floor == Decimal("500000")
    assert result.market_range.ceiling == Decimal("1500000")


# --------------------------------------------------------------------------- #
# Real-call test — gated.
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_E2E_TESTS") != "1"
    or not os.environ.get("MISTRAL_API_KEY"),
    reason="Set RUN_LLM_E2E_TESTS=1 with MISTRAL_API_KEY to exercise the live API.",
)
def test_adjuster_real_call(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    market_data_table: object,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
) -> None:
    """End-to-end against the live Mistral API. Opt-in."""
    from backend.app.llm import get_provider
    from backend.app.llm.factory import clear_provider_cache

    clear_provider_cache()
    provider = get_provider(db_settings, "mistral")
    claim_id = _insert_claim_stub(clean_db)

    adjuster = _build_adjuster(
        conn=clean_db,
        provider=provider,  # type: ignore[arg-type]
        db_settings=db_settings,
        prompt_loader=prompt_loader,
        market_data_table=market_data_table,
    )
    result = adjuster.evaluate(
        claim_id,
        uuid4(),
        parsed_claim=parsed_claim,
        validator_verdict=validator_verdict,
    )
    # Live model must produce an in-range value (the agent's parser
    # guarantees this for any successful return).
    assert result.market_range.contains(result.output.recommended_settlement)
    assert 0.0 <= result.output.confidence <= 1.0
