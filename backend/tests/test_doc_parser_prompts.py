"""Golden-shape tests for the Doc-Parser externalised prompts."""

from __future__ import annotations

from backend.app.prompts import PromptLoader


def test_system_prompt_declares_summary_role_and_output_shape() -> None:
    """The system prompt names the summariser role and the plain-prose contract.

    Phase 8.2: Doc-Parser no longer extracts structured JSON — those fields come
    from the claim record. The prompt asks only for a bounded plain-prose summary,
    so it must declare the summariser role and explicitly forbid JSON.
    """
    PromptLoader.clear_cache()
    loader = PromptLoader()
    text = loader.system("doc_parser").lower()
    assert "narrative summariser" in text
    # Plain prose only — the prompt must reject JSON and prose wrappers, and state
    # the 500-character cap that mirrors the DocParserOutput bound.
    assert "no json" in text
    assert "no preamble" in text
    assert "500" in text


def test_user_template_has_single_narrative_placeholder() -> None:
    """The user template renders only `{claim_narrative}` from the loader."""
    PromptLoader.clear_cache()
    loader = PromptLoader()
    formatted = loader.user(
        "doc_parser_template",
        claim_narrative="HELLO_NARRATIVE_TOKEN",
    )
    assert "HELLO_NARRATIVE_TOKEN" in formatted
    # No leftover placeholder syntax.
    assert "{claim_narrative}" not in formatted
