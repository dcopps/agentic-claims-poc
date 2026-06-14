"""
Variant factory — builds a `PipelineOrchestrator` configured for a named variant.

Two layers, separated so the interesting logic is testable without keys or the
embedder cold-load:

  - `resolve_validator_config(spec)` — pure: turns a `VariantSpec` into a
    `ResolvedValidatorConfig` (which provider, which model, which user template).
    No I/O.
  - `build_variant_orchestrator(...)` — wires real providers and the embedder and
    constructs the four agents, applying the resolved override to the Validator
    (the only agent Phase 5 variants touch). The non-overridden agents are built
    from defaults.

A model override is applied by deep-copying `Settings` and swapping the
Validator's model field — the agent then passes that model string to whichever
provider it holds, so a `provider: anthropic` + `model: <haiku>` override runs the
Validator on Anthropic Haiku. The Validator's audit records the *actual* provider
and model, so the substitution is provable from the audit log.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

import numpy as np
import psycopg

from backend.app.agents.adjuster import Adjuster
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.validator import Validator, default_embedder
from backend.app.escalation import EscalationPolicy
from backend.app.llm import get_provider
from backend.app.llm.provider import LLMProvider
from backend.app.orchestrator.pipeline import PipelineOrchestrator, StatusWriter
from backend.app.orchestrator.variant_registry import (
    ProviderName,
    VariantRegistry,
    VariantSpec,
)
from backend.app.prompts import PromptLoader
from backend.settings import Settings

# The Validator's default user template and default provider, used when a variant
# leaves them unspecified.
_DEFAULT_USER_TEMPLATE = "validator_template"
_DEFAULT_VALIDATOR_PROVIDER: ProviderName = "mistral"


@dataclass(frozen=True)
class ResolvedValidatorConfig:
    """The concrete Validator settings a variant resolves to."""

    provider_name: ProviderName
    model: str | None  # None => use the model from Settings
    user_template_name: str


def resolve_validator_config(spec: VariantSpec) -> ResolvedValidatorConfig:
    """Turn a variant spec into a concrete Validator configuration. Pure."""
    override = spec.validator
    if override is None:
        return ResolvedValidatorConfig(
            provider_name=_DEFAULT_VALIDATOR_PROVIDER,
            model=None,
            user_template_name=_DEFAULT_USER_TEMPLATE,
        )
    # A `prompt_template` is named with its `.md` suffix in the variants file; the
    # PromptLoader keys on the bare name.
    template = (
        override.prompt_template.removesuffix(".md")
        if override.prompt_template
        else _DEFAULT_USER_TEMPLATE
    )
    return ResolvedValidatorConfig(
        provider_name=override.provider or _DEFAULT_VALIDATOR_PROVIDER,
        model=override.model,
        user_template_name=template,
    )


def _build_validator(
    *,
    config: ResolvedValidatorConfig,
    settings: Settings,
    provider: LLMProvider,
    embedder: Callable[[str], np.ndarray],
    connection_factory: (
        Callable[[], AbstractContextManager[psycopg.Connection]] | None
    ) = None,
) -> Validator:
    """Construct a Validator for a resolved config, applying a model swap if any."""
    cfg = settings
    if config.model is not None:
        # Deep-copy so the swap is local to this run and never mutates the shared
        # Settings. The Validator reads its model from this field.
        cfg = settings.model_copy(deep=True)
        cfg.llm.mistral.validator_model = config.model
    return Validator(
        provider=provider,
        prompt_loader=PromptLoader(),
        embedder=embedder,
        settings=cfg,
        user_template_name=config.user_template_name,
        connection_factory=connection_factory,
    )


def build_variant_orchestrator(
    settings: Settings,
    policy: EscalationPolicy,
    registry: VariantRegistry,
    variant_name: str,
    *,
    status_writer: StatusWriter | None = None,
) -> PipelineOrchestrator:
    """
    Build an orchestrator configured for `variant_name`.

    Raises `UnknownVariantError` (via the registry) for an unregistered name; the
    API maps that to 404. The Validator is built per the resolved config; the
    other three agents come from defaults. Variant agents are not cached — they
    exist for the duration of one replay run.
    """
    spec = registry.resolve(variant_name)
    config = resolve_validator_config(spec)
    anthropic = get_provider(settings, "anthropic")
    mistral = get_provider(settings, "mistral")
    validator_provider = anthropic if config.provider_name == "anthropic" else mistral
    validator = _build_validator(
        config=config,
        settings=settings,
        provider=validator_provider,
        embedder=default_embedder(settings),
    )
    return PipelineOrchestrator(
        doc_parser=DocParser.with_defaults(settings, provider=anthropic),
        validator=validator,
        adjuster=Adjuster.with_defaults(settings, provider=mistral),
        guardrail=Guardrail.with_defaults(settings, provider=anthropic),
        policy=policy,
        settings=settings,
        status_writer=status_writer,
    )
