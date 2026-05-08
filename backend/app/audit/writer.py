"""
AuditWriter — appends an event to the audit log, computes the hashes,
and serialises concurrent writers via a transaction-scoped advisory lock.

Defensive ordering throughout `append`:
  1. Sanitise — Pydantic has already typed the event; we trust nothing
     else and convert `payload` through the canonicaliser to surface any
     non-JSON-safe values BEFORE opening a transaction.
  2. Validate — open the transaction, take the advisory lock, read the
     latest chain hash, confirm the FK target claim exists.
  3. Abort — raise `ValueError` (or `TypeError` from the canonicaliser)
     with diagnostic context. Transaction rolls back on the way out.
  4. Execute — INSERT, commit.

The advisory lock is keyed to a single integer (`_AUDIT_LOCK_KEY`) so
every writer waits behind the same mutex while reading the previous
chain hash and inserting. Without it, two concurrent writers could each
read the same `prev_chain_hash` and produce a fork.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from backend.app.audit.canonical import canonicalise
from backend.app.audit.chain import (
    GENESIS_CHAIN_HASH,
    compute_chain_hash,
    compute_row_hash,
)
from backend.app.audit.event import AuditEvent

# Advisory-lock key. Arbitrary 32-bit integer — the value doesn't matter
# as long as every writer in the application uses the same one. Picked
# from the high end of the int32 range to reduce the chance of collision
# with any other ad-hoc advisory locks the application might add later.
_AUDIT_LOCK_KEY: int = 0x4144_4954  # ASCII "ADIT"

# Maximum bytes of a payload we'll quote in error messages. Full payloads
# can be megabytes; a five-hundred-character excerpt is enough to tell
# the operator what went wrong without flooding the log.
_PAYLOAD_EXCERPT_BYTES: int = 500


@dataclass(frozen=True)
class AuditRow:
    """The persisted row, returned to the caller for downstream linking."""

    audit_id: int
    correlation_id: UUID
    claim_id: UUID
    agent: str
    step: str
    payload: dict[str, Any]
    row_hash: str
    prev_chain_hash: str
    chain_hash: str
    created_at: datetime


class AuditWriter:
    """Appends `AuditEvent` instances to the audit log."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def append(self, event: AuditEvent) -> AuditRow:
        """
        Append `event`; return the persisted `AuditRow`.

        Raises `ValueError` on any precondition failure (missing claim,
        canonicalisation refusal). The connection is left in a clean
        state on every exit path: success commits, failure rolls back.
        """
        # Sanitise — re-canonicalise NOW so any payload-shape failure
        # surfaces before we open a transaction. The canonical bytes also
        # become the input to `compute_row_hash` below; computing them
        # twice would be wasteful.
        canonical_bytes = canonicalise(event)
        row_hash = compute_row_hash(canonical_bytes)

        try:
            with self._conn.transaction(), self._conn.cursor() as cur:
                # Take the advisory lock. Released automatically at
                # transaction end. Without this, two concurrent
                # writers could each read the same prev_chain_hash
                # and fork the chain.
                cur.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (_AUDIT_LOCK_KEY,),
                )

                # Validate — claim FK exists. Same transaction means
                # a concurrent delete cannot race past us; the FK
                # itself is the storage-layer backstop.
                cur.execute(
                    "SELECT 1 FROM claims WHERE claim_id = %s",
                    (event.claim_id,),
                )
                if cur.fetchone() is None:
                    raise ValueError(
                        "AuditWriter: claim_id not found in claims table; "
                        f"claim_id={event.claim_id} step={event.step!r} "
                        f"payload_excerpt={_excerpt_payload(canonical_bytes)!r}"
                    )

                # Read the previous chain hash under the same lock.
                # `FOR UPDATE` is unnecessary because the advisory
                # lock already serialises access; ORDER BY audit_id
                # DESC LIMIT 1 returns the genesis sentinel when the
                # table is empty.
                cur.execute(
                    "SELECT chain_hash FROM audit_log "
                    "ORDER BY audit_id DESC LIMIT 1"
                )
                last = cur.fetchone()
                prev_chain_hash = (
                    last[0] if last is not None else GENESIS_CHAIN_HASH
                )

                chain_hash = compute_chain_hash(row_hash, prev_chain_hash)

                # Execute — single INSERT...RETURNING so we round-trip
                # the persisted row in one statement.
                cur.execute(
                    """
                        INSERT INTO audit_log (
                            correlation_id, claim_id, agent, step, payload,
                            row_hash, prev_chain_hash, chain_hash, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING audit_id, created_at
                        """,
                    (
                        event.correlation_id,
                        event.claim_id,
                        event.agent,
                        event.step,
                        Jsonb(event.payload),
                        row_hash,
                        prev_chain_hash,
                        chain_hash,
                        event.created_at,
                    ),
                )
                persisted = cur.fetchone()
                if persisted is None:
                    # Should be impossible — RETURNING always yields
                    # one row on a successful INSERT. Surfacing the
                    # impossibility loudly is preferable to silently
                    # returning a half-constructed AuditRow.
                    raise RuntimeError(
                        "AuditWriter: INSERT...RETURNING produced no row"
                    )
                audit_id, created_at = persisted

            return AuditRow(
                audit_id=audit_id,
                correlation_id=event.correlation_id,
                claim_id=event.claim_id,
                agent=event.agent,
                step=event.step,
                payload=event.payload,
                row_hash=row_hash,
                prev_chain_hash=prev_chain_hash,
                chain_hash=chain_hash,
                created_at=created_at,
            )
        except psycopg.errors.ForeignKeyViolation as exc:
            # Defence in depth — the explicit SELECT above catches a
            # missing claim, but a concurrent delete could in principle
            # slip past. Re-raise as ValueError so callers handle one
            # exception type at the API boundary.
            raise ValueError(
                f"AuditWriter: foreign key violation on claim_id={event.claim_id}; "
                "the referenced claim was deleted between validation and insert"
            ) from exc


def _excerpt_payload(canonical_bytes: bytes) -> str:
    """Return up to `_PAYLOAD_EXCERPT_BYTES` of the canonical encoding."""
    if len(canonical_bytes) <= _PAYLOAD_EXCERPT_BYTES:
        return canonical_bytes.decode("utf-8", errors="replace")
    truncated = canonical_bytes[:_PAYLOAD_EXCERPT_BYTES].decode("utf-8", errors="replace")
    return f"{truncated}…(truncated, full size={len(canonical_bytes)} bytes)"
