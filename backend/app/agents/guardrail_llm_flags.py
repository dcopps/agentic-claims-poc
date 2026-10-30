"""
Code-side verification of the Guardrail LLM check's citation flags (Phase 9.2.2).

Why this exists. Under a pinned model id the LLM check flagged three different
pieces of the Adjuster's own vocabulary as hallucinated policy citations on three
surfaces ("market range", "supply line", "$200,000 ceiling"), each reproducible
3/3 at temperature 0, and prompt wording could not make the verdict stable. The
model keeps its job of *finding* a suspicious reference; it loses the authority to
fail a claim on its own say-so. A `hallucinated_citation` claim counts only when:

  1. it quotes the words it objects to (`quote`),
  2. those words are present in the Adjuster's reasoning, and
  3. the reasoning's own span has the shape of a named provision by the same
     test the deterministic rule engine uses (`GuardrailRuleEngine.citation_pattern`,
     passed in — reused as the oracle, never copied).

A claim that fails is discarded and *recorded*: it lands in the audit payload with
its reason and in the log at INFO. It is never an exception — the exception path
stays reserved for a reply the agent cannot parse at all.

`pii` and `bias` claims are untouched by this check: no quote is required and
none is kept.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.agents._shared import excerpt as _excerpt
from backend.app.agents.guardrail_models import GuardrailFlag, GuardrailFlagKind

_logger = logging.getLogger(__name__)

DiscardReason = Literal["no_quote", "quote_not_in_reasoning", "quote_not_a_provision"]

# Discard log lines carry the quote so a refusal can be read without the audit
# row, but a model that "quotes" a paragraph must not flood the log.
_LOG_QUOTE_CHARS = 200

# Curly quote glyphs the model (and the Adjuster) may use interchangeably with
# the straight ones. Both sides of the containment test are mapped through this
# table so a straightened quote still locates a curly original and vice versa.
_QUOTE_GLYPHS = str.maketrans({"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"'})
_WRAPPING_QUOTE_CHARS = "'\""


class LLMFlagClaim(BaseModel):
    """
    What the model asserted, before code has checked it.

    The parse step validates each item of the model's `flags` array into this
    shape; a claim never leaves the agent — it is either promoted to a
    `GuardrailFlag` by `verify_llm_flags` or recorded as a `DiscardedLLMFlag`.
    `quote` is optional at the schema level so a missing quote is a *discard
    reason*, not a parse failure: the model's omission is itself evidence worth
    recording.
    """

    model_config = ConfigDict(extra="forbid")

    kind: GuardrailFlagKind
    detail: str = Field(min_length=1, max_length=300)
    quote: str | None = None


class DiscardedLLMFlag(BaseModel):
    """A claim the code refused to count, with the reason. Audit and log only."""

    model_config = ConfigDict(extra="forbid")

    kind: GuardrailFlagKind
    detail: str
    quote: str | None
    reason: DiscardReason


class CountedLLMFlag(BaseModel):
    """A promoted claim with the evidence that promoted it. Audit only."""

    model_config = ConfigDict(extra="forbid")

    kind: GuardrailFlagKind
    detail: str
    # The reasoning's own span for a citation flag; `None` for `pii` / `bias`,
    # which carry no quote whatever the model sent.
    quote: str | None


@dataclass(frozen=True)
class LLMCheckOutcome:
    """The verified result of one LLM check: what counts, what was refused."""

    counted: list[GuardrailFlag]
    counted_evidence: list[CountedLLMFlag]
    discarded: list[DiscardedLLMFlag]


def verify_llm_flags(
    claims: list[LLMFlagClaim],
    *,
    reasoning: str,
    citation_pattern: re.Pattern[str],
) -> LLMCheckOutcome:
    """
    Promote each claim to a `GuardrailFlag` or record why it was refused.

    Only `hallucinated_citation` claims are subject to the three checks; every
    other kind is promoted as-is. A refused claim is appended to `discarded` and
    logged, and processing continues with the next claim — one bad claim must not
    hide a good one.
    """
    counted: list[GuardrailFlag] = []
    evidence: list[CountedLLMFlag] = []
    discarded: list[DiscardedLLMFlag] = []
    for claim in claims:
        if claim.kind != "hallucinated_citation":
            counted.append(_promote(claim))
            evidence.append(CountedLLMFlag(kind=claim.kind, detail=claim.detail, quote=None))
            continue
        span, reason = _verify_citation_claim(claim, reasoning, citation_pattern)
        if reason is not None:
            discarded.append(_discard(claim, reason))
            continue
        counted.append(_promote(claim))
        evidence.append(CountedLLMFlag(kind=claim.kind, detail=claim.detail, quote=span))
    return LLMCheckOutcome(counted=counted, counted_evidence=evidence, discarded=discarded)


def _verify_citation_claim(
    claim: LLMFlagClaim, reasoning: str, citation_pattern: re.Pattern[str]
) -> tuple[str | None, DiscardReason | None]:
    """
    Sanitise → validate → abort, in order; the first failing check names the reason.

    Returns `(span, None)` on success, where `span` is the reasoning's own text
    that the quote located, or `(None, reason)` on refusal.
    """
    quote = _sanitise_quote(claim.quote)
    # A claim with nothing to check is refused before anything else: the model
    # was told the quote is required, and its absence is the finding.
    if not quote:
        return None, "no_quote"
    span = _locate_quote(quote, reasoning)
    # Not in the reasoning means the model paraphrased or invented the words it
    # objects to; there is nothing in the Adjuster's text to hold against it.
    if span is None:
        return None, "quote_not_in_reasoning"
    # The shape test runs on the reasoning's span, not the model's string, so a
    # claim cannot gain a capital letter or a keyword the text does not have.
    if citation_pattern.search(span) is None:
        return None, "quote_not_a_provision"
    return span, None


def _sanitise_quote(quote: str | None) -> str:
    """Strip whitespace, one layer of wrapping quotes, then straighten glyphs."""
    if quote is None:
        return ""
    text = quote.strip().translate(_QUOTE_GLYPHS)
    # The model habitually writes `'supply line'`; the wrapping is its
    # punctuation, not the Adjuster's words.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in _WRAPPING_QUOTE_CHARS:
        text = text[1:-1].strip()
    return text


def _locate_quote(quote: str, reasoning: str) -> str | None:
    """
    Find the quote in the reasoning and return the reasoning's own span.

    Tolerances, each a deliberate choice: case-insensitive, any whitespace run
    (including a line break) matches any other, and curly/straight quote glyphs
    are equivalent. Nothing else is folded — every tolerance is a way for a
    non-verbatim quote to pass, so the list stays short.
    """
    tokens = quote.split()
    pattern = re.compile(r"\s+".join(re.escape(token) for token in tokens), re.IGNORECASE)
    match = pattern.search(reasoning.translate(_QUOTE_GLYPHS))
    return match.group(0) if match is not None else None


def _promote(claim: LLMFlagClaim) -> GuardrailFlag:
    # `source` is stamped here, at promotion, so the merged flag list still
    # distinguishes detector provenance exactly as before this phase.
    return GuardrailFlag(kind=claim.kind, detail=claim.detail, source="llm")


def _discard(claim: LLMFlagClaim, reason: DiscardReason) -> DiscardedLLMFlag:
    _logger.info(
        "Guardrail discarded an LLM hallucinated_citation flag: reason=%s quote=%r detail=%r",
        reason,
        _excerpt(claim.quote, _LOG_QUOTE_CHARS) if claim.quote is not None else None,
        claim.detail,
    )
    return DiscardedLLMFlag(
        kind=claim.kind, detail=claim.detail, quote=claim.quote, reason=reason
    )
