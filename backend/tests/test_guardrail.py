"""
Tests for `backend.app.agents.guardrail.Guardrail`.

Strategy: real Postgres (`clean_db`) for the audit-write integration,
mocked LLM provider, the production `GuardrailRuleEngine` (i.e.
deterministic regex floor) plus controlled inputs. The gated
`RUN_LLM_E2E_TESTS=1` test exercises the live Haiku endpoint.
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
from pydantic import ValidationError

from backend.app.agents import (
    AdjusterOutput,
    AdjusterResult,
    Guardrail,
    GuardrailOutput,
    GuardrailResult,
    GuardrailRuleEngine,
    RetrievedChunk,
)
from backend.app.llm.provider import LLMProviderError
from backend.app.prompts import PromptLoader
from backend.data.market_data import MarketRange, clear_market_data_cache
from backend.settings import Settings

from .conftest import MockProvider

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clear_market_data_cache() -> None:
    clear_market_data_cache()


def _retrieved_chunks() -> list[RetrievedChunk]:
    """Three policy-like chunks for the allow-set."""
    return [
        RetrievedChunk(
            chunk_id=uuid4(),
            section="Named Perils Covered",
            content=(
                "Fire, lightning, windstorm, hail, explosion, smoke, vandalism, "
                "sprinkler leakage, water damage."
            ),
            similarity=0.85,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            section="Exclusions",
            content="Flood and earthquake are excluded.",
            similarity=0.62,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            section="Sub-Limits",
            content="Debris removal: 25% of direct damage.",
            similarity=0.55,
        ),
    ]


def _adjuster_result(reasoning: str) -> AdjusterResult:
    """Build an in-range AdjusterResult carrying `reasoning`."""
    return AdjusterResult(
        claim_id=uuid4(),
        correlation_id=uuid4(),
        output=AdjusterOutput(
            recommended_settlement=Decimal("85000.00"),
            confidence=0.82,
            reasoning=reasoning,
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


def _insert_claim_stub(conn: psycopg.Connection) -> UUID:
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
                "GR-TEST-0001",
                "Commercial Property",
                "Synthetic Manufacturing Ltd.",
                "POL-12345",
                date(2026, 4, 1),
                date(2026, 4, 3),
                "United Kingdom",
                "Burst supply line flooded warehouse.",
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


def _build_guardrail(
    *,
    conn: psycopg.Connection,
    provider: MockProvider,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    rule_engine: GuardrailRuleEngine | None = None,
) -> Guardrail:
    return Guardrail(
        provider=provider,
        prompt_loader=prompt_loader,
        settings=db_settings,
        rule_engine=rule_engine,
        connection_factory=lambda: _conn_factory(conn),
    )


def _llm_clean_response() -> str:
    return json.dumps(
        {"flags": [], "summary": "No additional issues found."}
    )


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_clean_reasoning_passes(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _llm_clean_response()

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(
            "Mid-range water_damage settlement; damage scope supports the value."
        ),
        retrieved_chunks=_retrieved_chunks(),
    )
    assert isinstance(result, GuardrailResult)
    assert result.output.passed is True
    assert result.output.flags == []

    # Audit row written with `passed=True`.
    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["output"]["passed"] is True
    assert row[0]["rule_checks"]["flag_count"] == 0
    assert row[0]["llm_call"]["provider"] == "anthropic"


def test_evaluate_captures_literal_prompt_in_audit(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """Phase 8.3: the audit records the literal prompt under llm_call.prompt."""
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _llm_clean_response()
    reasoning = "Mid-range water_damage settlement; damage scope supports the value."
    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(reasoning),
        retrieved_chunks=_retrieved_chunks(),
    )

    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    prompt = row[0]["llm_call"]["prompt"]
    assert isinstance(prompt["system"], str) and prompt["system"]
    # The adjuster's reasoning was substituted into the user prompt.
    assert reasoning in prompt["user"]
    assert "{adjuster_reasoning}" not in prompt["user"]
    assert prompt["user"] == mock_provider.calls[0].user


# --------------------------------------------------------------------------- #
# Rule engine — each PII detector + the citation detector + the bias detector.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "leak_text",
    [
        "Claimant SSN on file: 123-45-6789.",
        "Reached claimant at contact@example.com for confirmation.",
        "Verified the policy holder at +1 (212) 555-0188 on the phone.",
        "Charged the deductible to card 4111 1111 1111 1111.",
    ],
    ids=["ssn", "email", "phone_us", "credit_card_like"],
)
def test_pii_patterns_each_kind_fires(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
    leak_text: str,
) -> None:
    """Each PII regex produces a rule-source flag — `passed=False`."""
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _llm_clean_response()

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(leak_text),
        retrieved_chunks=_retrieved_chunks(),
    )
    assert result.output.passed is False
    assert any(flag.kind == "pii" and flag.source == "rule" for flag in result.output.flags)


def test_hallucinated_citation_fires(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A citation to an endorsement absent from the retrieved chunks flags."""
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _llm_clean_response()

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(
            "Settlement supported by Endorsement A2025-CB extending coverage."
        ),
        retrieved_chunks=_retrieved_chunks(),
    )
    assert result.output.passed is False
    flagged = [f for f in result.output.flags if f.kind == "hallucinated_citation"]
    assert flagged
    assert any("A2025-CB" in f.detail for f in flagged)


