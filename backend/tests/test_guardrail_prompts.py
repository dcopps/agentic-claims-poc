"""Golden-shape tests for the Guardrail externalised prompts."""

from __future__ import annotations

from backend.app.prompts import PromptLoader


def test_system_prompt_declares_role_and_three_check_kinds() -> None:
    """The system prompt names the role and enumerates the three checks."""
    PromptLoader.clear_cache()
    loader = PromptLoader()
    text = loader.system("guardrail")
    assert "guardrail" in text.lower()
    # All three locked flag kinds appear in the schema.
    for kind in ("pii", "bias", "hallucinated_citation"):
        assert kind in text
    # The "do not duplicate rule-engine flags" rule.
    assert "rule engine" in text.lower()
    assert "duplicate" in text.lower() or "do not re-flag" in text.lower()


def test_user_template_has_required_placeholders() -> None:
    """User template renders the four expected placeholders."""
    PromptLoader.clear_cache()
    loader = PromptLoader()
    formatted = loader.user(
        "guardrail_template",
        adjuster_settlement="85000.00",
        adjuster_reasoning="REASONING_TOKEN",
        retrieved_chunks="CHUNKS_TOKEN",
        rule_flags_already_found="FLAGS_TOKEN",
    )
    assert "REASONING_TOKEN" in formatted
    assert "CHUNKS_TOKEN" in formatted
    assert "FLAGS_TOKEN" in formatted
    assert "85000.00" in formatted
    for placeholder in (
        "{adjuster_settlement}",
        "{adjuster_reasoning}",
        "{retrieved_chunks}",
        "{rule_flags_already_found}",
    ):
        assert placeholder not in formatted


def test_system_prompt_judges_named_citations_and_not_coverage() -> None:
    """
    Phase 9.2.1: the prompt must say coverage is decided upstream and name market-range
    vocabulary as not a citation. Verified to fail on the pre-9.2.1 prompt, which said
    neither — that prompt's market-data note was a closed list that omitted "market range".
    """
    PromptLoader.clear_cache()
    text = PromptLoader().system("guardrail").lower()
    assert "coverage has already been decided" in text
    assert "market range" in text


def test_system_prompt_requires_a_verbatim_quote_on_citation_flags() -> None:
    """
    Phase 9.2.2: the output format carries `quote` on `hallucinated_citation` flags
    and the rules say it is copied verbatim from the reasoning and omitted on `pii`
    and `bias`. Verified to fail on the 9.2.1 prompt, which had no `quote` field.
    """
    PromptLoader.clear_cache()
    text = PromptLoader().system("guardrail")
    assert '"quote"' in text
    rules = text.lower()
    assert "`quote` is required on every `hallucinated_citation` flag" in rules
    assert "verbatim" in rules
    assert "omit `quote` on `pii` and `bias` flags" in rules
