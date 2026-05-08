"""
Audit event model — the typed input to `AuditWriter.append`.

The event captures the four invariants every audit row must carry: the
correlation id (one per claim pipeline run), the claim id (FK target),
the agent that produced the event, and the named step within that agent.
The payload is freeform JSON; the validator rejects the shapes the
canonicaliser cannot deterministically encode (see `canonical.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Locked enumeration of agent identifiers. `system` is the orchestrator-
# level identifier for events not attributable to a specific agent (e.g.
# a pipeline-start marker). Anything outside this set is a programming
# error, not a runtime input — the validator refuses early.
AgentName = Literal[
    "system",
    "doc_parser",
    "validator",
    "adjuster",
    "guardrail",
    "orchestrator",
]


class AuditEvent(BaseModel):
    """A single audit event, ready to be canonicalised and appended."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    claim_id: UUID
    agent: AgentName
    step: str = Field(min_length=1)
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("step")
    @classmethod
    def _strip_and_validate_step(cls, v: str) -> str:
        # Trim whitespace and re-check non-empty so "  " can't pass.
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("AuditEvent.step must be a non-empty, non-whitespace string")
        return cleaned

    @field_validator("created_at")
    @classmethod
    def _require_utc(cls, v: datetime) -> datetime:
        # Naive datetimes are forbidden because the canonicaliser would
        # otherwise produce identical bytes for events that occurred in
        # different timezones — a silent contract break.
        if v.tzinfo is None:
            raise ValueError(
                "AuditEvent.created_at must be timezone-aware (UTC); got naive datetime"
            )
        # Normalise to UTC. Storing a non-UTC offset round-trips through
        # ISO 8601 with the offset preserved, which would also fork the
        # canonical bytes; converting to UTC keeps the encoding stable.
        return v.astimezone(UTC)