def test_legitimate_citation_does_not_flag(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """Citing a section that does appear in the retrieved chunks passes."""
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _llm_clean_response()

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(
            "Aligned with the Sub-Limits Debris removal cap from the policy."
        ),
        retrieved_chunks=_retrieved_chunks(),
    )
    # No hallucinated_citation flag from the rule engine.
    assert not any(
        f.kind == "hallucinated_citation" and f.source == "rule"
        for f in result.output.flags
    )


def test_protected_characteristic_term_flags(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """A bias term in the reasoning produces a bias flag."""
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _llm_clean_response()

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(
            "Settlement weighted by the claimant's age and risk profile."
        ),
        retrieved_chunks=_retrieved_chunks(),
    )
    assert result.output.passed is False
    assert any(
        f.kind == "bias" and f.source == "rule" for f in result.output.flags
    )


# --------------------------------------------------------------------------- #
# LLM flags merge with rule flags.
# --------------------------------------------------------------------------- #


def test_llm_flags_are_merged_with_rule_flags(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """LLM-source flags accumulate alongside rule-source ones."""
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = json.dumps(
        {
            "flags": [
                {
                    "kind": "bias",
                    "detail": "implicit framing around claimant size",
                },
            ],
            "summary": "Subtle framing concern found.",
        }
    )

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(
            "Mid-range water_damage settlement; damage scope supports the value."
        ),
        retrieved_chunks=_retrieved_chunks(),
    )
    sources = {flag.source for flag in result.output.flags}
    assert "llm" in sources
    assert result.output.passed is False


# --------------------------------------------------------------------------- #
# Defensive guards
# --------------------------------------------------------------------------- #


def test_non_json_llm_response_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = "not json"

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        guardrail.evaluate(
            claim_id,
            uuid4(),
            adjuster_result=_adjuster_result("clean reasoning"),
            retrieved_chunks=_retrieved_chunks(),
        )
    assert "no `{...}` block" in str(exc_info.value)


def test_missing_flags_key_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = json.dumps({"summary": "ok"})

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        guardrail.evaluate(
            claim_id,
            uuid4(),
            adjuster_result=_adjuster_result("clean reasoning"),
            retrieved_chunks=_retrieved_chunks(),
        )
    assert "missing required key 'flags'" in str(exc_info.value)


