"""
Tests for `backend.app.agents.guardrail_llm_flags.verify_llm_flags` (Phase 9.2.2).

No database, no network: the verifier is a pure function of the model's claims,
the Adjuster's reasoning and the rule engine's citation pattern. Each discard
reason has a test that triggers it and asserts the reason string; the five
phrases that escalated real runs between 26 and 30 October 2026 are the
parametrised `quote_not_a_provision` cases, so this file is the deterministic
counterpart of the live replay corpus.
"""

from __future__ import annotations

import logging
import re

import pytest

from backend.app.agents.guardrail_llm_flags import (
    DiscardReason,
    LLMCheckOutcome,
    LLMFlagClaim,
    verify_llm_flags,
)
from backend.app.agents.guardrail_rules import GuardrailRuleEngine

_PATTERN = GuardrailRuleEngine.with_defaults().citation_pattern

_CORAL_BAY_REASONING = (
    "Severe storm produced wind damage to the headquarters roof followed by "
    "consequential internal water ingress. The recommended settlement assumes "
    "coverage extended under Endorsement Coastal Surge Rider, which the claimant "
    "cited but which does not appear in the carrier's retrieved policy text."
)

_HARBORLINE_REASONING = (
    "The claim describes a sudden burst supply line causing warehouse flooding. "
    "The claimant's claimed amount of $85,000 aligns with the midpoint of the "
    "moderate-severity market range and the plumbing contractor verified the "
    "sudden failure. A settlement of $82,500 reflects the moderate but material "
    "scope of the loss while remaining conservative relative to the $200,000 ceiling, "
    "positioning it squarely within the moderate-severity band of the market band."
)


def _citation(
    quote: str | None, detail: str = "names a provision absent from the chunks"
) -> LLMFlagClaim:
    return LLMFlagClaim(kind="hallucinated_citation", detail=detail, quote=quote)


def _verify(claims: list[LLMFlagClaim], reasoning: str = _CORAL_BAY_REASONING) -> LLMCheckOutcome:
    return verify_llm_flags(claims, reasoning=reasoning, citation_pattern=_PATTERN)


def _only_reason(outcome: LLMCheckOutcome) -> DiscardReason:
    assert outcome.counted == [], outcome
    assert len(outcome.discarded) == 1, outcome
    return outcome.discarded[0].reason


# --------------------------------------------------------------------------- #
# Discard reasons
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("quote", [None, "", "   ", "''", '""'])
def test_citation_without_quote_is_discarded(quote: str | None) -> None:
    outcome = _verify([_citation(quote)])
    assert _only_reason(outcome) == "no_quote"
    assert outcome.discarded[0].quote == quote


def test_quote_absent_from_reasoning_is_discarded() -> None:
    outcome = _verify([_citation("Endorsement Harbour Flood Rider")])
    assert _only_reason(outcome) == "quote_not_in_reasoning"


@pytest.mark.parametrize(
    "quote",
    ["market range", "moderate-severity band", "sudden failure", "supply line", "$200,000 ceiling"],
)
def test_quote_without_provision_shape_is_discarded(quote: str) -> None:
    """The five phrases that escalated real runs; none carries a provision keyword."""
    outcome = _verify([_citation(quote)], reasoning=_HARBORLINE_REASONING)
    assert _only_reason(outcome) == "quote_not_a_provision"


def test_first_failing_check_names_the_reason() -> None:
    """A quote that is both absent and shapeless reports the absence: order is the contract."""
    outcome = _verify([_citation("market range")])
    assert _only_reason(outcome) == "quote_not_in_reasoning"


# --------------------------------------------------------------------------- #
# Promotion
# --------------------------------------------------------------------------- #


def test_well_formed_quote_is_counted() -> None:
    outcome = _verify([_citation("Endorsement Coastal Surge Rider")])
    assert outcome.discarded == []
    assert [(f.kind, f.source) for f in outcome.counted] == [("hallucinated_citation", "llm")]
    assert outcome.counted_evidence[0].quote == "Endorsement Coastal Surge Rider"


def test_quote_with_surrounding_words_is_counted() -> None:
    """`search`, not `fullmatch`: a quote may carry a few words around the provision."""
    outcome = _verify([_citation("coverage extended under Endorsement Coastal Surge Rider, which")])
    assert outcome.discarded == []
    assert len(outcome.counted) == 1


