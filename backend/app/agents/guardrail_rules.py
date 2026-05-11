"""
Guardrail deterministic rule engine.

The rule engine is the floor — a small, explicit set of regex and
keyword checks that catch obvious failure modes regardless of what
the LLM check returns. Phase 3 commits to *named, greppable* patterns
rather than a probabilistic detector so the behaviour is
reproducible, testable, and reviewable.

Three checks:

  - **PII** — SSN, email, US phone, credit-card-like digit runs.
    Detected by anchored regex on the Adjuster's reasoning field.
  - **Hallucinated policy citation** — phrases of the form
    `(endorsement|sub-limit|clause|provision|section|exclusion) <Name>`
    that do not appear (case-insensitively, by substring) in the
    section names or content of the retrieved policy chunks.
  - **Bias / protected characteristics** — substring hits against a
    small, explicit set of protected-characteristic terms.

The engine is stateless beyond construction. A rule engine instance
holds the compiled patterns; tests can construct it directly with a
custom pattern set to exercise edge cases.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from backend.app.agents.guardrail_models import GuardrailFlag
from backend.app.agents.validator_models import RetrievedChunk

# PII patterns. Each entry is `(pattern_name, compiled_regex)`. The
# name lands in the flag detail so an operator can grep for the
# specific class of leak without re-running the rule. The patterns
# are deliberately conservative — false positives lean toward
# escalation, which is the safe direction for a guardrail.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        "phone_us",
        re.compile(
            r"\b\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"
        ),
    ),
    # 13–19 consecutive digits with optional spaces/dashes — covers
    # most consumer card formats without trying to validate Luhn.
    (
        "credit_card_like",
        re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    ),
)

# Citation-candidate regex. The keyword group is what makes the
# candidate look like a policy reference; the name group is the
# string we then check against the retrieved chunks' allow-set.
_CITATION_CANDIDATE_RE = re.compile(
    r"(?P<kind>endorsement|sub-?limit|clause|provision|section|exclusion)"
    r"\s+(?P<name>[A-Z][A-Za-z0-9 \-./]{1,60})",
    re.IGNORECASE,
)

# Protected-characteristic terms. Matched with word boundaries
# (case-insensitive) so short terms like "age" do not fire on
# substrings such as "damage" or "manager" — the substring approach
# was the obvious choice and the wrong one. Storing the precompiled
# patterns alongside their human-readable name lets the audit row
# carry the term that matched.
_PROTECTED_TERMS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("race", re.compile(r"\brace\b", re.IGNORECASE)),
    ("ethnicity", re.compile(r"\bethnicity\b", re.IGNORECASE)),
    ("religion", re.compile(r"\breligion\b", re.IGNORECASE)),
    ("gender", re.compile(r"\bgender\b", re.IGNORECASE)),
    (
        "sexual orientation",
        re.compile(r"\bsexual orientation\b", re.IGNORECASE),
    ),
    ("disability", re.compile(r"\bdisability\b", re.IGNORECASE)),
    ("age", re.compile(r"\bage\b", re.IGNORECASE)),
)


@dataclass
class GuardrailRuleEngine:
    """
    Stateless detector — compile once, scan many.

    Constructor accepts optional pattern sets so a test can pin a
    smaller or larger surface. Production wiring uses the
    module-level defaults via `GuardrailRuleEngine.with_defaults()`.
    """

    pii_patterns: tuple[tuple[str, re.Pattern[str]], ...] = field(
        default_factory=lambda: _PII_PATTERNS
    )
    citation_pattern: re.Pattern[str] = field(
        default_factory=lambda: _CITATION_CANDIDATE_RE
    )
    protected_terms: tuple[tuple[str, re.Pattern[str]], ...] = field(
        default_factory=lambda: _PROTECTED_TERMS
    )

    @classmethod
    def with_defaults(cls) -> GuardrailRuleEngine:
        """Construct the production rule engine. Wiring helper."""
        return cls()

    def scan(
        self,
        *,
        reasoning: str,
        retrieved_chunks: Iterable[RetrievedChunk],
    ) -> list[GuardrailFlag]:
        """
        Run every detector against `reasoning` and return the
        accumulated flag list. Empty list means clean.

        Defensive ordering:
          1. Sanitise — strip the reasoning; an empty reasoning
             is a structural error caught at the agent boundary,
             not here.
          2. Validate — both inputs must be non-empty for the
             checks to be meaningful. The retrieved-chunks
             allow-set is built up-front so each citation
             candidate can be tested against it cheaply.
          3. Abort — `ValueError` with the offending parameter.
          4. Execute — run each pattern set; accumulate flags.
        """
        text = reasoning.strip()
        if not text:
            raise ValueError(
                "GuardrailRuleEngine.scan: reasoning is empty or whitespace"
            )
        chunks = list(retrieved_chunks)
        if not chunks:
            raise ValueError(
                "GuardrailRuleEngine.scan: retrieved_chunks must be non-empty "
                "(the hallucinated-citation check needs an allow-set)"
            )

        flags: list[GuardrailFlag] = []
        flags.extend(self._pii_flags(text))
        flags.extend(self._citation_flags(text, chunks))
        flags.extend(self._bias_flags(text))
        return flags

    # ------------------------------------------------------------------ #
    # Detectors
    # ------------------------------------------------------------------ #

    def _pii_flags(self, text: str) -> list[GuardrailFlag]:
        results: list[GuardrailFlag] = []
        for name, pattern in self.pii_patterns:
            match = pattern.search(text)
            if match is not None:
                results.append(
                    GuardrailFlag(
                        kind="pii",
                        # Mask the matched span so the audit row does
                        # not echo the literal PII back at storage time.
                        detail=f"{name} pattern matched (length={len(match.group(0))})",
                        source="rule",
                    )
                )
        return results

    def _citation_flags(
        self, text: str, chunks: list[RetrievedChunk]
    ) -> list[GuardrailFlag]:
        allow_set = _build_citation_allow_set(chunks)
        results: list[GuardrailFlag] = []
        seen_names: set[str] = set()
        for match in self.citation_pattern.finditer(text):
            name = match.group("name").strip().lower()
            kind = match.group("kind").strip().lower()
            # Deduplicate within one scan so a model that repeats
            # the same phrase three times yields one flag, not three.
            key = f"{kind}|{name}"
            if key in seen_names:
                continue
            seen_names.add(key)
            if _citation_is_in_allow_set(name, allow_set):
                continue
            results.append(
                GuardrailFlag(
                    kind="hallucinated_citation",
                    detail=f"{kind} '{match.group('name').strip()}' not in retrieved chunks",
                    source="rule",
                )
            )
        return results

    def _bias_flags(self, text: str) -> list[GuardrailFlag]:
        results: list[GuardrailFlag] = []
        for name, pattern in self.protected_terms:
            if pattern.search(text) is not None:
                results.append(
                    GuardrailFlag(
                        kind="bias",
                        detail=f"protected-characteristic term '{name}' present in reasoning",
                        source="rule",
                    )
                )
        return results


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #


def _build_citation_allow_set(chunks: list[RetrievedChunk]) -> set[str]:
    """
    Build the case-insensitive allow-set of strings the citation
    detector considers "present in the policy".

    Each retrieved chunk contributes its section name (lowercased)
    plus every non-empty line of its content (lowercased + stripped).
    A citation candidate is "allowed" if its name is a substring of
    any allow-set entry — sub-string rather than equality so phrases
    like "named perils" pass when the chunk's content contains
    "Named Perils Covered".
    """
    allow: set[str] = set()
    for chunk in chunks:
        allow.add(chunk.section.strip().lower())
        for line in chunk.content.splitlines():
            cleaned = line.strip().lower()
            if cleaned:
                allow.add(cleaned)
        # Also add the whole content as one entry so multi-word
        # phrases that span line breaks still match.
        allow.add(chunk.content.strip().lower())
    return allow


def _citation_is_in_allow_set(name: str, allow_set: set[str]) -> bool:
    """Substring containment against every allow-set entry."""
    return any(name in entry for entry in allow_set)
