"""
Audit canonicalisation tests — the contract between writer and verifier.

The same logical event must always produce the same bytes. Tests exercise
the locked invariants (sorted keys, no whitespace, UTC) and the guard
clauses for ambiguous types (Decimal, set, bytes).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from backend.app.audit.canonical import canonicalise
from backend.app.audit.event import AuditEvent

_FIXED_CORRELATION_ID = UUID("00000000-0000-0000-0000-000000000001")
_FIXED_CLAIM_ID = UUID("00000000-0000-0000-0000-000000000002")
_FIXED_TIME = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _event(payload: dict[str, object]) -> AuditEvent:
    return AuditEvent(
        correlation_id=_FIXED_CORRELATION_ID,
        claim_id=_FIXED_CLAIM_ID,
        agent="orchestrator",
        step="phase_start",
        payload=payload,
        created_at=_FIXED_TIME,
    )


def test_canonical_output_is_deterministic_across_payload_orderings() -> None:
    a = canonicalise(_event({"a": 1, "b": 2}))
    b = canonicalise(_event({"b": 2, "a": 1}))
    assert a == b


def test_canonical_output_has_no_whitespace() -> None:
    out = canonicalise(_event({"a": 1, "list": [1, 2, 3]}))
    text = out.decode("utf-8")
    assert " " not in text
    assert "\n" not in text


def test_canonical_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError) as excinfo:
        AuditEvent(
            correlation_id=_FIXED_CORRELATION_ID,
            claim_id=_FIXED_CLAIM_ID,
            agent="orchestrator",
            step="phase_start",
            payload={},
            created_at=datetime(2026, 5, 8, 12, 0, 0),
        )
    assert "timezone-aware" in str(excinfo.value)


def test_canonical_rejects_decimal_in_payload() -> None:
    with pytest.raises(TypeError) as excinfo:
        canonicalise(_event({"settlement": Decimal("85000.00")}))
    assert "Decimal in audit payload" in str(excinfo.value)


def test_canonical_rejects_set_in_payload() -> None:
    with pytest.raises(TypeError) as excinfo:
        canonicalise(_event({"tags": {"a", "b"}}))
    assert "ordering is undefined" in str(excinfo.value)


def test_canonical_rejects_bytes_in_payload() -> None:
    with pytest.raises(TypeError) as excinfo:
        canonicalise(_event({"blob": b"\x00\x01\x02"}))
    assert "bytes in audit payload" in str(excinfo.value)


def test_step_must_be_non_empty_after_strip() -> None:
    with pytest.raises(ValueError) as excinfo:
        AuditEvent(
            correlation_id=_FIXED_CORRELATION_ID,
            claim_id=_FIXED_CLAIM_ID,
            agent="orchestrator",
            step="   ",
            payload={},
            created_at=_FIXED_TIME,
        )
    assert "non-empty" in str(excinfo.value)
