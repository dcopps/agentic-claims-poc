"""
Tests for provider wiring through the real factory (Phase 8.6).

These build the default orchestrator and a variant orchestrator exactly as the
API does — real `get_provider`, real SDK client construction — and inspect which
provider each agent holds and which model it will request. No network call
happens: constructing an SDK client does not contact the vendor. The embedder is
stubbed to avoid the SentenceTransformer cold-load, and keys are obviously fake
placeholders set on a deep copy, never read from the environment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import cast

import numpy as np
import pytest
from pydantic import SecretStr

from backend.app.agents.adjuster import Adjuster
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.validator import Validator
from backend.app.escalation import EscalationPolicy
from backend.app.llm.anthropic_provider import AnthropicProvider
from backend.app.llm.factory import clear_provider_cache
from backend.app.llm.mistral_provider import MistralProvider
from backend.app.orchestrator.pipeline import PipelineOrchestrator
from backend.app.orchestrator.variant_factory import build_variant_orchestrator
from backend.app.orchestrator.variant_registry import VariantRegistry
from backend.settings import Settings

_HAIKU = "claude-haiku-4-5-20251001"
_MISTRAL_PIN = "mistral-large-2512"
_PLACEHOLDER_KEY = "placeholder-not-a-real-key"


@pytest.fixture(autouse=True)
def _isolated_provider_cache() -> Iterator[None]:
    # The cache keys on id(settings); clearing on both sides keeps a recycled id
    # from handing one test's provider to another.
    clear_provider_cache()
    yield
    clear_provider_cache()


@pytest.fixture(autouse=True)
def _stub_default_embedder(
    monkeypatch: pytest.MonkeyPatch, stub_embedder: Callable[[str], np.ndarray]
) -> None:
    def factory(_settings: Settings) -> Callable[[str], np.ndarray]:
        return stub_embedder

    monkeypatch.setattr("backend.app.agents.validator.default_embedder", factory)
    monkeypatch.setattr("backend.app.orchestrator.variant_factory.default_embedder", factory)


def _settings_with_keys(db_settings: Settings, *, mistral_key: bool) -> Settings:
    settings = db_settings.model_copy(deep=True)
    settings.llm.anthropic.api_key = SecretStr(_PLACEHOLDER_KEY)
    settings.llm.mistral.api_key = SecretStr(_PLACEHOLDER_KEY) if mistral_key else None
    return settings


def _policy(settings: Settings) -> EscalationPolicy:
    return EscalationPolicy.load_from_yaml(settings.escalation.policy_path)


def _registry(settings: Settings) -> VariantRegistry:
    return VariantRegistry.load_from_yaml(settings.pipeline.variants_path)


def _agents(
    orch: PipelineOrchestrator,
) -> tuple[DocParser, Validator, Adjuster, Guardrail]:
    # The orchestrator types its collaborators as Protocols; the real wiring
    # installs the concrete agents, whose private state these tests inspect.
    return (
        cast(DocParser, orch._doc_parser),
        cast(Validator, orch._validator),
        cast(Adjuster, orch._adjuster),
        cast(Guardrail, orch._guardrail),
    )


def test_default_wiring_routes_every_agent_to_anthropic_haiku(db_settings: Settings) -> None:
    settings = _settings_with_keys(db_settings, mistral_key=True)
    doc_parser, validator, adjuster, guardrail = _agents(
        PipelineOrchestrator.with_defaults(settings, policy=_policy(settings))
    )

    assert isinstance(doc_parser._provider, AnthropicProvider)
    assert isinstance(validator._provider, AnthropicProvider)
    assert isinstance(adjuster._provider, AnthropicProvider)
    assert isinstance(guardrail._provider, AnthropicProvider)
    assert validator._settings.llm.model_for("validator") == _HAIKU
    assert adjuster._settings.llm.model_for("adjuster") == _HAIKU


def test_default_wiring_builds_without_a_mistral_key(db_settings: Settings) -> None:
    """
    The wiring discriminator. With no Mistral key, `get_provider(..., "mistral")`
    raises — so this passes only if the default path constructs no Mistral
    provider at all. A default still (even partly) wired to Mistral fails here.
    """
    settings = _settings_with_keys(db_settings, mistral_key=False)
    _, validator, adjuster, _ = _agents(
        PipelineOrchestrator.with_defaults(settings, policy=_policy(settings))
    )
    assert isinstance(validator._provider, AnthropicProvider)
    assert isinstance(adjuster._provider, AnthropicProvider)


def test_v1_mistral_variant_routes_validator_and_adjuster_to_mistral(
    db_settings: Settings,
) -> None:
    settings = _settings_with_keys(db_settings, mistral_key=True)
    doc_parser, validator, adjuster, guardrail = _agents(
        build_variant_orchestrator(
            settings, _policy(settings), _registry(settings), "v1_mistral"
        )
    )

    assert isinstance(validator._provider, MistralProvider)
    assert isinstance(adjuster._provider, MistralProvider)
    assert validator._settings.llm.model_for("validator") == _MISTRAL_PIN
    assert adjuster._settings.llm.model_for("adjuster") == _MISTRAL_PIN
    assert isinstance(doc_parser._provider, AnthropicProvider)
    assert isinstance(guardrail._provider, AnthropicProvider)
    # The shared Settings is untouched by the variant (deep copy).
    assert settings.llm.provider_for("validator") == "anthropic"


def test_strict_variant_runs_the_strict_template_on_haiku(db_settings: Settings) -> None:
    settings = _settings_with_keys(db_settings, mistral_key=False)
    _, validator, _, _ = _agents(
        build_variant_orchestrator(
            settings, _policy(settings), _registry(settings), "v2_strict_validator"
        )
    )

    assert isinstance(validator._provider, AnthropicProvider)
    assert validator._settings.llm.model_for("validator") == _HAIKU
    assert validator._user_template_name == "validator_strict"
