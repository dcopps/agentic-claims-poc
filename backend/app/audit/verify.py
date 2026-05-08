"""
Audit chain verification — recomputes every row's hashes and reports the
first break.

The verifier is the inverse of the writer. It reads the table in
`audit_id` order, reconstructs the canonical bytes from the persisted
columns, recomputes `row_hash` and `chain_hash`, and compares against
what's stored. The first row whose recomputed hash diverges from the
stored hash is the break.

Two break modes:

  - `row_hash` mismatch: the row's own content has been tampered.
  - `chain_hash` mismatch: the row's content is intact but a previous
    row's `chain_hash` (or this row's stored `prev_chain_hash`) has
    been tampered.

Either way the verifier stops at the first divergence. The full-walk
"report all breaks" variant is an optional enhancement deferred to a
later phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import psycopg

from backend.app.audit.canonical import canonicalise
from backend.app.audit.chain import (
    GENESIS_CHAIN_HASH,
    compute_chain_hash,
    compute_row_hash,
)
from backend.app.audit.event import AuditEvent

BreakKind = Literal["row_hash_mismatch", "chain_hash_mismatch"]


@dataclass(frozen=True)
class AuditBreak:
    """Where the chain first diverges and what kind of divergence it is."""

    audit_id: int
    kind: BreakKind
    expected: str
    actual: str


@dataclass(frozen=True)
class ChainVerification:
    """Verification result. `ok` is True iff `first_break is None`."""

    ok: bool
    rows_checked: int
    first_break: AuditBreak | None


def verify_chain(conn: psycopg.Connection) -> ChainVerification:
    """
    Walk the `audit_log` table in `audit_id` order; report the first break.

    Defensive ordering:
      1. Sanitise — none required; the function reads what's persisted.
      2. Validate — every row goes through `AuditEvent` reconstruction so
         a malformed payload (empty step, naive datetime) surfaces here
         even if it somehow slipped past the writer.
      3. Abort — return early on the first divergence; the caller
         decides how to escalate (alert, page, halt the pipeline).
      4. Execute — return `ChainVerification(ok=True, ...)` if no break.
    """
    expected_prev = GENESIS_CHAIN_HASH
    rows_checked = 0

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT audit_id, correlation_id, claim_id, agent, step, payload,
                   row_hash, prev_chain_hash, chain_hash, created_at
            FROM audit_log
            ORDER BY audit_id ASC
            """
        )
        for row in cur:
            (
                audit_id,
                correlation_id,
                claim_id,
                agent,
                step,
                payload,
                stored_row_hash,
                stored_prev_chain_hash,
                stored_chain_hash,
                created_at,
            ) = row

            event = AuditEvent(
                correlation_id=correlation_id,
                claim_id=claim_id,
                agent=agent,
                step=step,
                payload=payload,
                created_at=created_at,
            )

            recomputed_row_hash = compute_row_hash(canonicalise(event))
            if recomputed_row_hash != stored_row_hash:
                return ChainVerification(
                    ok=False,
                    rows_checked=rows_checked + 1,
                    first_break=AuditBreak(
                        audit_id=audit_id,
                        kind="row_hash_mismatch",
                        expected=recomputed_row_hash,
                        actual=stored_row_hash,
                    ),
                )

            recomputed_chain_hash = compute_chain_hash(
                recomputed_row_hash, expected_prev
            )
            # Two failure modes collapse here: either `prev_chain_hash`
            # was tampered, or `chain_hash` itself was tampered. We
            # report the divergence at this row; an operator inspecting
            # the surrounding rows can tell which of the two it is.
            if recomputed_chain_hash != stored_chain_hash:
                return ChainVerification(
                    ok=False,
                    rows_checked=rows_checked + 1,
                    first_break=AuditBreak(
                        audit_id=audit_id,
                        kind="chain_hash_mismatch",
                        expected=recomputed_chain_hash,
                        actual=stored_chain_hash,
                    ),
                )

            # Stored prev pointer must equal the chain we've walked. A
            # mismatch here is also a chain-hash break — surfacing it
            # explicitly makes the verifier output unambiguous.
            if stored_prev_chain_hash != expected_prev:
                return ChainVerification(
                    ok=False,
                    rows_checked=rows_checked + 1,
                    first_break=AuditBreak(
                        audit_id=audit_id,
                        kind="chain_hash_mismatch",
                        expected=expected_prev,
                        actual=stored_prev_chain_hash,
                    ),
                )

            expected_prev = stored_chain_hash
            rows_checked += 1

    return ChainVerification(ok=True, rows_checked=rows_checked, first_break=None)
