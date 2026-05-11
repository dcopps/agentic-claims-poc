"""Golden-shape tests for the Doc-Parser externalised prompts."""

from __future__ import annotations

from backend.app.prompts import PromptLoader


def test_system_prompt_declares_role_and_output_shape() -> None:
    """The system prompt names the role and the required JSON fields."""
    PromptLoader.clear_cache()
    loader = PromptLoader()
    text = loader.system("doc_parser")
    assert "document parser" in text
    # Every locked field name must appear in the schema block.
    for field in (
        "loss_date",
        "jurisdiction",
        "claim_type",
        "claimed_amount",
        "claimant_identifier",
        "narrative_summary",
    ):
        assert field in text
    # The system prompt must reject prose wrappers.
    assert "no preamble" in text.lower()


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