@pytest.mark.parametrize(
    ("quote", "reasoning"),
    [
        ("'Endorsement Coastal Surge Rider'", _CORAL_BAY_REASONING),
        ("“Endorsement Coastal Surge Rider”", _CORAL_BAY_REASONING),
        ("endorsement coastal surge rider", _CORAL_BAY_REASONING),
        ("Endorsement   Coastal\nSurge Rider", _CORAL_BAY_REASONING),
        (
            "Endorsement Coastal Surge Rider",
            _CORAL_BAY_REASONING.replace("Surge Rider", "Surge\n Rider"),
        ),
        (
            "the claimant's Endorsement Coastal",
            _CORAL_BAY_REASONING.replace(
                "the claimant cited", "the claimant’s Endorsement Coastal"
            ),
        ),
    ],
    ids=[
        "wrapping-straight",
        "wrapping-curly",
        "case",
        "whitespace-in-quote",
        "line-break-in-reasoning",
        "curly-apostrophe",
    ],
)
def test_containment_normalisation(quote: str, reasoning: str) -> None:
    outcome = _verify([_citation(quote)], reasoning=reasoning)
    assert outcome.discarded == [], outcome.discarded
    assert len(outcome.counted) == 1


def test_shape_is_judged_on_the_reasoning_span() -> None:
    """Capitalising a lower-case phrase cannot manufacture the capital the regex needs."""
    reasoning = _CORAL_BAY_REASONING.replace(
        "Endorsement Coastal Surge Rider", "endorsement coastal surge rider"
    )
    outcome = _verify([_citation("Endorsement Coastal Surge Rider")], reasoning=reasoning)
    assert _only_reason(outcome) == "quote_not_a_provision"
    assert outcome.discarded[0].quote == "Endorsement Coastal Surge Rider"


def test_counted_evidence_is_the_reasoning_span_not_the_models_string() -> None:
    outcome = _verify([_citation("'endorsement coastal surge rider'")])
    assert outcome.counted_evidence[0].quote == "Endorsement Coastal Surge Rider"


# --------------------------------------------------------------------------- #
# Other kinds, mixed lists, the oracle
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", ["pii", "bias"])
@pytest.mark.parametrize("quote", [None, "something the model quoted anyway"])
def test_pii_and_bias_pass_through_untouched(kind: str, quote: str | None) -> None:
    claim = LLMFlagClaim(kind=kind, detail="finding", quote=quote)  # type: ignore[arg-type]
    outcome = _verify([claim])
    assert outcome.discarded == []
    assert [(f.kind, f.detail, f.source) for f in outcome.counted] == [(kind, "finding", "llm")]
    # The quote is dropped, not kept: these kinds carry no evidence field.
    assert outcome.counted_evidence[0].quote is None


def test_one_refused_claim_does_not_hide_a_good_one() -> None:
    outcome = _verify(
        [
            _citation("market range"),
            LLMFlagClaim(kind="bias", detail="references claimant's age"),
            _citation("Endorsement Coastal Surge Rider"),
        ]
    )
    assert [f.kind for f in outcome.counted] == ["bias", "hallucinated_citation"]
    assert [d.reason for d in outcome.discarded] == ["quote_not_in_reasoning"]


def test_custom_citation_pattern_is_honoured() -> None:
    """The oracle is the argument, not the module constant."""
    rider_only = re.compile(r"Rider\s+[A-Z][A-Za-z ]+")
    outcome = verify_llm_flags(
        [_citation("Endorsement Coastal Surge Rider")],
        reasoning=_CORAL_BAY_REASONING,
        citation_pattern=rider_only,
    )
    assert _only_reason(outcome) == "quote_not_a_provision"


def test_claim_schema_forbids_unknown_keys_and_wrong_quote_type() -> None:
    with pytest.raises(ValueError, match="source"):
        LLMFlagClaim.model_validate({"kind": "bias", "detail": "x", "source": "llm"})
    with pytest.raises(ValueError, match="quote"):
        LLMFlagClaim.model_validate({"kind": "hallucinated_citation", "detail": "x", "quote": 7})


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #


def test_discard_is_logged_at_info_with_truncated_quote(caplog: pytest.LogCaptureFixture) -> None:
    long_quote = "x" * 400
    with caplog.at_level(logging.INFO, logger="backend.app.agents.guardrail_llm_flags"):
        _verify([_citation(long_quote, detail="a very long quote")])
    records = [
        r for r in caplog.records if "discarded an LLM hallucinated_citation" in r.getMessage()
    ]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "reason=quote_not_in_reasoning" in message
    assert "detail='a very long quote'" in message
    assert "x" * 200 in message
    assert "x" * 201 not in message
    assert "truncated, full length=400" in message
