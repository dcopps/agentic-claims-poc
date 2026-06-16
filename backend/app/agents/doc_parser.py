"""
Doc-Parser agent — narrative summariser over the claim record.

Strategy (Phase 8.2): the `claims` row is the source of truth for the
structured fields. Live rehearsal showed Haiku reliably *defaults*
`loss_date`, `jurisdiction`, `claimant_identifier`, and `claimed_amount`
to placeholders rather than extracting them, tripping schema validation
and aborting the pipeline. So the agent no longer asks the model for those
fields at all.

Step-for-step:

  1. Load the full `ClaimRecord` from the `claims` table by `claim_id`
     via the injected `ClaimsRepository`. The orchestrator (Phase 4) is
     the canonical caller; isolation tests pass a stub connection factory.
  2. Build the summary prompt via `PromptLoader` — no inline f-strings.
  3. Call Claude Haiku through the LLM Gateway with system/user
     separation, asking only for a one-paragraph `narrative_summary`.
     The model returns plain prose; a length/content guard bounds it.
  4. Assemble `DocParserOutput` from the record's structured columns plus
     the model-generated summary. The shape is the locked Phase 3 contract.
  5. Write a complete audit-log entry under the supplied correlation id,
     recording `fields_source="claim_record"` so the trail says honestly
     where each field came from. Errors are audited alongside successes.

Every collaborator is constructor-injected. Tests swap stubs;
`with_defaults` wires the production graph.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

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
    new_correlation_id as _new_correlation_id,
)
from backend.app.agents.doc_parser_models import (
    DocParserOutput,
    DocParserResult,
)
from backend.app.audit import AuditEvent, AuditWriter
from backend.app.claims.models import ClaimRecord
from backend.app.claims.repository import ClaimsRepository
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

# Additive audit field (Phase 8.2): records that the structured fields were
# sourced from the claim record, not from LLM extraction. Joins the Phase 5/6/7
# additive extensions in CLAUDE.md's locked-extensions list.
_FIELDS_SOURCE = "claim_record"

# Summary bounds. The upper bound mirrors `DocParserOutput.narrative_summary`'s
# 500-char cap so the guard rejects an over-long summary with a specific message
# rather than deferring to a less precise Pydantic error.
_SUMMARY_MAX_CHARS = 500

# Probe-path sentinels. The agent test bench passes a bare narrative with no
# claim, so the structured fields have no source of truth. Rather than fabricate
# them from the narrative — the extraction this agent no longer performs — the
# probe stamps explicit sentinels and the test-bench UI labels them as such.
_PROBE_SENTINEL_LOSS_DATE = date(1970, 1, 1)
_PROBE_SENTINEL_JURISDICTION = "Unknown"
_PROBE_SENTINEL_CLAIM_TYPE = "unknown"
_PROBE_SENTINEL_CLAIMANT = "Unknown"
_PROBE_SENTINEL_CLAIMED_AMOUNT = Decimal("0.01")


class DocParser:
    """Narrative-summariser agent for first-notice-of-loss claims."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_loader: PromptLoader,
        settings: Settings,
        claims_repository: ClaimsRepository | None = None,
        connection_factory: (
            Callable[[], AbstractContextManager[psycopg.Connection]] | None
        ) = None,
    ) -> None:
        self._provider: LLMProvider = provider
        self._prompt_loader: PromptLoader = prompt_loader
        self._settings: Settings = settings
        self._claims_repository: ClaimsRepository = (
            claims_repository or ClaimsRepository()
        )
        self._connection_factory: Callable[
            [], AbstractContextManager[psycopg.Connection]
        ] = connection_factory or self._default_connection_factory

    @classmethod
    def with_defaults(
        cls, settings: Settings, *, provider: LLMProvider
    ) -> DocParser:
        """Wire the production collaborators (`PromptLoader`, repository, DB)."""
        return cls(
            provider=provider,
            prompt_loader=PromptLoader(),
            settings=settings,
            claims_repository=ClaimsRepository(),
        )

    def evaluate(
        self, claim_id: UUID, correlation_id: UUID
    ) -> DocParserResult:
        """
        Run the summary flow against a single claim. Returns a typed
        `DocParserResult`; raises `ValueError` on any precondition or
        summary-guard failure, and `LLMProviderError` if the Gateway
        call itself fails. Audit log entries are written on every exit
        path that reaches the model call (a missing claim raises before
        any audit, as it did before the refactor).
        """
        with self._connection_factory() as conn:
            record = self._load_claim_record(conn, claim_id)
            response, summary, error, latency_ms, prompt = self._invoke_llm(
                record.narrative
            )
            # The structured fields always come from the record; only the
            # summary is model-derived, so the output exists iff the summary did.
            output = (
                _output_from_record(record, summary) if summary is not None else None
            )
            self._write_audit(
                conn=conn,
                correlation_id=correlation_id,
                claim_id=claim_id,
                narrative=record.narrative,
                response=response,
                output=output,
                latency_ms=latency_ms,
                error=error,
                prompt=prompt,
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

    def parse(self, narrative: str) -> tuple[DocParserOutput, ProbeMetadata]:
        """
        Run the summary LLM step on a raw narrative — no audit, no claim.

        The agent-test-bench path: build the prompt, call the model, validate the
        summary, and return a `DocParserOutput` whose structured fields are
        sentinels (there is no claim record to read) and whose `narrative_summary`
        is the real model output. The only side effect is the APILogger record
        `provider.complete` emits. `evaluate` is the audit-writing, claim-bound
        counterpart; this reuses its core (`_invoke_llm`) so the two cannot drift.
        """
        response, summary, error, latency_ms, _prompt = self._invoke_llm(narrative)
        if error is not None:
            raise error
        assert response is not None and summary is not None
        return _probe_output(summary), probe_metadata(response, latency_ms)

    # ------------------------------------------------------------------ #
    # Pipeline steps
    # ------------------------------------------------------------------ #

    def _load_claim_record(
        self, conn: psycopg.Connection, claim_id: UUID
    ) -> ClaimRecord:
        """
        Read the claim row, or abort. The record is the source of truth for the
        structured fields; a missing row is a caller error (the orchestrator
        persists the claim before firing the pipeline). An empty narrative is
        rejected here because the summary call has nothing to work from.
        """
        record = self._claims_repository.get(conn, claim_id)
        if record is None:
            raise ValueError(
                f"DocParser: claim not found in claims table; claim_id={claim_id}"
            )
        if not record.narrative.strip():
            raise ValueError(
                "DocParser: claim narrative is empty or whitespace; "
                f"claim_id={claim_id}"
            )
        return record

    def _invoke_llm(
        self, narrative: str
    ) -> tuple[
        ProviderResponse | None, str | None, BaseException | None, int, CapturedPrompt
    ]:
        """
        Build the summary prompt, call the provider, validate the prose.

        Returns `(response, summary, error, latency_ms, prompt)`. Either `summary`
        is a validated string and `error` is None, or `error` is populated and
        `summary` is None. `latency_ms` is measured across the whole call so the
        audit entry can report time-spent on the failure paths too. `prompt` is the
        literal text sent to the model; it is built before the call, so it is
        returned on every path — including the provider-exception path — letting the
        audit capture what was sent even when no response came back.
        """
        system_prompt = self._prompt_loader.system("doc_parser")
        user_prompt = self._prompt_loader.user(
            "doc_parser_template",
            claim_narrative=narrative,
        )
        prompt = CapturedPrompt(system=system_prompt, user=user_prompt)
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
            return None, None, exc, int((time.perf_counter() - t0) * 1000), prompt

        try:
            summary = _validate_summary(response.text)
        except ValueError as exc:
            return response, None, exc, int((time.perf_counter() - t0) * 1000), prompt
        return response, summary, None, int((time.perf_counter() - t0) * 1000), prompt

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
        prompt: CapturedPrompt | None,
    ) -> None:
        payload = _build_audit_payload(
            claim_id=claim_id,
            narrative=narrative,
            response=response,
            output=output,
            latency_ms=latency_ms,
            error=error,
            prompt=prompt,
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


def _validate_summary(response_text: str) -> str:
    """
    Validate Haiku's plain-prose summary. Sanitise → validate → abort → return.

    The model now returns prose, not JSON, so there is nothing to parse — only to
    bound. Both failure modes raise `ValueError` with the offending text:
      - Empty or whitespace-only: the model produced no summary.
      - Longer than the `DocParserOutput` cap: rejected here with the length and
        an excerpt, rather than deferring to a less specific Pydantic error.
    """
    summary = response_text.strip()
    if not summary:
        raise ValueError(
            "DocParser: model returned an empty or whitespace-only summary; "
            f"excerpt={response_text[:500]!r}"
        )
    if len(summary) > _SUMMARY_MAX_CHARS:
        raise ValueError(
            f"DocParser: model summary exceeds the {_SUMMARY_MAX_CHARS}-character "
            f"cap; got {len(summary)} chars; excerpt={summary[:500]!r}"
        )
    return summary


def _output_from_record(
    record: ClaimRecord, narrative_summary: str
) -> DocParserOutput:
    """
    Assemble the Doc-Parser output from the claim record plus the LLM summary.

    This is the single place the column→field mapping lives, so the two name
    differences — `reported_amount`→`claimed_amount` and
    `claimant_name`→`claimant_identifier` — cannot drift across call sites. The
    structured values come from an already-validated `ClaimRecord`; only
    `narrative_summary` originates with the model, and it is pre-validated by
    `_validate_summary`.
    """
    return DocParserOutput(
        loss_date=record.loss_date,
        jurisdiction=record.jurisdiction,
        claim_type=record.claim_type,
        claimed_amount=record.reported_amount,
        claimant_identifier=record.claimant_name,
        narrative_summary=narrative_summary,
    )


def _probe_output(narrative_summary: str) -> DocParserOutput:
    """
    Assemble a probe-path output: real LLM summary, sentinel structured fields.

    The test bench has no claim record, so the structured fields have no source
    of truth; the sentinels are honest placeholders the UI labels explicitly.
    """
    return DocParserOutput(
        loss_date=_PROBE_SENTINEL_LOSS_DATE,
        jurisdiction=_PROBE_SENTINEL_JURISDICTION,
        claim_type=_PROBE_SENTINEL_CLAIM_TYPE,
        claimed_amount=_PROBE_SENTINEL_CLAIMED_AMOUNT,
        claimant_identifier=_PROBE_SENTINEL_CLAIMANT,
        narrative_summary=narrative_summary,
    )


def _build_audit_payload(
    *,
    claim_id: UUID,
    narrative: str,
    response: ProviderResponse | None,
    output: DocParserOutput | None,
    latency_ms: int,
    error: BaseException | None,
    prompt: CapturedPrompt | None,
) -> dict[str, Any]:
    """Assemble the locked doc-parser-step audit payload.

    `fields_source` is the Phase 8.2 additive field: it records that the
    structured fields came from the claim record, not from LLM extraction. The
    `output` block carries the full field set as before; the `llm_call` block now
    reflects a call that produced only `narrative_summary`, and (Phase 8.3) carries
    the literal `prompt` that was sent.
    """
    payload: dict[str, Any] = {
        "input": {
            "claim_id": str(claim_id),
            "narrative_excerpt": _excerpt(narrative, _NARRATIVE_AUDIT_EXCERPT_CHARS),
        },
        # Honest provenance: the structured fields are sourced from the claim
        # record; only the summary is model-derived.
        "fields_source": _FIELDS_SOURCE,
        "llm_call": attach_prompt(
            {
                "provider": _PROVIDER_LABEL,
                "model": response.model,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "latency_ms": latency_ms,
            }
            if response is not None
            else {"provider": _PROVIDER_LABEL, "latency_ms": latency_ms},
            prompt,
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