def test_flags_not_a_list_raises(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = json.dumps({"flags": "oops", "summary": "ok"})

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(ValueError) as exc_info:
        guardrail.evaluate(
            claim_id,
            uuid4(),
            adjuster_result=_adjuster_result("clean reasoning"),
            retrieved_chunks=_retrieved_chunks(),
        )
    assert "'flags' must be a list" in str(exc_info.value)


def test_empty_retrieved_chunks_raises_in_rule_engine() -> None:
    """Rule engine refuses an empty retrieved-chunks list — citation check can't run."""
    engine = GuardrailRuleEngine.with_defaults()
    with pytest.raises(ValueError) as exc_info:
        engine.scan(reasoning="clean text", retrieved_chunks=[])
    assert "retrieved_chunks must be non-empty" in str(exc_info.value)


def test_fail_closed_model_validator() -> None:
    """`GuardrailOutput` raises when flags exist but passed=True."""
    from backend.app.agents.guardrail_models import GuardrailFlag

    with pytest.raises(ValidationError) as exc_info:
        GuardrailOutput(
            passed=True,
            flags=[GuardrailFlag(kind="pii", detail="ssn-like match", source="rule")],
            summary="oops",
        )
    assert "fail-closed contract violated" in str(exc_info.value)


def test_provider_raises_writes_audit_and_propagates(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.raise_on_call = LLMProviderError("AnthropicProvider: rate limited")

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    with pytest.raises(LLMProviderError):
        guardrail.evaluate(
            claim_id,
            uuid4(),
            adjuster_result=_adjuster_result("clean reasoning"),
            retrieved_chunks=_retrieved_chunks(),
        )
    with clean_db.cursor() as cur:
        cur.execute("SELECT payload FROM audit_log WHERE claim_id = %s", (claim_id,))
        row = cur.fetchone()
    assert row is not None
    assert row[0]["error"]["type"] == "LLMProviderError"


# --------------------------------------------------------------------------- #
# Real-call test — gated.
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_E2E_TESTS") != "1"
    or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Set RUN_LLM_E2E_TESTS=1 with ANTHROPIC_API_KEY to exercise the live API.",
)
def test_guardrail_real_call(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
) -> None:
    """End-to-end against the live Anthropic Haiku API. Opt-in."""
    from backend.app.llm import get_provider
    from backend.app.llm.factory import clear_provider_cache

    clear_provider_cache()
    provider = get_provider(db_settings, "anthropic")
    claim_id = _insert_claim_stub(clean_db)

    guardrail = _build_guardrail(
        conn=clean_db,
        provider=provider,  # type: ignore[arg-type]
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(
            "Mid-range water_damage settlement; damage scope supports the value."
        ),
        retrieved_chunks=_retrieved_chunks(),
    )
    # The live model can return clean or with subtle LLM-side flags;
    # the only invariant we assert is the typed return shape.
    assert isinstance(result, GuardrailResult)
    assert isinstance(result.output, GuardrailOutput)


# --------------------------------------------------------------------------- #
# Phase 8 — market vocabulary is not a hallucinated citation (regression).
# --------------------------------------------------------------------------- #


def test_market_vocabulary_is_not_flagged(
    clean_db: psycopg.Connection,
    db_settings: Settings,
    prompt_loader: PromptLoader,
    mock_provider: MockProvider,
) -> None:
    """The Adjuster's market-data vocabulary must not trip the citation check.

    'market band' / 'mid-range' / 'within range' / 'lookup table' carry none of
    the citation keywords (endorsement, clause, section, …), so the deterministic
    rule engine raises no hallucinated_citation flag; with a benign LLM response
    the combined verdict passes.
    """
    claim_id = _insert_claim_stub(clean_db)
    mock_provider.response_text = _llm_clean_response()
    guardrail = _build_guardrail(
        conn=clean_db,
        provider=mock_provider,
        db_settings=db_settings,
        prompt_loader=prompt_loader,
    )
    result = guardrail.evaluate(
        claim_id,
        uuid4(),
        adjuster_result=_adjuster_result(
            "Settlement of $85,000 sits within the market band and mid-range of "
            "the market-data lookup table for this loss; the value is within range."
        ),
        retrieved_chunks=_retrieved_chunks(),
    )
    assert result.output.passed is True
    assert not any(f.kind == "hallucinated_citation" for f in result.output.flags)
