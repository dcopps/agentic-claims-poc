"""
Adjuster agent — structured settlement estimator.

Step-for-step:

  1. Look up the `(claim_type, severity)` cell in the market-data
     table. Severity is derived deterministically inside the table
     from the parsed claim's `claimed_amount` — never an
     LLM-supplied input.
  2. Build the user prompt via `PromptLoader`, threading the
     parsed claim, the validator's verdict, and the looked-up
     range as explicit placeholders. No inline f-strings.
  3. Call Mistral Large through the LLM Gateway with `response_format=
     "json"`. The system prompt locks the schema.
  4. Parse the response into `AdjusterOutput`. **Re-validate** the
     value is in `[floor, ceiling]` — out-of-bounds is a hard
     `ValueError`, never a silent clamp. The contract Phase 4
     depends on is that any `AdjusterResult` the agent emits has a
     settlement value strictly inside the looked-up range.
  5. Write a complete audit-log entry under the supplied
     correlation id, including the market range used so the
     decision is reconstructable from the log alone.

The agent does not read the database directly: its `evaluate(...)`
input already carries the parsed claim and the validator's verdict
from earlier orchestrator steps. `claim_id` and `correlation_id` are
required for audit logging.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from decimal import Decimal
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
from backend.app.agents.adjuster_models import (
    AdjusterOutput,
    AdjusterResult,
)
from backend.app.agents.doc_parser_models import DocParserOutput
from backend.app.agents.validator_models import ValidatorVerdict
from backend.app.audit import AuditEvent, AuditWriter
from backend.app.llm.provider import (
    LLMProvider,
    LLMProviderError,
    ProviderResponse,
)
from backend.app.prompts import PromptLoader
from backend.data.market_data import (
    MarketDataTable,
    MarketRange,
    load_market_data,
)
from backend.db.connection import open_connection
from backend.settings import Settings

# Excerpt budgets for the audit payload's input section. Sized to
# keep the JSONB row triage-readable without flooding it.
_REASONING_AUDIT_EXCERPT_CHARS = 1000
_VALIDATOR_REASONING_EXCERPT_CHARS = 500

# Locked audit step identifier.
_AUDIT_STEP_NAME = "settlement_estimate"

# Adjuster routes through Mistral, per the project's architectural
# decisions.
_PROVIDER_LABEL = "mistral"


class Adjuster:
    """Settlement-estimation agent with within-range LLM selection."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_loader: PromptLoader,
        market_data: MarketDataTable,
        settings: Settings,
        connection_factory: (
            Callable[[], AbstractContextManager[psycopg.Connection]] | None
        ) = None,
    ) -> None:
        self._provider: LLMProvider = provider
        self._prompt_loader: PromptLoader = prompt_loader
        self._market_data: MarketDataTable = market_data
        self._settings: Settings = settings
        self._connection_factory: Callable[
            [], AbstractContextManager[psycopg.Connection]
        ] = connection_factory or self._default_connection_factory

    @classmethod
    def with_defaults(
        cls, settings: Settings, *, provider: LLMProvider
    ) -> Adjuster:
        """Wire production collaborators, including the market-data load."""
        return cls(
            provider=provider,
            prompt_loader=PromptLoader(),
            market_data=load_market_data(settings.adjuster.market_data_path),
            settings=settings,
        )

    def evaluate(
        self,
        claim_id: UUID,
        correlation_id: UUID,
        *,
        parsed_claim: DocParserOutput,
        validator_verdict: ValidatorVerdict,
    ) -> AdjusterResult:
        """
        Run the settlement-estimate flow. Returns a typed
        `AdjusterResult` whose embedded value is guaranteed in-range;
        raises `ValueError` on any precondition failure, parse
        failure, or out-of-bounds value; raises `LLMProviderError`
        on Gateway failure. Audit log entries are written on every
        exit path.
        """
        with self._connection_factory() as conn:
            market_range = self._lookup_market_range(parsed_claim)
            response, output, error, latency_ms = self._invoke_llm(
                parsed_claim=parsed_claim,
                validator_verdict=validator_verdict,
                market_range=market_range,
            )
            self._write_audit(
                conn=conn,
                correlation_id=correlation_id,
                claim_id=claim_id,
                parsed_claim=parsed_claim,
                validator_verdict=validator_verdict,
                market_range=market_range,
                response=response,
                output=output,
                latency_ms=latency_ms,
                error=error,
            )

            if error is not None:
                raise error
            assert output is not None
            assert response is not None
            return AdjusterResult(
                claim_id=claim_id,
                correlation_id=correlation_id,
                output=output,
                market_range=market_range,
                model=response.model,
                latency_ms=latency_ms,
            )

    # ------------------------------------------------------------------ #
    # Pipeline steps
    # ------------------------------------------------------------------ #

    def _lookup_market_range(self, parsed_claim: DocParserOutput) -> MarketRange:
        """Defensive wrapper around the table's lookup."""
        return self._market_data.lookup(
            claim_type=parsed_claim.claim_type,
            reported_amount=parsed_claim.claimed_amount,
        )

    def _invoke_llm(
        self,
        *,
        parsed_claim: DocParserOutput,
        validator_verdict: ValidatorVerdict,
        market_range: MarketRange,
    ) -> tuple[
        ProviderResponse | None,
        AdjusterOutput | None,
        BaseException | None,
        int,
    ]:
        """
        Build the prompt, call the provider, parse and range-check
        the output. Returns `(response, output, error, latency_ms)`.
        """
        system_prompt = self._prompt_loader.system("adjuster")
        user_prompt = self._prompt_loader.user(
            "adjuster_template",
            claim_summary=_format_claim_summary(parsed_claim),
            validator_verdict=_format_validator_verdict(validator_verdict),
            claim_type=market_range.claim_type,
            severity=market_range.severity,
            range_floor=str(market_range.floor),
            range_ceiling=str(market_range.ceiling),
        )
        correlation_id = _new_correlation_id()
        t0 = time.perf_counter()
        try:
            response = self._provider.complete(
                system=system_prompt,
                user=user_prompt,
                model=self._settings.llm.mistral.adjuster_model,
                max_tokens=self._settings.llm.adjuster_max_tokens,
                temperature=self._settings.llm.adjuster_temperature,
                correlation_id=correlation_id,
                agent="adjuster",
                step=_AUDIT_STEP_NAME,
                response_format="json",
                timeout_s=self._settings.llm.request_timeout_s,
            )
        except LLMProviderError as exc:
            return None, None, exc, int((time.perf_counter() - t0) * 1000)

        try:
            output = _parse_output(response.text, market_range)
        except ValueError as exc:
            return response, None, exc, int((time.perf_counter() - t0) * 1000)
        return response, output, None, int((time.perf_counter() - t0) * 1000)

    def _write_audit(
        self,
        *,
        conn: psycopg.Connection,
        correlation_id: UUID,
        claim_id: UUID,
        parsed_claim: DocParserOutput,
        validator_verdict: ValidatorVerdict,
        market_range: MarketRange,
        response: ProviderResponse | None,
        output: AdjusterOutput | None,
        latency_ms: int,
        error: BaseException | None,
    ) -> None:
        payload = _build_audit_payload(
            claim_id=claim_id,
            parsed_claim=parsed_claim,
            validator_verdict=validator_verdict,
            market_range=market_range,
            response=response,
            output=output,
            latency_ms=latency_ms,
            error=error,
        )
        event = AuditEvent(
            correlation_id=correlation_id,
            claim_id=claim_id,
            agent="adjuster",
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


def _format_claim_summary(parsed_claim: DocParserOutput) -> str:
    """Render the parsed claim as a deterministic block for the prompt."""
    return (
        f"- Cause: {parsed_claim.claim_type}\n"
        f"- Loss date: {parsed_claim.loss_date.isoformat()}\n"
        f"- Jurisdiction: {parsed_claim.jurisdiction}\n"
        f"- Claimant: {parsed_claim.claimant_identifier}\n"
        f"- Claimed amount (USD): {parsed_claim.claimed_amount}\n"
        f"- Summary: {parsed_claim.narrative_summary}"
    )


def _format_validator_verdict(verdict: ValidatorVerdict) -> str:
    """Render the validator's verdict as a deterministic block for the prompt."""
    return (
        f"- Covered: {verdict.covered}\n"
        f"- Confidence: {verdict.confidence:.2f}\n"
        f"- Policy basis: {verdict.policy_basis}\n"
        f"- Reasoning: {verdict.reasoning}"
    )


def _parse_output(response_text: str, market_range: MarketRange) -> AdjusterOutput:
    """
    Pull an `AdjusterOutput` out of the model's text response and
    enforce the within-range invariant.

    Failure modes, surfaced as `ValueError` with diagnostic context:
      - No `{...}` block.
      - Non-JSON.
      - Non-object JSON.
      - Pydantic validation failure (negative amount, bad
        confidence, oversized reasoning).
      - Settlement value outside `[floor, ceiling]`.

    No silent clamping. A model that returns out-of-bounds is a hard
    failure the audit log records.
    """
    raw = _extract_json_block(response_text, agent_name="Adjuster")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        excerpt_text = response_text[:500]
        raise ValueError(
            "Adjuster: model response is not valid JSON; "
            f"error={exc} excerpt={excerpt_text!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            "Adjuster: model response JSON is not an object; "
            f"got type={type(parsed).__name__}"
        )

    try:
        output = AdjusterOutput.model_validate(parsed)
    except PydanticValidationError as exc:
        raise ValueError(
            "Adjuster: model response failed schema validation; "
            f"errors={exc.errors()} parsed={parsed!r}"
        ) from exc

    _assert_within_range(output.recommended_settlement, market_range)
    return output


def _assert_within_range(value: Decimal, market_range: MarketRange) -> None:
    """Raise if the model's settlement value falls outside the looked-up range."""
    if not market_range.contains(value):
        raise ValueError(
            "Adjuster: model recommended_settlement falls outside the "
            f"market range [{market_range.floor}, {market_range.ceiling}] "
            f"for ({market_range.claim_type}, {market_range.severity}); "
            f"got {value} — refusing to silently clamp"
        )


def _build_audit_payload(
    *,
    claim_id: UUID,
    parsed_claim: DocParserOutput,
    validator_verdict: ValidatorVerdict,
    market_range: MarketRange,
    response: ProviderResponse | None,
    output: AdjusterOutput | None,
    latency_ms: int,
    error: BaseException | None,
) -> dict[str, Any]:
    """Assemble the locked adjuster-step audit payload."""
    # Decimal fields routed through `mode="json"` so the canonical
    # audit encoder (which refuses Decimal) sees only strings.
    validator_excerpt = {
        "covered": validator_verdict.covered,
        "confidence": validator_verdict.confidence,
        "policy_basis": validator_verdict.policy_basis,
        "reasoning_excerpt": _excerpt(
            validator_verdict.reasoning, _VALIDATOR_REASONING_EXCERPT_CHARS
        ),
    }
    payload: dict[str, Any] = {
        "input": {
            "claim_id": str(claim_id),
            "parsed_claim_excerpt": parsed_claim.model_dump(mode="json"),
            "validator_verdict_excerpt": validator_excerpt,
        },
        "market_data": {
            "claim_type": market_range.claim_type,
            "severity": market_range.severity,
            "floor": str(market_range.floor),
            "ceiling": str(market_range.ceiling),
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
                # `mode="json"` converts Decimal -> string here too.
                "recommended_settlement": str(output.recommended_settlement),
                "confidence": output.confidence,
                "reasoning_excerpt": _excerpt(
                    output.reasoning, _REASONING_AUDIT_EXCERPT_CHARS
                ),
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
