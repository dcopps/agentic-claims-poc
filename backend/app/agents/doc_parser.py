"""
Doc-Parser agent — structured-field extraction from FNOL narratives.

Step-for-step:

  1. Load the narrative from the `claims` table by `claim_id`. The
     orchestrator (Phase 4) is the canonical caller; isolation tests
     pass a stub connection factory.
  2. Build the user prompt via `PromptLoader` — no inline f-strings.
  3. Call Claude Haiku through the LLM Gateway with system/user
     separation. Haiku has no native JSON mode; the system prompt
     locks the format, and the parser strictly validates the result.
  4. Parse the response into `DocParserOutput`. Fail fast on
     malformed JSON, missing fields, type errors, or out-of-range
     values — no retry-rescue at this layer (retry is deferred to
     Phase 6).
  5. Write a complete audit-log entry under the supplied
     correlation id. Errors are audited alongside successes.

Every collaborator is constructor-injected. Tests swap stubs;
`with_defaults` wires the production graph.
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
from backend.app.agents.doc_parser_models import (
    DocParserOutput,
    DocParserResult,
)
from backend.app.audit import AuditEvent, AuditWriter
from backend.app.llm.provider import (
    LLMProvider,
    LLMProviderError,
    ProviderResponse,
)
from backend.app.prompts import PromptLoader
from backend.db.connection import open_connection
from backend.settings import Settings

# Excerpt budget for the audit-log narrative field. Matches the
# Validator's choice — long enough for triage, short enough to keep
# the audit JSONB row sub-megabyte.
_NARRATIVE_AUDIT_EXCERPT_CHARS = 1000

# Locked audit step identifier. Stable for downstream queries.
_AUDIT_STEP_NAME = "doc_extract"

# Doc-Parser routes through Anthropic Haiku, locked by the project's
# architectural decisions in CLAUDE.md.
_PROVIDER_LABEL = "anthropic"


class DocParser:
    """Structured-extraction agent for first-notice-of-loss narratives."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_loader: PromptLoader,
        settings: Settings,
        connection_factory: (
            Callable[[], AbstractContextManager[psycopg.Connection]] | None
        ) = None,
    ) -> None:
        self._provider: LLMProvider = provider
        self._prompt_loader: PromptLoader = prompt_loader
        self._settings: Settings = settings
        self._connection_factory: Callable[
            [], AbstractContextManager[psycopg.Connection]
        ] = connection_factory or self._default_connection_factory

    @classmethod
    def with_defaults(
        cls, settings: Settings, *, provider: LLMProvider
    ) -> DocParser:
        """Wire the production collaborators (`PromptLoader`, real DB connection)."""
        return cls(
            provider=provider,
            prompt_loader=PromptLoader(),
            settings=settings,
        )

    def evaluate(
        self, claim_id: UUID, correlation_id: UUID
    ) -> DocParserResult:
        """
        Run the extraction flow against a single claim. Returns a
        typed `DocParserResult`; raises `ValueError` on any
        precondition failure or parse failure, and
        `LLMProviderError` if the Gateway call itself fails. Audit
        log entries are written on every exit path.
        """
        with self._connection_factory() as conn:
            narrative = self._load_narrative(conn, claim_id)
            response, output, error, latency_ms = self._invoke_llm(narrative)
            self._write_audit(
                conn=conn,
                correlation_id=correlation_id,
                claim_id=claim_id,
                narrative=narrative,
                response=response,
                output=output,
                latency_ms=latency_ms,
                error=error,
            )

            if error is not None:
                raise error
            assert output is not None
            assert response is not None
            return DocParserResult(
                claim_id=claim_id,
                correlation_id=correlation_id,
                output=output,
                model=response.model,
                latency_ms=latency_ms,
            )

    # ------------------------------------------------------------------ #
    # Pipeline steps
    # ------------------------------------------------------------------ #

    def _load_narrative(self, conn: psycopg.Connection, claim_id: UUID) -> str:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT narrative FROM claims WHERE claim_id = %s",
                (claim_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"DocParser: claim not found in claims table; claim_id={claim_id}"
            )
        narrative = row[0]
        if not isinstance(narrative, str) or not narrative.strip():
            raise ValueError(
                "DocParser: claim narrative is empty or non-string; "
                f"claim_id={claim_id} type={type(narrative).__name__}"
            )
        return narrative

    def _invoke_llm(
        self, narrative: str
    ) -> tuple[
        ProviderResponse | None,
        DocParserOutput | None,
        BaseException | None,
        int,
    ]:
        """
        Build the prompt, call the provider, parse the output.

        Returns `(response, output, error, latency_ms)`. Either
        `output` is populated and `error` is None, or `error` is
        populated and `output` is None. `latency_ms` is measured
        across the whole call so the audit entry can report
        time-spent even on the failure paths.
        """
        system_prompt = self._prompt_loader.system("doc_parser")
        user_prompt = self._prompt_loader.user(
            "doc_parser_template",
            claim_narrative=narrative,
        )
        correlation_id = _new_correlation_id()
        t0 = time.perf_counter()
        try:
            response = self._provider.complete(
                system=system_prompt,
                user=user_prompt,
                model=self._settings.llm.anthropic.doc_parser_model,
                max_tokens=self._settings.llm.doc_parser_max_tokens,
                temperature=self._settings.llm.doc_parser_temperature,
                correlation_id=correlation_id,
                agent="doc_parser",
                step=_AUDIT_STEP_NAME,
                response_format="text",
                timeout_s=self._settings.llm.request_timeout_s,
            )
        except LLMProviderError as exc:
            return None, None, exc, int((time.perf_counter() - t0) * 1000)

        try:
            output = _parse_output(response.text)
        except ValueError as exc:
            return response, None, exc, int((time.perf_counter() - t0) * 1000)
        return response, output, None, int((time.perf_counter() - t0) * 1000)

    def _write_audit(
        self,
        *,
        conn: psycopg.Connection,
        correlation_id: UUID,
        claim_id: UUID,
        narrative: str,
        response: ProviderResponse | None,
        output: DocParserOutput | None,
        latency_ms: int,
        error: BaseException | None,
    ) -> None:
        payload = _build_audit_payload(
            claim_id=claim_id,
            narrative=narrative,
            response=response,
            output=output,
            latency_ms=latency_ms,
            error=error,
        )
        event = AuditEvent(
            correlation_id=correlation_id,
            claim_id=claim_id,
            agent="doc_parser",
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


def _parse_output(response_text: str) -> DocParserOutput:
    """
    Pull a `DocParserOutput` out of the model's text response.

    Failure modes, all surfaced as `ValueError` with the response
    excerpt embedded:
      - No `{...}` block in the response.
      - Block is not valid JSON.
      - JSON is not an object.
      - Object fails `DocParserOutput` schema validation (missing
        field, wrong type, bad date, non-positive amount, exceeded
        length).

    No retry-rescue. A misbehaving model is a hard failure; the
    audit log captures the exact response that broke parsing.
    """
    raw = _extract_json_block(response_text, agent_name="DocParser")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        excerpt_text = response_text[:500]
        raise ValueError(
            "DocParser: model response is not valid JSON; "
            f"error={exc} excerpt={excerpt_text!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            "DocParser: model response JSON is not an object; "
            f"got type={type(parsed).__name__}"
        )

    try:
        return DocParserOutput.model_validate(parsed)
    except PydanticValidationError as exc:
        raise ValueError(
            "DocParser: model response failed schema validation; "
            f"errors={exc.errors()} parsed={parsed!r}"
        ) from exc


def _build_audit_payload(
    *,
    claim_id: UUID,
    narrative: str,
    response: ProviderResponse | None,
    output: DocParserOutput | None,
    latency_ms: int,
    error: BaseException | None,
) -> dict[str, Any]:
    """Assemble the locked doc-parser-step audit payload."""
    payload: dict[str, Any] = {
        "input": {
            "claim_id": str(claim_id),
            "narrative_excerpt": _excerpt(narrative, _NARRATIVE_AUDIT_EXCERPT_CHARS),
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
        # `output.model_dump(mode="json")` returns `claimed_amount` as
        # a string, which keeps the canonical audit encoder happy
        # (Decimals are explicitly refused at that layer).
        "output": output.model_dump(mode="json") if output is not None else None,
        "error": (
            {"type": type(error).__name__, "message": str(error)}
            if error is not None
            else None
        ),
    }
    return payload
