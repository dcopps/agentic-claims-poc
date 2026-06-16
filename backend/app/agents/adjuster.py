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
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from pydantic import ValidationError as PydanticValidationError

from backend.app.agents._shared import (
    CapturedPrompt,
    ProbeMetadata,
    attach_prompt,
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

# Deterministic demo affordance (Phase 7). A seeded claim carrying one of these
# scenario tags returns the named fixture's Adjuster output instead of calling the
# LLM, so the demo reproduces reliably. The audit payload records `demo_fixture`
# truthfully, so the trail shows the output came from a fixture, not a model.
_DEMO_FIXTURES_DIR = Path("backend/data/demo_fixtures")
_SCENARIO_FIXTURES: dict[str, str] = {
    "guardrail_escalation": "guardrail_adjuster.json",
}
# Provider/model labels recorded in the audit when the demo fixture is used.
_DEMO_FIXTURE_PROVIDER = "demo_fixture"
_DEMO_FIXTURE_MODEL = "demo_fixture"


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
            # Deterministic demo path: a seeded scenario claim returns a fixture
            # instead of calling the model. Otherwise the live LLM path runs.
            fixture = self._load_demo_fixture(conn, claim_id, market_range)
            response: ProviderResponse | None
            output: AdjusterOutput | None
            error: BaseException | None
            # The fixture path never calls the LLM, so no prompt was sent; `prompt`
            # stays None and the audit omits `llm_call.prompt` (truthful — see
            # `attach_prompt`). The live path captures the literal prompt.
            prompt: CapturedPrompt | None
            if fixture is not None:
                response, output, error, latency_ms, prompt = None, fixture, None, 0, None
            else:
                response, output, error, latency_ms, prompt = self._invoke_llm(
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
                demo_fixture=fixture is not None,
                prompt=prompt,
            )

            if error is not None:
                raise error
            assert output is not None
            model = response.model if response is not None else _DEMO_FIXTURE_MODEL
            return AdjusterResult(
                claim_id=claim_id,
                correlation_id=correlation_id,
                output=output,
                market_range=market_range,
                model=model,
                latency_ms=latency_ms,
            )

    def estimate(
        self,
        parsed_claim: DocParserOutput,
        validator_verdict: ValidatorVerdict,
    ) -> tuple[AdjusterOutput, ProbeMetadata]:
        """
        Run the settlement-estimate LLM step — no audit, no claim (test bench).

        Looks up the market range for the parsed claim, calls the model, parses
        and range-checks the output, and returns it with the LLM-call metadata.
        Reuses `evaluate`'s steps; the only side effect is the APILogger record.
        """
        market_range = self._lookup_market_range(parsed_claim)
        response, output, error, latency_ms, _prompt = self._invoke_llm(
            parsed_claim=parsed_claim,
            validator_verdict=validator_verdict,
            market_range=market_range,
        )
        if error is not None:
            raise error
        assert response is not None and output is not None
        return output, probe_metadata(response, latency_ms)

    # ------------------------------------------------------------------ #
    # Pipeline steps
    # ------------------------------------------------------------------ #

    def _lookup_market_range(self, parsed_claim: DocParserOutput) -> MarketRange:
        """Defensive wrapper around the table's lookup."""
        return self._market_data.lookup(
            claim_type=parsed_claim.claim_type,
            reported_amount=parsed_claim.claimed_amount,
        )

    def _load_demo_fixture(
        self,
        conn: psycopg.Connection,
        claim_id: UUID,
        market_range: MarketRange,
    ) -> AdjusterOutput | None:
        """
        Return the demo-fixture Adjuster output for a seeded scenario claim, or
        None for a normal claim.

        Keyed on the claim's `scenario_tag` (already a demo marker). Fail-closed:
        a tagged claim whose fixture is missing, malformed, or out of the
        looked-up market range raises — it never silently falls through to a live
        call, which would defeat the determinism the fixture exists to provide.
        """
        scenario_tag = self._read_scenario_tag(conn, claim_id)
        fixture_name = (
            _SCENARIO_FIXTURES.get(scenario_tag) if scenario_tag is not None else None
        )
        if fixture_name is None:
            return None
        output = _load_fixture_output(_DEMO_FIXTURES_DIR / fixture_name)
        # The fixture must satisfy the same within-range invariant as a live value.
        _assert_within_range(output.recommended_settlement, market_range)
        return output

    def _read_scenario_tag(
        self, conn: psycopg.Connection, claim_id: UUID
    ) -> str | None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT scenario_tag FROM claims WHERE claim_id = %s", (claim_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        tag: str | None = row[0]
        return tag

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
        CapturedPrompt,
    ]:
        """
        Build the prompt, call the provider, parse and range-check
        the output. Returns `(response, output, error, latency_ms, prompt)`.
        `prompt` is the literal text sent — built before the call, so returned on
        every path including the provider-exception path.
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
        prompt = CapturedPrompt(system=system_prompt, user=user_prompt)
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
            return None, None, exc, int((time.perf_counter() - t0) * 1000), prompt

        try:
            output = _parse_output(response.text, market_range)
        except ValueError as exc:
            return response, None, exc, int((time.perf_counter() - t0) * 1000), prompt
        return response, output, None, int((time.perf_counter() - t0) * 1000), prompt

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
        demo_fixture: bool = False,
        prompt: CapturedPrompt | None = None,
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
            demo_fixture=demo_fixture,
            prompt=prompt,
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


def _llm_call_block(
    response: ProviderResponse | None,
    latency_ms: int,
    demo_fixture: bool,
    prompt: CapturedPrompt | None,
) -> dict[str, Any]:
    """Build the audit `llm_call` block, truthful about the demo-fixture path.

    The literal `prompt` is attached when one was sent (Phase 8.3). The demo-fixture
    path passes `prompt=None`, so its block carries no `prompt` key — there was no
    model call to capture text from.
    """
    if demo_fixture:
        return {
            "provider": _DEMO_FIXTURE_PROVIDER,
            "note": "no model call; deterministic demo fixture",
            "latency_ms": latency_ms,
        }
    if response is not None:
        return attach_prompt(
            {
                "provider": _PROVIDER_LABEL,
                "model": response.model,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "latency_ms": latency_ms,
            },
            prompt,
        )
    return attach_prompt({"provider": _PROVIDER_LABEL, "latency_ms": latency_ms}, prompt)


def _load_fixture_output(path: Path) -> AdjusterOutput:
    """
    Load a demo-fixture file into a validated `AdjusterOutput`. Fail-closed.

    Keys prefixed with `_` (the JSON-comment convention used in the fixture) are
    stripped before strict validation. Any failure — missing file, non-JSON,
    non-object, or a body that does not satisfy `AdjusterOutput` — raises
    `ValueError`; the caller never falls through to a live call on a bad fixture.
    """
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Adjuster: demo fixture not found at {resolved}")
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Adjuster: demo fixture is not valid JSON at {resolved}; error={exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"Adjuster: demo fixture must be a JSON object at {resolved}; "
            f"got type={type(data).__name__}"
        )
    fields = {key: value for key, value in data.items() if not key.startswith("_")}
    try:
        return AdjusterOutput.model_validate(fields)
    except PydanticValidationError as exc:
        raise ValueError(
            "Adjuster: demo fixture failed AdjusterOutput validation at "
            f"{resolved}; errors={exc.errors()}"
        ) from exc


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
    demo_fixture: bool = False,
    prompt: CapturedPrompt | None = None,
) -> dict[str, Any]:
    """Assemble the locked adjuster-step audit payload.

    `demo_fixture` is True when the output came from the deterministic demo
    fixture rather than a model call (Phase 7). It is recorded at the top level
    and the `llm_call` block reports no model call, so the trail is truthful about
    the source — the demo affordance is auditable, not hidden.

    `prompt` (Phase 8.3) is the literal text sent to the model; it is attached to
    the `llm_call` block on the live path and absent on the demo-fixture path.
    """
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
        "demo_fixture": demo_fixture,
        "llm_call": _llm_call_block(response, latency_ms, demo_fixture, prompt),
        "output": (
            {
                # `mode="json"` converts Decimal -> string here too.
                "recommended_settlement": str(output.recommended_settlement),
                "confidence": output.confidence,
                # Full reasoning is stored so the audit log alone is sufficient to
                # reconstruct any past decision (Phase 5 runs reconstruction reads
                # this). `reasoning_excerpt` is retained for human triage at a
                # glance; `reasoning` is the authoritative, untruncated value
                # (bounded to 2000 chars by the model constraint).
                "reasoning": output.reasoning,
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
