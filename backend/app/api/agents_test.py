"""
Agent test bench API — invoke one agent on arbitrary input, out-of-band.

Each endpoint builds the agent (honouring an optional `?variant=`) and calls its
non-audit `probe` method: the agent runs its prompt → LLM → parse path and returns
the typed output plus LLM-call metadata. **No audit entry is written** and no claim
is touched — the test bench is for development and demo exploration, distinct from
production-shaped claim runs. The only side effect is the APILogger record that
`provider.complete` already emits.

Because these make real LLM calls, their happy-path tests are gated
(`RUN_LLM_E2E_TESTS=1`); the guard tests (malformed body → 422, unknown variant →
404) fail before any provider call and run in CI.

`GET /api/agents/{agent}/prompt?variant=` returns the externalised prompt source
(system + user) for an agent/variant, for the run-detail expand panel.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.agents._shared import ProbeMetadata
from backend.app.agents.adjuster import Adjuster
from backend.app.agents.adjuster_models import AdjusterOutput
from backend.app.agents.doc_parser import DocParser
from backend.app.agents.doc_parser_models import DocParserOutput
from backend.app.agents.guardrail import Guardrail
from backend.app.agents.guardrail_models import GuardrailOutput
from backend.app.agents.validator import Validator, default_embedder
from backend.app.agents.validator_models import RetrievedChunk, ValidatorVerdict
from backend.app.api.pipeline import get_settings, get_variant_registry
from backend.app.claims import ClaimType
from backend.app.llm import get_provider
from backend.app.llm.provider import LLMProvider
from backend.app.orchestrator.variant_factory import (
    _build_validator,
    resolve_validator_config,
)
from backend.app.orchestrator.variant_registry import (
    UnknownVariantError,
    VariantRegistry,
)
from backend.app.prompts import PromptLoader
from backend.settings import Settings

agents_test_router = APIRouter(prefix="/agents", tags=["agents"])

# Agent → its externalised system-prompt name and default user-template name.
_PROMPT_NAMES: dict[str, tuple[str, str]] = {
    "doc_parser": ("doc_parser", "doc_parser_template"),
    "validator": ("validator", "validator_template"),
    "adjuster": ("adjuster", "adjuster_template"),
    "guardrail": ("guardrail", "guardrail_template"),
}


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


class ProbeMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int


def _meta(probe: ProbeMetadata) -> ProbeMeta:
    return ProbeMeta(
        model=probe.model,
        latency_ms=probe.latency_ms,
        prompt_tokens=probe.prompt_tokens,
        completion_tokens=probe.completion_tokens,
    )


class DocParserTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narrative: str = Field(min_length=1, max_length=5000)


class ValidatorTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narrative: str = Field(min_length=1, max_length=5000)
    # Accepted for API-shape parity; the narrative-driven retrieval does not key
    # on claim_type, so it is reserved (not consumed by the current probe).
    claim_type: ClaimType


class AdjusterTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_parser_output: DocParserOutput
    validator_verdict: ValidatorVerdict


class GuardrailTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adjuster_output: AdjusterOutput
    retrieved_chunks: list[RetrievedChunk]


class DocParserTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: DocParserOutput
    meta: ProbeMeta


class ValidatorTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: ValidatorVerdict
    retrieved_chunks: list[RetrievedChunk]
    meta: ProbeMeta


class AdjusterTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: AdjusterOutput
    meta: ProbeMeta


class GuardrailTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: GuardrailOutput
    meta: ProbeMeta


class AgentPromptView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str
    variant: str
    system: str
    user: str


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@agents_test_router.post("/test/doc-parser", response_model=DocParserTestResult)
def test_doc_parser(
    body: DocParserTestRequest,
    variant: str = "default",
    settings: Settings = Depends(get_settings),
    registry: VariantRegistry = Depends(get_variant_registry),
) -> DocParserTestResult:
    _require_variant(registry, variant)
    agent = DocParser.with_defaults(settings, provider=_provider(settings, "anthropic"))
    output, meta = agent.parse(body.narrative)
    return DocParserTestResult(output=output, meta=_meta(meta))


@agents_test_router.post("/test/validator", response_model=ValidatorTestResult)
def test_validator(
    body: ValidatorTestRequest,
    variant: str = "default",
    settings: Settings = Depends(get_settings),
    registry: VariantRegistry = Depends(get_variant_registry),
) -> ValidatorTestResult:
    agent = _validator_for(settings, registry, variant)  # raises 404 on bad variant
    verdict, chunks, meta = agent.assess(body.narrative)
    return ValidatorTestResult(output=verdict, retrieved_chunks=chunks, meta=_meta(meta))


@agents_test_router.post("/test/adjuster", response_model=AdjusterTestResult)
def test_adjuster(
    body: AdjusterTestRequest,
    variant: str = "default",
    settings: Settings = Depends(get_settings),
    registry: VariantRegistry = Depends(get_variant_registry),
) -> AdjusterTestResult:
    _require_variant(registry, variant)
    agent = Adjuster.with_defaults(settings, provider=_provider(settings, "mistral"))
    output, meta = agent.estimate(body.doc_parser_output, body.validator_verdict)
    return AdjusterTestResult(output=output, meta=_meta(meta))


@agents_test_router.post("/test/guardrail", response_model=GuardrailTestResult)
def test_guardrail(
    body: GuardrailTestRequest,
    variant: str = "default",
    settings: Settings = Depends(get_settings),
    registry: VariantRegistry = Depends(get_variant_registry),
) -> GuardrailTestResult:
    _require_variant(registry, variant)
    agent = Guardrail.with_defaults(settings, provider=_provider(settings, "anthropic"))
    output, meta = agent.check(body.adjuster_output, body.retrieved_chunks)
    return GuardrailTestResult(output=output, meta=_meta(meta))


@agents_test_router.get("/{agent}/prompt", response_model=AgentPromptView)
def get_agent_prompt(
    agent: str,
    variant: str = "default",
    registry: VariantRegistry = Depends(get_variant_registry),
) -> AgentPromptView:
    """Return the externalised system + user prompt source for an agent/variant."""
    normalised = agent.replace("-", "_")
    names = _PROMPT_NAMES.get(normalised)
    if names is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent}")
    _require_variant(registry, variant)
    system_name, user_name = names
    user_template = _user_template_for(normalised, user_name, registry, variant)
    loader = PromptLoader()
    return AgentPromptView(
        agent=normalised,
        variant=variant,
        system=loader.raw("system", system_name),
        user=loader.raw("user", user_template),
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _require_variant(registry: VariantRegistry, variant: str) -> None:
    try:
        registry.resolve(variant)
    except UnknownVariantError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _provider(settings: Settings, vendor: str) -> LLMProvider:
    # vendor is a fixed literal at each call site; cast through the factory.
    return get_provider(settings, vendor)  # type: ignore[arg-type]


def _validator_for(
    settings: Settings, registry: VariantRegistry, variant: str
) -> Validator:
    try:
        spec = registry.resolve(variant)
    except UnknownVariantError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    config = resolve_validator_config(spec)
    provider = _provider(settings, config.provider_name)
    embedder: Callable[[str], np.ndarray] = default_embedder(settings)
    return _build_validator(
        config=config, settings=settings, provider=provider, embedder=embedder
    )


def _user_template_for(
    agent: str, default_template: str, registry: VariantRegistry, variant: str
) -> str:
    # Only the validator's user template changes by variant in Phase 5/6.
    if agent == "validator":
        return resolve_validator_config(registry.resolve(variant)).user_template_name
    return default_template
