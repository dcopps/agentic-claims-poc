"""
Tests for the per-agent provider selectors and model resolution (Phase 8.6).

The selectors decide which LLM provider each agent is routed to, and
`LLMSettings.model_for` resolves the model from the selected provider block. The
default is all-Anthropic; the Mistral ids stay pinned for the `v1_mistral`
variant. Most tests build `LLMSettings` directly — no database, no keys. The
hierarchy test builds a full `Settings`, so it depends on `db_settings` for a safe
`DATABASE_URL`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.settings import AgentRole, LLMSettings, Settings

_HAIKU = "claude-haiku-4-5-20251001"
_MISTRAL_PIN = "mistral-large-2512"
_AGENTS: tuple[AgentRole, ...] = ("doc_parser", "validator", "adjuster", "guardrail")


# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #


def test_every_agent_selector_defaults_to_anthropic() -> None:
    llm = LLMSettings()
    assert llm.doc_parser_provider == "anthropic"
    assert llm.validator_provider == "anthropic"
    assert llm.adjuster_provider == "anthropic"
    assert llm.guardrail_provider == "anthropic"


def test_anthropic_validator_and_adjuster_models_default_to_haiku() -> None:
    llm = LLMSettings()
    assert llm.anthropic.validator_model == _HAIKU
    assert llm.anthropic.adjuster_model == _HAIKU


def test_mistral_doc_parser_and_guardrail_models_default_to_unset() -> None:
    # Unverified routes carry no guessed default; the pinned ids are unchanged.
    llm = LLMSettings()
    assert llm.mistral.doc_parser_model is None
    assert llm.mistral.guardrail_model is None
    assert llm.mistral.validator_model == _MISTRAL_PIN
    assert llm.mistral.adjuster_model == _MISTRAL_PIN


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def test_model_for_resolves_every_agent_to_haiku_on_defaults() -> None:
    llm = LLMSettings()
    for agent in _AGENTS:
        assert llm.provider_for(agent) == "anthropic"
        assert llm.model_for(agent) == _HAIKU


def test_model_for_follows_a_mistral_selector_to_the_pinned_model() -> None:
    llm = LLMSettings(validator_provider="mistral", adjuster_provider="mistral")
    assert llm.provider_for("validator") == "mistral"
    assert llm.model_for("validator") == _MISTRAL_PIN
    assert llm.model_for("adjuster") == _MISTRAL_PIN
    # Agents whose selector did not change keep the Anthropic model.
    assert llm.model_for("guardrail") == _HAIKU


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #


def test_unknown_provider_selector_is_rejected_at_load() -> None:
    with pytest.raises(ValidationError) as excinfo:
        LLMSettings(validator_provider="openai")  # type: ignore[arg-type]
    message = str(excinfo.value)
    assert "validator_provider" in message
    assert "'anthropic' or 'mistral'" in message
    assert "openai" in message


def test_mistral_selector_without_a_mistral_model_is_rejected_at_load() -> None:
    with pytest.raises(ValidationError) as excinfo:
        LLMSettings(doc_parser_provider="mistral")
    message = str(excinfo.value)
    assert "llm.doc_parser_provider is 'mistral'" in message
    assert "llm.mistral.doc_parser_model is not set" in message


def test_model_for_rejects_an_unknown_agent_name() -> None:
    with pytest.raises(ValueError) as excinfo:
        LLMSettings().model_for("orchestrator")  # type: ignore[arg-type]
    message = str(excinfo.value)
    assert "agent must be one of" in message
    assert "'orchestrator'" in message


def test_model_for_rechecks_a_copy_mutated_without_validation() -> None:
    # A variant deep-copies and assigns without re-validation; the call-time
    # check is what stops an unresolvable selector reaching a provider.
    llm = LLMSettings().model_copy(deep=True)
    llm.guardrail_provider = "mistral"
    with pytest.raises(ValueError) as excinfo:
        llm.model_for("guardrail")
    assert "llm.mistral.guardrail_model is not set" in str(excinfo.value)


def test_provider_for_rechecks_an_unknown_value_on_a_mutated_copy() -> None:
    llm = LLMSettings().model_copy(deep=True)
    llm.adjuster_provider = "openai"  # type: ignore[assignment]
    with pytest.raises(ValueError) as excinfo:
        llm.provider_for("adjuster")
    message = str(excinfo.value)
    assert "llm.adjuster_provider must be one of" in message
    assert "'openai'" in message


# --------------------------------------------------------------------------- #
# Settings hierarchy
# --------------------------------------------------------------------------- #


def test_nested_env_var_flips_an_agent_to_mistral(
    db_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented no-deploy switch: an env var outranks the default."""
    del db_settings  # requested only so DATABASE_URL points at the safe test DB
    monkeypatch.setenv("LLM__VALIDATOR_PROVIDER", "mistral")
    settings = Settings()
    assert settings.llm.provider_for("validator") == "mistral"
    assert settings.llm.model_for("validator") == _MISTRAL_PIN
    assert settings.llm.provider_for("adjuster") == "anthropic"
