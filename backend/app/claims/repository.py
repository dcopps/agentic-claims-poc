"""
ClaimsRepository — persistence for the claims system-of-record.

Connection-scoped, like `AuditWriter`: every method takes a `psycopg.Connection`
the caller owns, so the repository never decides transaction or connection
lifetime. Writes run inside `conn.transaction()` (commit on success, rollback on
error); reads do not open a transaction.

Defensive throughout: `update_status` validates the target value before touching
the database, and a write that affects zero rows (a claim that vanished) raises
rather than silently succeeding.
"""

from __future__ import annotations

from typing import Any, get_args
from uuid import UUID, uuid4

import psycopg

from backend.app.claims.models import ClaimRecord, ClaimStatus, ClaimSubmission

# The columns every read/write round-trips, in a fixed order so the row-to-model
# mapping has a single source of truth.
_COLUMNS = (
    "claim_id, claim_number, line_of_business, claimant_name, policy_number, "
    "loss_date, reported_date, jurisdiction, narrative, claim_type, "
    "reported_amount, status, scenario_tag, created_at, updated_at"
)

# The set of valid status values, derived from the Literal so it cannot drift
# from the type (or the DB CHECK, which mirrors the same seven values).
_VALID_STATUSES: frozenset[str] = frozenset(get_args(ClaimStatus))

# Bounds for the list endpoint's page size. Below 1 is meaningless; the upper
# bound keeps a single response from scanning the whole table.
_MIN_LIST_LIMIT = 1
_MAX_LIST_LIMIT = 200


class ClaimsRepository:
    """Insert, read, list, and status-update operations on `claims`."""

    @staticmethod
    def insert(conn: psycopg.Connection, submission: ClaimSubmission) -> ClaimRecord:
        """
        Persist a submitted claim with `status='received'` and return the row.

        `claim_id` and `claim_number` are generated server-side; the claim number
        embeds the new id so the UNIQUE constraint cannot be tripped by two
        submissions in the same second.
        """
        claim_id = uuid4()
        claim_number = f"CLM-{submission.reported_date.year}-{claim_id.hex[:8].upper()}"
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO claims (
                    claim_id, claim_number, claimant_name, policy_number,
                    loss_date, reported_date, jurisdiction, narrative,
                    claim_type, reported_amount, scenario_tag
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_COLUMNS}
                """,
                (
                    claim_id,
                    claim_number,
                    submission.claimant_name,
                    submission.policy_number,
                    submission.loss_date,
                    submission.reported_date,
                    submission.jurisdiction,
                    submission.narrative,
                    submission.claim_type,
                    submission.reported_amount,
                    submission.scenario_tag,
                ),
            )
            row = cur.fetchone()
        # RETURNING always yields one row on a successful INSERT; the guard keeps
        # the type checker honest and surfaces the impossible loudly.
        if row is None:
            raise RuntimeError("ClaimsRepository: INSERT...RETURNING produced no row")
        return _row_to_record(row)

    @staticmethod
    def get(conn: psycopg.Connection, claim_id: UUID) -> ClaimRecord | None:
        """Return the claim, or None if no row matches."""
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNS} FROM claims WHERE claim_id = %s", (claim_id,)
            )
            row = cur.fetchone()
        return _row_to_record(row) if row is not None else None

    @staticmethod
    def list_claims(
        conn: psycopg.Connection,
        *,
        limit: int,
        status: ClaimStatus | None = None,
    ) -> list[ClaimRecord]:
        """Return claims most-recent-first, optionally filtered by status."""
        if not _MIN_LIST_LIMIT <= limit <= _MAX_LIST_LIMIT:
            raise ValueError(
                f"ClaimsRepository.list_claims: limit must be in "
                f"[{_MIN_LIST_LIMIT}, {_MAX_LIST_LIMIT}]; got {limit}"
            )
        where = ""
        params: list[Any] = []
        if status is not None:
            where = "WHERE status = %s"
            params.append(status)
        params.append(limit)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLUMNS} FROM claims {where} "
                "ORDER BY created_at DESC LIMIT %s",
                tuple(params),
            )
            rows = cur.fetchall()
        return [_row_to_record(row) for row in rows]

    @staticmethod
    def update_status(
        conn: psycopg.Connection, claim_id: UUID, status: str
    ) -> None:
        """
        Set the claim's status and bump `updated_at`.

        Validates the value against the allowed set before the write — an unknown
        status is a caller error, surfaced with the valid set, not deferred to the
        DB CHECK. A write affecting zero rows means the claim is gone; that raises.
        """
        if status not in _VALID_STATUSES:
            raise ValueError(
                "ClaimsRepository.update_status: unknown status "
                f"{status!r}; valid values are {sorted(_VALID_STATUSES)}"
            )
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                "UPDATE claims SET status = %s, updated_at = now() "
                "WHERE claim_id = %s",
                (status, claim_id),
            )
            if cur.rowcount == 0:
                raise ValueError(
                    "ClaimsRepository.update_status: claim not found; "
                    f"claim_id={claim_id}"
                )


def _row_to_record(row: tuple[Any, ...]) -> ClaimRecord:
    """Map a `_COLUMNS`-ordered row tuple to a typed `ClaimRecord`."""
    return ClaimRecord(
        claim_id=row[0],
        claim_number=row[1],
        line_of_business=row[2],
        claimant_name=row[3],
        policy_number=row[4],
        loss_date=row[5],
        reported_date=row[6],
        jurisdiction=row[7],
        narrative=row[8],
        claim_type=row[9],
        reported_amount=row[10],
        status=row[11],
        scenario_tag=row[12],
        created_at=row[13],
        updated_at=row[14],
    )
