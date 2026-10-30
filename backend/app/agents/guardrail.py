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
  3. Call the model its settings select (Claude Haiku by default)
     through the LLM Gateway. The LLM's job is
     to find subtler failures the rule engine missed —
     particularly semantic-bias and citation cases the
     regex-only floor cannot catch.
  4. Parse the LLM's JSON `flags` list into *claims*, then
     verify them (Phase 9.2.2, `guardrail_llm_flags.py`): a
     `hallucinated_citation` claim counts only when its `quote`
     is found in the Adjuster's reasoning and that span has the
     shape of a named provision by the rule engine's own test.
     Refused claims are recorded, not counted. Counted claims
     are labelled `source="llm"` and merged with the rule
     engine's flags.
  5. Decide `passed`: `True` iff the combined flag list is
     empty. This is the *fail-closed* contract — any single
     flag from either detector aborts the auto-approve path.
  6. Write a complete audit-log entry under the supplied
     correlation id, including the verified and refused LLM
     claims with their evidence.

`evaluate(...)` takes the upstream Adjuster output and the
retrieved chunks directly. The orchestrator (Phase 4) supplies
both from its in-memory pipeline state.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from pydantic import ValidationError as PydanticValidationError

from backend.app.agents._shared import (
    CapturedRequest,
    ProbeMetadata,
    attach_request,
    probe_metadata,
)
from backend.app.agents._shared import (
    excerpt as _excerpt,
)
from backend.app.agents._shared import (
    extract_json_block as _extract_json_block,
)
from backend.app.agents._shared import (
    new_correlation_id as _new_correlation_id,
)
from backend.app.agents.adjuster_models import AdjusterOutput, AdjusterResult
from backend.app.agents.guardrail_llm_flags import (
    LLMCheckOutcome,
    LLMFlagClaim,
    verify_llm_flags,
)
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
from backend.data.market_data import MarketRange
from backend.db.connection import open_connection
from backend.settings import Settings

# Excerpt budgets for the audit payload.
_REASONING_AUDIT_EXCERPT_CHARS = 1000
_CHUNK_AUDIT_EXCERPT_CHARS = 300

# Locked audit step identifier.
_AUDIT_STEP_NAME = "output_check"

# Pre-baked summary copy. Defined once so the audit row is stable
# across runs that produced equivalent flag sets.
_SUMMARY_PASS = "No additional issues found beyond the rule-engine pre-scan."
_SUMMARY_FAIL_TEMPLATE = "Guardrail flagged {count} issue(s): {kinds}."


