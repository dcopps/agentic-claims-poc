"""
Golden-text tests for the Validator's externalised prompts.

These guard against accidental edits to `prompts/system/validator.md` or
`prompts/user/validator_template.md`. The system prompt's wording is
load-bearing — it tells the model the JSON output format and the
citation discipline — so a silent edit should fail the suite.

Tests are content-shape assertions, not full-text diffs, so legitimate
wording tweaks remain easy while structural drift (a missing field
name, a deleted constraint) fails loudly.
"""

from __future__ import annotations

from backend.app.prompts import PromptLoader


def test_system_prompt_mentions_each_locked_output_field(
    prompt_loader: PromptLoader,
) -> None:
    system = prompt_loader.system("validator")
    for field in (
        "covered",
        "confidence",
        "reasoning",
        "policy_basis",
        "cited_chunks",
    ):
        assert field in system, f"system prompt missing {field!r}"


def test_system_prompt_repeats_anti_hallucination_rule(
    prompt_loader: PromptLoader,
) -> None:
    system = prompt_loader.system("validator")
    lowered = system.lower()
    assert "must be one of the `chunk_id` values" in lowered
    assert "hard error" in lowered


def test_user_template_substitutes_both_placeholders(
    prompt_loader: PromptLoader,
) -> None:
    rendered = prompt_loader.user(
        "validator_template",
        claim_narrative="<<NARRATIVE>>",
        retrieved_chunks="<<CHUNKS>>",
    )
    assert "<<NARRATIVE>>" in rendered
    assert "<<CHUNKS>>" in rendered
    assert "{claim_narrative}" not in rendered
    assert "{retrieved_chunks}" not in rendered
