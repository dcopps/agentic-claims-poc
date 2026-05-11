"""
Typed shapes the Validator agent exchanges with its callers.

Three layers:

  - `RetrievedChunk` — what the pgvector query produces. Carries the
    chunk's content plus the cosine *similarity* (not distance —
    converted at the retrieval layer so callers don't have to remember
    pgvector's convention).
  - `CitedChunk` — what the LLM is asked to return. Subset of
    `RetrievedChunk` carrying only the fields the model is responsible
    for, plus a `chunk_id` that must match one of the retrieved set
    (cross-checked in `Validator._parse_verdict`).
  - `ValidatorVerdict` / `ValidatorResult` — the validator's typed
    output. `ValidatorVerdict` is the JSON-shaped model the LLM
    populates; `ValidatorResult` wraps it with the retrieval context
    and latency so Phase 4's orchestrator and escalation engine can
    operate on a single typed payload.

All four shapes lock at end of Phase 2.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RetrievedChunk(BaseModel):
    """A single chunk returned by the cosine-similarity search."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    section: str = Field(min_length=1)
    content: str = Field(min_length=1)
    similarity: float = Field(ge=0.0, le=1.0)


class CitedChunk(BaseModel):
    """A citation the validator's LLM produced in its JSON response."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    section: str = Field(min_length=1)


class ValidatorVerdict(BaseModel):
    """
    Strict JSON contract for what the Validator's LLM must return.

    `cited_chunks` length is bounded so the model cannot dump the
    entire retrieved set blindly — the citation has to be selective.
    """

    model_config = ConfigDict(extra="forbid")

    covered: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1)
    policy_basis: str = Field(min_length=1)
    cited_chunks: list[CitedChunk] = Field(min_length=1, max_length=3)


class ValidatorResult(BaseModel):
    """
    Full validator output, ready for the orchestrator and the
    escalation engine downstream.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: UUID
    correlation_id: UUID
    verdict: ValidatorVerdict
    retrieved_chunks: list[RetrievedChunk] = Field(min_length=1)
    model: str = Field(min_length=1)
    latency_ms: int = Field(ge=0)
