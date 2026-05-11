"""
Guardrail agent — output safety check on the Adjuster's response.

Step-for-step:

  1. Run the deterministic `GuardrailRuleEngine` over the
     Adjuster's reasoning and the retrieved policy chunks. The
     rule engine emits a small, explicit set of flags (PII,
     hallucinated citation, bias) — see `guardrail_rules.py`.
  2. Build the user prompt via `PromptLoader`, threading the
     Adjuster's reasoning, the retrieved chunks, and the rule
     engine's pre-detected findings (so the LLM does not
     duplicate them).
  3. Call Claude Haiku through the LLM Gateway. The LLM's job is
     to find subtler failures the rule engine missed —
     particularly semantic-bias and citation cases the
     regex-only floor cannot catch.
  4. Parse the LLM's JSON `flags` list, label the source as
     `"llm"` on each, and merge with the rule engine's flags.
  5. Decide `passed`: `True` iff the combined flag list is
     empty. This is the *fail-closed* contract — any single
     flag from either detector aborts the auto-approve path.
  6. Write a complete audit-log entry under the supplied
     correlation id.

`evaluate(...)` takes the upstream Adjuster output and the
retrieved chunks directly. The orchestrator (Phase 4) supplies
both from its in-memory pipeline state.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from pydantic import ValidationError as PydanticValidationError

from backend.app.agents._shared import (
    excerpt as _excerpt,
)
from backend.app.agents._shared import (
    extract_json_block as _extract_json_block,
)
from backend.app.agents._shared import (
    new_correlation_id as _new_correlation_id,
)
from backend.app.agents.adjuster_models import AdjusterResult
from backend.app.agents.guardrail_models import (
    GuardrailFlag,
    GuardrailOutput,
    GuardrailResult,
)
from backend.app.agents.guardrail_rules import GuardrailRuleEngine
from backend.app.agents.validator_models import RetrievedChunk
from backend.app.audit import AuditEvent, AuditWriter
from backend.app.llm.provider import (
    LLMProvider,
    LLMProviderError,
    ProviderResponse,
)
from backend.app.prompts import PromptLoader
from backend.db.connection import open_connection
from backend.settings import Settings

# Excerpt budgets for the audit payload.
_REASONING_AUDIT_EXCERPT_CHARS = 1000
_CHUNK_AUDIT_EXCERPT_CHARS = 300

# Locked audit step identifier.
_AUDIT_STEP_NAME = "output_check"

# Guardrail routes through Anthropic Haiku, per the project's
# architectural decisions.
_PROVIDER_LABEL = "anthropic"

# Pre-baked summary copy. Defined once so the audit row is stable
# across runs that produced equivalent flag sets.
_SUMMARY_PASS = "No additional issues found beyond the rule-engine pre-scan."
_SUMMARY_FAIL_TEMPLATE = "Guardrail flagged {count} issue(s): {kinds}."


class Guardrail:
    """Output-safety agent. Combines deterministic rules with an LLM check."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_loader: PromptLoader,
        settings: Settings,
        rule_engine: GuardrailRuleEngine | None = None,
        connection_factory: (
            Callable[[], AbstractContextManager[psycopg.Connection]] | None
        ) = None,
    ) -> None:
        self._provider: LLMProvider = provider
        self._prompt_loader: PromptLoader = prompt_loader
        self._settings: Settings = settings
        self._rule_engine: GuardrailRuleEngine = (
            rule_engine or GuardrailRuleEngine.with_defaults()
        )
        self._connection_factory: Callable[
            [], AbstractContextManager[psycopg.Connection]
        ] = connection_factory or self._default_connection_factory

    @classmethod
    def with_defaults(
        cls, settings: Settings, *, provider: LLMProvider
    ) -> Guardrail:
        """Wire production collaborators."""
        return cls(
            provider=provider,
            prompt_loader=PromptLoader(),
            settings=settings,
        )

    def evaluate(
        self,
        claim_id: UUID,
        correlation_id: UUID,
        *,
        adjuster_result: AdjusterResult,
        retrieved_chunks: list[RetrievedChunk],
    ) -> GuardrailResult:
        """
        Run the guardrail flow. Returns a typed `GuardrailResult`
        with `passed` set fail-closed; raises `ValueError` on parse
        failure and `LLMProviderError` on Gateway failure. Audit
        log entries are written on every exit path.
        """
        with self._connection_factory() as conn:
            rule_flags = self._run_rule_checks(adjuster_result, retrieved_chunks)
            response, llm_flags, error, latency_ms = self._invoke_llm(
                adjuster_result=adjuster_result,
                retrieved_chunks=retrieved_chunks,
                rule_flags=rule_flags,
            )
            output = (
                _combine_and_decide(rule_flags, llm_flags)
                if error is None
                else None
            )
            self._write_audit(
                conn=conn,
                correlation_id=correlation_id,
                claim_id=claim_id,
                adjuster_result=adjuster_result,
                retrieved_chunks=retrieved_chunks,
                rule_flags=rule_flags,
                response=response,
                output=output,
                latency_ms=latency_ms,
                error=error,
            )

            if error is not None:
                raise error
            assert output is not None
            assert response is not None
            return GuardrailResult(
                claim_id=claim_id,
                correlation_id=correlation_id,
                output=output,
                model=response.model,
                latency_ms=latency_ms,
            )

    # ------------------------------------------------------------------ #
    # Pipeline steps
    # ------------------------------------------------------------------ #

    def _run_rule_checks(
        self,
        adjuster_result: AdjusterResult,
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[GuardrailFlag]:
        return self._rule_engine.scan(
            reasoning=adjuster_result.output.reasoning,
            retrieved_chunks=retrieved_chunks,
        )

    def _invoke_llm(
        self,
        *,
        adjuster_result: AdjusterResult,
        retrieved_chunks: list[RetrievedChunk],
        rule_flags: list[GuardrailFlag],
    ) -> tuple[
        ProviderResponse | None,
        list[GuardrailFlag],
        BaseException | None,
        int,
    ]:
        """
        Build the prompt, call the provider, parse the LLM's flags.

        Returns `(response, llm_flags, error, latency_ms)`. On
        success `llm_flags` may be empty (clean scan); on failure
        it is empty and `error` carries the cause.
        """
        system_prompt = self._prompt_loader.system("guardrail")
        user_prompt = self._prompt_loader.user(
            "guardrail_template",
            adjuster_settlement=str(adjuster_result.output.recommended_settlement),
            adjuster_reasoning=adjuster_result.output.reasoning,
            retrieved_chunks=_format_chunks_for_prompt(retrieved_chunks),
            rule_flags_already_found=_format_rule_flags_for_prompt(rule_flags),
        )
        correlation_id = _new_correlation_id()
        t0 = time.perf_counter()
        try:
            response = self._provider.complete(
                system=system_prompt,
                user=user_prompt,
                model=self._settings.llm.anthropic.guardrail_model,
                max_tokens=self._settings.llm.guardrail_max_tokens,
                temperature=self._settings.llm.guardrail_temperature,
                correlation_id=correlation_id,
                agent="guardrail",
                step=_AUDIT_STEP_NAME,
                response_format="text",
                timeout_s=self._settings.llm.request_timeout_s,
            )
        except LLMProviderError as exc:
            return None, [], exc, int((time.perf_counter() - t0) * 1000)

        try:
            llm_flags = _parse_llm_flags(response.text)
        except ValueError as exc:
            return response, [], exc, int((time.perf_counter() - t0) * 1000)
        return response, llm_flags, None, int((time.perf_counter() - t0) * 1000)

    def _write_audit(
        self,
        *,
        conn: psycopg.Connection,
        correlation_id: UUID,
        claim_id: UUID,
        adjuster_result: AdjusterResult,
        retrieved_chunks: list[RetrievedChunk],
        rule_flags: list[GuardrailFlag],
        response: ProviderResponse | None,
        output: GuardrailOutput | None,
        latency_ms: int,
        error: BaseException | None,
    ) -> None:
        payload = _build_audit_payload(
            claim_id=claim_id,
            adjuster_result=adjuster_result,
            retrieved_chunks=retrieved_chunks,
            rule_flags=rule_flags,
            response=response,
            output=output,
            latency_ms=latency_ms,
            error=error,
        )
        event = AuditEvent(
            correlation_id=correlation_id,
            claim_id=claim_id,
            agent="guardrail",
            step=_AUDIT_STEP_NAME,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        AuditWriter(conn).append(event)

    def _default_connection_factory(
        self,
    ) -> AbstractContextManager[psycopg.Connection]:
        return open_connection(self._settings)


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #


def _format_chunks_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a deterministic block for the prompt."""
    blocks: list[str] = []
    for chunk in chunks:
        blocks.append(
            f"[section={chunk.section}]\n{chunk.content}"
        )
    return "\n\n".join(blocks)


def _format_rule_flags_for_prompt(flags: list[GuardrailFlag]) -> str:
    """
    Render the rule-engine flags as a numbered list for the prompt.

    The empty case returns a sentinel string rather than empty bytes
    so the prompt's placeholder is always populated and the model
    knows "nothing was pre-detected" — distinct from "I forgot to
    look at the rule flags".
    """
    if not flags:
        return "(none — rule engine reported no findings)"
    lines = [
        f"{idx}. [{flag.kind}] {flag.detail}"
        for idx, flag in enumerate(flags, start=1)
    ]
    return "\n".join(lines)


def _parse_llm_flags(response_text: str) -> list[GuardrailFlag]:
    """
    Pull the LLM's `flags` array out of the JSON response.

    Failure modes, surfaced as `ValueError` with diagnostic context:
      - No `{...}` block.
      - Non-JSON.
      - Non-object JSON.
      - Missing `flags` key.
      - `flags` is not a list.
      - Any item fails `GuardrailFlag` schema validation when
        decorated with `source="llm"`.
    """
    raw = _extract_json_block(response_text, agent_name="Guardrail")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        excerpt_text = response_text[:500]
        raise ValueError(
            "Guardrail: model response is not valid JSON; "
            f"error={exc} excerpt={excerpt_text!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            "Guardrail: model response JSON is not an object; "
            f"got type={type(parsed).__name__}"
        )

    flags_raw = parsed.get("flags")
    if flags_raw is None:
        raise ValueError(
            "Guardrail: model response is missing required key 'flags'; "
            f"keys={sorted(parsed.keys())}"
        )
    if not isinstance(flags_raw, list):
        raise ValueError(
            "Guardrail: model response 'flags' must be a list; "
            f"got type={type(flags_raw).__name__}"
        )

    flags: list[GuardrailFlag] = []
    for index, item in enumerate(flags_raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"Guardrail: model response 'flags[{index}]' must be an object; "
                f"got type={type(item).__name__}"
            )
        # The LLM is asked not to emit `source`; we stamp it here so
        # the merged flag list distinguishes detector provenance.
        payload = {**item, "source": "llm"}
        try:
            flags.append(GuardrailFlag.model_validate(payload))
        except PydanticValidationError as exc:
            raise ValueError(
                f"Guardrail: model response 'flags[{index}]' failed schema "
                f"validation; errors={exc.errors()} item={item!r}"
            ) from exc
    return flags


def _combine_and_decide(
    rule_flags: list[GuardrailFlag], llm_flags: list[GuardrailFlag]
) -> GuardrailOutput:
    """
    Merge the two flag lists and resolve `passed` fail-closed.

    Pass = empty combined list. Any flag, from either detector, sets
    `passed=False`. The `GuardrailOutput` model validator also
    enforces this invariant; computing it explicitly here keeps the
    failure surface inside the agent rather than relying on the
    Pydantic exception path.
    """
    combined: list[GuardrailFlag] = [*rule_flags, *llm_flags]
    passed = len(combined) == 0
    summary = (
        _SUMMARY_PASS
        if passed
        else _SUMMARY_FAIL_TEMPLATE.format(
            count=len(combined),
            kinds=", ".join(sorted({flag.kind for flag in combined})),
        )
    )
    return GuardrailOutput(passed=passed, flags=combined, summary=summary)


def _build_audit_payload(
    *,
    claim_id: UUID,
    adjuster_result: AdjusterResult,
    retrieved_chunks: list[RetrievedChunk],
    rule_flags: list[GuardrailFlag],
    response: ProviderResponse | None,
    output: GuardrailOutput | None,
    latency_ms: int,
    error: BaseException | None,
) -> dict[str, Any]:
    """Assemble the locked guardrail-step audit payload."""
    payload: dict[str, Any] = {
        "input": {
            "claim_id": str(claim_id),
            "adjuster_output_excerpt": {
                "recommended_settlement": str(
                    adjuster_result.output.recommended_settlement
                ),
                "confidence": adjuster_result.output.confidence,
                "reasoning_excerpt": _excerpt(
                    adjuster_result.output.reasoning,
                    _REASONING_AUDIT_EXCERPT_CHARS,
                ),
            },
            "retrieved_chunks_summary": [
                {
                    "chunk_id": str(chunk.chunk_id),
                    "section": chunk.section,
                    "content_excerpt": _excerpt(
                        chunk.content, _CHUNK_AUDIT_EXCERPT_CHARS
                    ),
                }
                for chunk in retrieved_chunks
            ],
        },
        "rule_checks": {
            "flag_count": len(rule_flags),
            "flags": [flag.model_dump(mode="json") for flag in rule_flags],
        },
        "llm_call": (
            {
                "provider": _PROVIDER_LABEL,
                "model": response.model,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "latency_ms": latency_ms,
            }
            if response is not None
            else {"provider": _PROVIDER_LABEL, "latency_ms": latency_ms}
        ),
        "output": (
            {
                "passed": output.passed,
                "flag_count": len(output.flags),
                "flags": [flag.model_dump(mode="json") for flag in output.flags],
                "summary": output.summary,
            }
            if output is not None
            else None
        ),
        "error": (
            {"type": type(error).__name__, "message": str(error)}
            if error is not None
            else None
        ),
    }
    return payload
