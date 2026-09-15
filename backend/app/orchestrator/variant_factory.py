"""
Variant factory — builds a `PipelineOrchestrator` configured for a named variant.

Two layers, separated so the interesting logic is testable without keys or the
embedder cold-load:

  - `resolve_variant_settings(settings, spec)` and
    `resolve_validator_template(spec)` — pure: turn a `VariantSpec` into a
    deep-copied `Settings` carrying the overridden provider selectors and model
    ids, plus the Validator's user template. No I/O.
  - `build_variant_orchestrator(...)` — wires real providers and the embedder and
    constructs the four agents from the resolved settings, exactly as the default
    orchestrator is wired from the shared settings.

A variant is therefore a settings overlay, not a separate wiring path: the agents
read their provider selector and model through `Settings.llm.model_for`, so a
`v1_mistral` override of `validator_provider` changes both the provider the
Validator holds and the model it requests. Every agent's audit records the
*actual* provider and model, so the substitution is provable from the audit log.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

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
    ProviderOverride,
    VariantRegistry,
    VariantSpec,
)
from backend.app.prompts import PromptLoader
from backend.settings import AgentRole, LLMSettings, Settings

# The Validator's default user template, used when a variant leaves it unspecified.
_DEFAULT_USER_TEMPLATE = "validator_template"


def resolve_variant_settings(settings: Settings, spec: VariantSpec) -> Settings:
    """
    Return a deep copy of `settings` with the variant's provider/model overrides
    applied. Pure; the shared `Settings` is never mutated.

    A variant with no overrides still gets a copy, so callers never need to
    distinguish the two cases. The copy is not re-validated by Pydantic; the
    `model_for` lookup the agents perform re-checks it on every call.
    """
    resolved = settings.model_copy(deep=True)
    _apply_override(resolved.llm, "validator", spec.validator)
    _apply_override(resolved.llm, "adjuster", spec.adjuster)
    return resolved


def resolve_validator_template(spec: VariantSpec) -> str:
    """The Validator user-template name a variant selects. Pure."""
    override = spec.validator
    if override is None or override.prompt_template is None:
        return _DEFAULT_USER_TEMPLATE
    # A `prompt_template` is named with its `.md` suffix in the variants file; the
    # PromptLoader keys on the bare name.
    return override.prompt_template.removesuffix(".md")


def _apply_override(
    llm: LLMSettings, agent: AgentRole, override: ProviderOverride | None
) -> None:
    """Write one agent's provider selector and/or model id into `llm` in place."""
    if override is None:
        return
    # Provider first: a model override lands in the block of the provider the
    # agent will actually use, which may be the one this override just selected.
    if override.provider is not None:
        _set_provider(llm, agent, override.provider)
    if override.model is not None:
        _set_model(llm, agent, override.model)


def _set_provider(llm: LLMSettings, agent: AgentRole, provider: ProviderName) -> None:
    # Only the two agents with variant slots can reach here; the registry schema
    # has no Doc-Parser or Guardrail slot.
    if agent == "validator":
        llm.validator_provider = provider
    elif agent == "adjuster":
        llm.adjuster_provider = provider
    else:
        raise ValueError(
            f"variant_factory: provider overrides are supported for validator and "
            f"adjuster only; got agent={agent!r}"
        )


def _set_model(llm: LLMSettings, agent: AgentRole, model: str) -> None:
    block = llm.anthropic if llm.provider_for(agent) == "anthropic" else llm.mistral
    if agent == "validator":
        block.validator_model = model
    elif agent == "adjuster":
        block.adjuster_model = model
    else:
        raise ValueError(
            f"variant_factory: model overrides are supported for validator and "
            f"adjuster only; got agent={agent!r}"
        )


def _build_validator(
    *,
    settings: Settings,
    user_template_name: str,
    provider: LLMProvider,
    embedder: Callable[[str], np.ndarray],
    connection_factory: (
        Callable[[], AbstractContextManager[psycopg.Connection]] | None
    ) = None,
) -> Validator:
    """Construct a Validator from already-resolved variant settings and template."""
    return Validator(
        provider=provider,
        prompt_loader=PromptLoader(),
        embedder=embedder,
        settings=settings,
        user_template_name=user_template_name,
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
    API maps that to 404. Variant agents are not cached — they exist for the
    duration of one replay run.

    Providers are looked up on the *shared* `settings`, never the per-run copy:
    the provider cache keys on `id(settings)`, so keying on a fresh copy would add
    an entry per replay, and a garbage-collected copy's reused id could return a
    stale provider. Provider construction reads only keys, logging and pricing,
    none of which a variant overrides — only the selectors are read from the copy.
    """
    spec = registry.resolve(variant_name)
    cfg = resolve_variant_settings(settings, spec)

    def provider(agent: AgentRole) -> LLMProvider:
        return get_provider(settings, cfg.llm.provider_for(agent))

    return PipelineOrchestrator(
        doc_parser=DocParser.with_defaults(cfg, provider=provider("doc_parser")),
        validator=_build_validator(
            settings=cfg,
            user_template_name=resolve_validator_template(spec),
            provider=provider("validator"),
            embedder=default_embedder(settings),
        ),
        adjuster=Adjuster.with_defaults(cfg, provider=provider("adjuster")),
        guardrail=Guardrail.with_defaults(cfg, provider=provider("guardrail")),
        policy=policy,
        settings=settings,
        status_writer=status_writer,
    )
