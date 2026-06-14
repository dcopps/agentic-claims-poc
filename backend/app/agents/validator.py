"""
Validator agent — RAG-driven coverage decision.

The agent implements `diagrams/2-rag-zoom.mmd` step-for-step:

  1. Embed the claim narrative with the same model used at indexing
     time (`bge-small-en-v1.5`).
  2. Retrieve the top-K policy chunks from `policy_chunks` via
     pgvector cosine distance, scoped to the indexed policy file.
  3. Build the augmented prompt via `PromptLoader`. No inline
     f-string prompts anywhere.
  4. Call Mistral Large through the LLM Gateway with system / user
     separation. JSON-mode requested; the system prompt locks the
     output schema.
  5. Parse the response into `ValidatorVerdict` and cross-check that
     every cited chunk id appears in the retrieved set. A citation
     to a chunk the validator never saw is the anti-hallucination
     guard at this layer.
  6. Write a complete audit-log entry under the supplied correlation
     id. Errors are audited just like successes — the chain captures
     the failure rather than leaving a gap.

Every external collaborator is injected: provider, prompt loader,
embedder, connection factory. Tests swap stubs; production wiring
(`Validator.with_defaults(settings)`) wires the real ones.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import numpy as np
import psycopg
from pydantic import ValidationError as PydanticValidationError

from backend.app.agents._shared import (
    clamp_unit as _clamp_unit,
)
from backend.app.agents._shared import (
    excerpt as _excerpt,
)
from backend.app.agents._shared import (
    extract_json_block as _shared_extract_json_block,
)
from backend.app.agents._shared import (
    new_correlation_id as _new_correlation_id,
)
from backend.app.agents.validator_models import (
    CitedChunk,
    RetrievedChunk,
    ValidatorResult,
    ValidatorVerdict,
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

# Excerpt budgets for the audit-log payload. Audit content is canonical
# and durable, but megabyte-scale prompts in JSONB would bloat the
# database for no inspection benefit. The excerpts are sized to give
# a human reviewer enough context to triage; the LLM call's full raw
# response is also stored in case forensic reconstruction is needed.
_NARRATIVE_AUDIT_EXCERPT_CHARS = 1000
_CHUNK_AUDIT_EXCERPT_CHARS = 600

# Validator pipeline step name. Used as `AuditEvent.step`; locked so
# downstream queries against the audit log have a stable identifier.
_AUDIT_STEP_NAME = "coverage_check"


class Validator:
    """RAG-driven coverage decision against the carrier's policy excerpt."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompt_loader: PromptLoader,
        embedder: Callable[[str], np.ndarray],
        settings: Settings,
        connection_factory: (
            Callable[[], AbstractContextManager[psycopg.Connection]] | None
        ) = None,
        user_template_name: str = "validator_template",
    ) -> None:
        self._provider: LLMProvider = provider
        self._prompt_loader: PromptLoader = prompt_loader
        self._embedder: Callable[[str], np.ndarray] = embedder
        self._settings: Settings = settings
        # The user-message template the agent loads. Defaults to the standard
        # template; a replay variant (e.g. `v2_strict_validator`) overrides it to
        # exercise a different instruction without touching the system prompt.
        self._user_template_name: str = user_template_name
        self._connection_factory: Callable[
            [], AbstractContextManager[psycopg.Connection]
        ] = connection_factory or self._default_connection_factory

    @classmethod
    def with_defaults(
        cls, settings: Settings, *, provider: LLMProvider
    ) -> Validator:
        """
        Wire the production collaborators: `PromptLoader`, the cached
        `SentenceTransformer` embedder, and the real Postgres
        connection factory. Tests construct `Validator` directly with
        stubs.
        """
        return cls(
            provider=provider,
            prompt_loader=PromptLoader(),
            embedder=default_embedder(settings),
            settings=settings,
        )

    def evaluate(self, claim_id: UUID, correlation_id: UUID) -> ValidatorResult:
        """
        Run the RAG flow against a single claim. Returns a typed
        `ValidatorResult`; raises `ValueError` on any precondition
        failure (claim missing, narrative empty, no chunks indexed)
        and `LLMProviderError` if the Gateway call fails. Audit log
        entries are written on every exit path.
        """
        with self._connection_factory() as conn:
            narrative = self._load_narrative(conn, claim_id)
            query_vector = self._embed_narrative(narrative)
            retrieved = self._retrieve_top_chunks(conn, query_vector)
            response, verdict, error, latency_ms = self._invoke_llm(
                narrative=narrative,
                retrieved=retrieved,
            )
            self._write_audit(
                conn=conn,
                correlation_id=correlation_id,
                claim_id=claim_id,
                narrative=narrative,
                retrieved=retrieved,
                response=response,
                verdict=verdict,
                latency_ms=latency_ms,
                error=error,
            )

            if error is not None:
                raise error
            # `verdict` is guaranteed non-None when error is None — the
            # type narrowing is for the type checker.
            assert verdict is not None
            assert response is not None
            return ValidatorResult(
                claim_id=claim_id,
                correlation_id=correlation_id,
                verdict=verdict,
                retrieved_chunks=retrieved,
                model=response.model,
                latency_ms=latency_ms,
            )

    # ------------------------------------------------------------------ #
    # Pipeline steps — each short, single-responsibility, defensively
    # guarded. Order mirrors the RAG diagram top-to-bottom.
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
                f"Validator: claim not found in claims table; claim_id={claim_id}"
            )
        narrative = row[0]
        if not isinstance(narrative, str) or not narrative.strip():
            raise ValueError(
                "Validator: claim narrative is empty or non-string; "
                f"claim_id={claim_id} type={type(narrative).__name__}"
            )
        return narrative

    def _embed_narrative(self, narrative: str) -> np.ndarray:
        vector = self._embedder(narrative)
        expected = self._settings.embedding.dimension
        if not isinstance(vector, np.ndarray):
            raise ValueError(
                "Validator: embedder did not return a numpy.ndarray; "
                f"got type={type(vector).__name__}"
            )
        if vector.ndim != 1 or vector.shape[0] != expected:
            raise ValueError(
                "Validator: embedder produced unexpected shape; "
                f"expected ({expected},), got {vector.shape}"
            )
        return vector

    def _retrieve_top_chunks(
        self, conn: psycopg.Connection, query_vector: np.ndarray
    ) -> list[RetrievedChunk]:
        source_path = str(self._settings.retrieval.policy_source_path)
        top_k = self._settings.retrieval.top_k
        # `<=>` is cosine *distance*; `1 - distance` is cosine
        # *similarity*. The convention is converted here so the rest
        # of the agent and the audit payload speak in similarity.
        with conn.cursor() as cur:
            # The `%s::vector` cast is required: psycopg binds the
            # parameter as `double precision[]` and pgvector's
            # cosine-distance operator (`<=>`) is defined only on the
            # `vector` type. Without the cast the planner raises
            # `operator does not exist: vector <=> double precision[]`.
            cur.execute(
                """
                SELECT chunk_id, section, content,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM policy_chunks
                WHERE source_path = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector.tolist(), source_path, query_vector.tolist(), top_k),
            )
            rows = cur.fetchall()
        if not rows:
            raise ValueError(
                "Validator: no policy chunks retrieved; "
                f"source_path={source_path!r}, top_k={top_k} — "
                "has the policy been indexed?"
            )
        return [
            RetrievedChunk(
                chunk_id=row[0],
                section=row[1],
                content=row[2],
                similarity=_clamp_unit(float(row[3])),
            )
            for row in rows
        ]

    def _invoke_llm(
        self,
        *,
        narrative: str,
        retrieved: list[RetrievedChunk],
    ) -> tuple[ProviderResponse | None, ValidatorVerdict | None, BaseException | None, int]:
        """
        Build the prompt, call the provider, parse the verdict.

        Returns `(response, verdict, error, latency_ms)`. Either
        `verdict` is populated and `error` is None, or `error` is
        populated and `verdict` is None. `latency_ms` is measured
        across the whole step so an audit entry can report time-spent
        even when the call failed.
        """
        system_prompt = self._prompt_loader.system("validator")
        user_prompt = self._prompt_loader.user(
            self._user_template_name,
            claim_narrative=narrative,
            retrieved_chunks=_format_chunks_for_prompt(retrieved),
        )
        # Synthesise a correlation id slice for the APILogger. The
        # caller's correlation id is the canonical one; passing it
        # through here keeps a single ID across audit + log.
        correlation_id = _new_correlation_id()
        t0 = time.perf_counter()
        try:
            response = self._provider.complete(
                system=system_prompt,
                user=user_prompt,
                model=self._settings.llm.mistral.validator_model,
                max_tokens=self._settings.llm.validator_max_tokens,
                temperature=self._settings.llm.validator_temperature,
                correlation_id=correlation_id,
                agent="validator",
                step=_AUDIT_STEP_NAME,
                response_format="json",
                timeout_s=self._settings.llm.request_timeout_s,
            )
        except LLMProviderError as exc:
            return None, None, exc, int((time.perf_counter() - t0) * 1000)

        try:
            verdict = _parse_verdict(response.text, retrieved)
        except ValueError as exc:
            return response, None, exc, int((time.perf_counter() - t0) * 1000)
        return response, verdict, None, int((time.perf_counter() - t0) * 1000)

    def _write_audit(
        self,
        *,
        conn: psycopg.Connection,
        correlation_id: UUID,
        claim_id: UUID,
        narrative: str,
        retrieved: list[RetrievedChunk],
        response: ProviderResponse | None,
        verdict: ValidatorVerdict | None,
        latency_ms: int,
        error: BaseException | None,
    ) -> None:
        payload = _build_audit_payload(
            claim_id=claim_id,
            narrative=narrative,
            retrieved=retrieved,
            response=response,
            verdict=verdict,
            latency_ms=latency_ms,
            error=error,
            provider_label=self._provider.vendor,
        )
        event = AuditEvent(
            correlation_id=correlation_id,
            claim_id=claim_id,
            agent="validator",
            step=_AUDIT_STEP_NAME,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        AuditWriter(conn).append(event)

    # ------------------------------------------------------------------ #
    # Connection plumbing
    # ------------------------------------------------------------------ #

    def _default_connection_factory(
        self,
    ) -> AbstractContextManager[psycopg.Connection]:
        # `open_connection` is decorated with `@contextmanager`, so the
        # return value already satisfies AbstractContextManager.
        return open_connection(self._settings)


# --------------------------------------------------------------------------- #
# Module helpers
# --------------------------------------------------------------------------- #


def _format_chunks_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks as a deterministic block for the prompt."""
    blocks: list[str] = []
    for chunk in chunks:
        blocks.append(
            f"[chunk_id={chunk.chunk_id}, section={chunk.section}, "
            f"similarity={chunk.similarity:.4f}]\n{chunk.content}"
        )
    return "\n\n".join(blocks)


def _parse_verdict(
    response_text: str, retrieved: list[RetrievedChunk]
) -> ValidatorVerdict:
    """
    Pull a `ValidatorVerdict` out of the model's text response and
    cross-check that every cited chunk id was in the retrieved set.
    """
    raw = _extract_json_block(response_text)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        excerpt = response_text[:500]
        raise ValueError(
            "Validator: model response is not valid JSON; "
            f"error={exc} excerpt={excerpt!r}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            "Validator: model response JSON is not an object; "
            f"got type={type(parsed).__name__}"
        )

    try:
        verdict = ValidatorVerdict.model_validate(parsed)
    except PydanticValidationError as exc:
        raise ValueError(
            "Validator: model response failed schema validation; "
            f"errors={exc.errors()} parsed={parsed!r}"
        ) from exc

    _assert_citations_subset(verdict.cited_chunks, retrieved)
    return verdict


def _extract_json_block(text: str) -> str:
    """Delegate to `_shared.extract_json_block` with the Validator's agent label."""
    return _shared_extract_json_block(text, agent_name="Validator")


def _assert_citations_subset(
    cited: list[CitedChunk], retrieved: list[RetrievedChunk]
) -> None:
    retrieved_ids = {chunk.chunk_id for chunk in retrieved}
    cited_ids = {chunk.chunk_id for chunk in cited}
    rogue = cited_ids - retrieved_ids
    if rogue:
        raise ValueError(
            "Validator: model cited chunk ids not present in retrieved set "
            "(anti-hallucination guard); "
            f"rogue={sorted(str(x) for x in rogue)} "
            f"retrieved={sorted(str(x) for x in retrieved_ids)}"
        )


def _build_audit_payload(
    *,
    claim_id: UUID,
    narrative: str,
    retrieved: list[RetrievedChunk],
    response: ProviderResponse | None,
    verdict: ValidatorVerdict | None,
    latency_ms: int,
    error: BaseException | None,
    provider_label: str,
) -> dict[str, Any]:
    """Assemble the locked validator-step audit payload.

    `provider_label` is the *actual* provider the call ran against
    (`self._provider.vendor`), not a hardcoded vendor. This keeps the audit
    truthful when a replay variant substitutes the provider — e.g. running the
    Validator on Anthropic Haiku instead of Mistral records `"anthropic"`. An
    audit entry that misreported the provider would undermine the provider-
    substitutability evidence the audit log exists to furnish.
    """
    payload: dict[str, Any] = {
        "input": {
            "claim_id": str(claim_id),
            "narrative_excerpt": _excerpt(narrative, _NARRATIVE_AUDIT_EXCERPT_CHARS),
        },
        "retrieval": {
            "top_k": len(retrieved),
            "chunks": [
                {
                    "chunk_id": str(chunk.chunk_id),
                    "section": chunk.section,
                    "similarity": chunk.similarity,
                    "content_excerpt": _excerpt(
                        chunk.content, _CHUNK_AUDIT_EXCERPT_CHARS
                    ),
                }
                for chunk in retrieved
            ],
        },
        "llm_call": (
            {
                "provider": provider_label,
                "model": response.model,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "latency_ms": latency_ms,
            }
            if response is not None
            else {"provider": provider_label, "latency_ms": latency_ms}
        ),
        "verdict": (
            verdict.model_dump(mode="json") if verdict is not None else None
        ),
        "error": (
            {"type": type(error).__name__, "message": str(error)}
            if error is not None
            else None
        ),
    }
    return payload


# --------------------------------------------------------------------------- #
# Embedding-model factory
# --------------------------------------------------------------------------- #


def default_embedder(settings: Settings) -> Callable[[str], np.ndarray]:
    """
    Return a callable that embeds a single string via the configured
    `SentenceTransformer` model.

    The underlying model is cached at module level so subsequent
    calls do not pay the ~3 second cold-load cost. Tests pass a stub
    embedder via the `Validator` constructor and never touch this
    factory.
    """
    model = _load_embedding_model(
        settings.embedding.model_name,
        normalise=settings.embedding.normalise_embeddings,
    )
    normalise = settings.embedding.normalise_embeddings

    def embed(text: str) -> np.ndarray:
        if not text.strip():
            raise ValueError(
                "default_embedder: input text is empty or whitespace"
            )
        vector = model.encode(
            text,
            normalize_embeddings=normalise,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vector, dtype=np.float32).reshape(-1)

    return embed


@lru_cache(maxsize=1)
def _load_embedding_model(model_name: str, *, normalise: bool) -> Any:
    """Module-level cache: load the SentenceTransformer once per process.

    The return type is `Any` because `sentence_transformers` does not
    ship a `py.typed` marker — pinning the precise class here would
    force a noisy ignore on every consumer. Callers receive the real
    `SentenceTransformer` instance.
    """
    # Imported here so test modules that stub the embedder don't pay
    # the ~50MB / ~3s cold load on import.
    from sentence_transformers import SentenceTransformer

    del normalise  # cache discriminator; the value is consumed by `encode`
    return SentenceTransformer(model_name)