@dataclass(frozen=True)
class _LLMCall:
    """
    Everything one LLM check produced, on every exit path.

    `request` is built before the call, so it is present even when the provider
    raised. `outcome` is present only when the reply parsed; on the error paths
    it is `None` and `error` carries the cause.
    """

    response: ProviderResponse | None
    outcome: LLMCheckOutcome | None
    error: BaseException | None
    latency_ms: int
    request: CapturedRequest


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
            call = self._invoke_llm(
                adjuster_result=adjuster_result,
                retrieved_chunks=retrieved_chunks,
                rule_flags=rule_flags,
            )
            output = (
                _combine_and_decide(rule_flags, call.outcome.counted)
                if call.outcome is not None
                else None
            )
            self._write_audit(
                conn=conn,
                correlation_id=correlation_id,
                claim_id=claim_id,
                adjuster_result=adjuster_result,
                retrieved_chunks=retrieved_chunks,
                rule_flags=rule_flags,
                call=call,
                output=output,
            )

            if call.error is not None:
                raise call.error
            assert output is not None
            assert call.response is not None
            return GuardrailResult(
                claim_id=claim_id,
                correlation_id=correlation_id,
                output=output,
                model=call.response.model,
                latency_ms=call.latency_ms,
            )

    def check(
        self,
        adjuster_output: AdjusterOutput,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[GuardrailOutput, ProbeMetadata]:
        """
        Run the guardrail check on an adjuster output — no audit, no claim.

        The guardrail reads only the adjuster's *output* (reasoning + settlement),
        so the test-bench path wraps it in a minimal `AdjusterResult` with a
        synthetic range that contains the value, letting the existing rule-engine
        + LLM path run unchanged. The wrapping is test-bench only; the orchestrator
        always passes a real result. The only side effect is the APILogger record.
        """
        synthetic = AdjusterResult(
            claim_id=_new_correlation_id(),
            correlation_id=_new_correlation_id(),
            output=adjuster_output,
            market_range=MarketRange(
                claim_type="probe",
                severity="moderate",
                floor=Decimal("0"),
                ceiling=adjuster_output.recommended_settlement,
            ),
            model="probe",
            latency_ms=0,
        )
        rule_flags = self._run_rule_checks(synthetic, retrieved_chunks)
        call = self._invoke_llm(
            adjuster_result=synthetic,
            retrieved_chunks=retrieved_chunks,
            rule_flags=rule_flags,
        )
        if call.error is not None:
            raise call.error
        assert call.response is not None
        assert call.outcome is not None
        output = _combine_and_decide(rule_flags, call.outcome.counted)
        return output, probe_metadata(call.response, call.latency_ms)

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
    ) -> _LLMCall:
        """
        Build the prompt, call the provider, parse the LLM's claims, verify them.

        On success `outcome.counted` may be empty (clean scan, or every claim
        refused); on failure `outcome` is `None` and `error` carries the cause.
        The verification oracle is the rule engine this agent holds, so a test
        engine with a custom citation pattern is honoured here too.
        """
        system_prompt = self._prompt_loader.system("guardrail")
        user_prompt = self._prompt_loader.user(
            "guardrail_template",
            adjuster_settlement=str(adjuster_result.output.recommended_settlement),
            adjuster_reasoning=adjuster_result.output.reasoning,
            retrieved_chunks=_format_chunks_for_prompt(retrieved_chunks),
            rule_flags_already_found=_format_rule_flags_for_prompt(rule_flags),
        )
        request = CapturedRequest(
            system=system_prompt,
            user=user_prompt,
            model=self._settings.llm.model_for("guardrail"),
        )
        correlation_id = _new_correlation_id()
        t0 = time.perf_counter()
        try:
            response = self._provider.complete(
                system=system_prompt,
                user=user_prompt,
                model=request.model,
                max_tokens=self._settings.llm.guardrail_max_tokens,
                temperature=self._settings.llm.guardrail_temperature,
                correlation_id=correlation_id,
                agent="guardrail",
                step=_AUDIT_STEP_NAME,
                response_format="text",
                timeout_s=self._settings.llm.request_timeout_s,
            )
        except LLMProviderError as exc:
            return _LLMCall(None, None, exc, int((time.perf_counter() - t0) * 1000), request)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        try:
            claims = _parse_llm_flags(response.text)
        except ValueError as exc:
            return _LLMCall(response, None, exc, latency_ms, request)
        outcome = verify_llm_flags(
            claims,
            reasoning=adjuster_result.output.reasoning,
            citation_pattern=self._rule_engine.citation_pattern,
        )
        return _LLMCall(response, outcome, None, latency_ms, request)

    def _write_audit(
        self,
        *,
        conn: psycopg.Connection,
        correlation_id: UUID,
        claim_id: UUID,
        adjuster_result: AdjusterResult,
        retrieved_chunks: list[RetrievedChunk],
        rule_flags: list[GuardrailFlag],
        call: _LLMCall,
        output: GuardrailOutput | None,
    ) -> None:
        payload = _build_audit_payload(
            claim_id=claim_id,
            adjuster_result=adjuster_result,
            retrieved_chunks=retrieved_chunks,
            rule_flags=rule_flags,
            call=call,
            output=output,
            provider_label=self._provider.vendor,
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


def _parse_llm_flags(response_text: str) -> list[LLMFlagClaim]:
    """
    Pull the LLM's `flags` array out of the JSON response as unverified claims.

    Failure modes, surfaced as `ValueError` with diagnostic context:
      - No `{...}` block.
      - Non-JSON.
      - Non-object JSON.
      - Missing `flags` key.
      - `flags` is not a list.
      - Any item fails `LLMFlagClaim` schema validation (unknown keys, a
        `quote` of the wrong type, an unknown `kind`).

    A missing `quote` is *not* a parse failure: `verify_llm_flags` refuses the
    claim with `no_quote`, which is the recordable finding.
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

    claims: list[LLMFlagClaim] = []
    for index, item in enumerate(flags_raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"Guardrail: model response 'flags[{index}]' must be an object; "
                f"got type={type(item).__name__}"
            )
        # The LLM is asked not to emit `source`; the claim model forbids it and
        # `verify_llm_flags` stamps `source="llm"` on promotion.
        try:
            claims.append(LLMFlagClaim.model_validate(item))
        except PydanticValidationError as exc:
            raise ValueError(
                f"Guardrail: model response 'flags[{index}]' failed schema "
                f"validation; errors={exc.errors()} item={item!r}"
            ) from exc
    return claims


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
    call: _LLMCall,
    output: GuardrailOutput | None,
    provider_label: str,
) -> dict[str, Any]:
    """Assemble the locked guardrail-step audit payload.

    `provider_label` is the provider the agent actually holds
    (`self._provider.vendor`), per the Phase 5 truthful-provider rule extended to
    every agent in Phase 8.6 — the Guardrail's provider is a settings choice.

    `call.request` carries the literal prompt (Phase 8.3) and requested model
    (Phase 8.5.3) sent to the model, attached to the `llm_call` block when a call
    was made. The two Phase 9.2.2 keys (`llm_flags_counted`, `llm_flags_discarded`)
    are built by `_llm_verification_block` and are always present.
    """
    response, latency_ms, error, request = (
        call.response, call.latency_ms, call.error, call.request
    )
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
        "llm_call": attach_request(
            {
                "provider": provider_label,
                "model": response.model,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "latency_ms": latency_ms,
            }
            if response is not None
            else {"provider": provider_label, "latency_ms": latency_ms},
            request,
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
        **_llm_verification_block(call.outcome),
    }
    return payload


def _llm_verification_block(outcome: LLMCheckOutcome | None) -> dict[str, Any]:
    """
    The Phase 9.2.2 additive audit keys, always present.

    Both lists are empty when nothing was verified — a clean reply, or the error
    paths where no reply was parsed (the `error` block says why) — so the shape
    is stable across every row written from `0.9.1.2` on. `llm_flags_counted`
    carries the reasoning's own span that promoted each citation flag; without it
    the audit would hold the evidence for every refusal and none for any
    acceptance.
    """
    if outcome is None:
        return {"llm_flags_counted": [], "llm_flags_discarded": []}
    return {
        "llm_flags_counted": [
            flag.model_dump(mode="json") for flag in outcome.counted_evidence
        ],
        "llm_flags_discarded": [
            flag.model_dump(mode="json") for flag in outcome.discarded
        ],
    }
