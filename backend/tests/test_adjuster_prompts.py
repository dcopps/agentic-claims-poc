"""Golden-shape tests for the Adjuster externalised prompts."""

from __future__ import annotations

from backend.app.prompts import PromptLoader


def test_system_prompt_declares_role_and_within_range_constraint() -> None:
    """The system prompt names the role and locks the within-range rule."""
    PromptLoader.clear_cache()
    loader = PromptLoader()
    text = loader.system("adjuster")
    assert "settlement adjuster" in text
    # Within-range language must be unambiguous.
    assert "MUST" in text and "floor" in text and "ceiling" in text
    # The reasoning constraint that the Guardrail will check downstream.
    assert "Never" in text and "policy" in text.lower()
    # JSON output field names.
    for field in ("recommended_settlement", "confidence", "reasoning"):
        assert field in text


def test_user_template_has_all_required_placeholders() -> None:
    """User template renders the five expected placeholders."""
    PromptLoader.clear_cache()
    loader = PromptLoader()
    formatted = loader.user(
        "adjuster_template",
        claim_summary="SUMMARY_TOKEN",
        validator_verdict="VERDICT_TOKEN",
        claim_type="water_damage",
        severity="moderate",
        range_floor="50000",
        range_ceiling="200000",
    )
    assert "SUMMARY_TOKEN" in formatted
    assert "VERDICT_TOKEN" in formatted
    assert "water_damage" in formatted
    assert "moderate" in formatted
    assert "50000" in formatted
    assert "200000" in formatted
    # No leftover placeholder syntax.
    for placeholder in (
        "{claim_summary}",
        "{validator_verdict}",
        "{claim_type}",
        "{severity}",
        "{range_floor}",
        "{range_ceiling}",
    ):
        assert placeholder not in formatted
