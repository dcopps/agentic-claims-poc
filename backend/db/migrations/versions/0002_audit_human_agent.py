"""Extend audit_log.agent with 'human' and claims.status with 'aborted'.

Phase 6 introduces a human-in-the-loop decision step. Two schema extensions
support it:

  1. **audit_log agent CHECK** gains `'human'`. A reviewer's approve/reject is
     written as an audit entry with `agent='human'`, so the *who* and *why* live
     in the tamper-evident ledger alongside the agents' entries.
  2. **claims status CHECK** gains `'aborted'`. A human *rejection* moves the
     claim to a terminal `aborted` status (approval moves it to `settled`). The
     original CHECK (migration 0001) enumerated the seven lifecycle values but
     not `aborted` — that value existed only as a *pipeline* outcome, never a
     claim status — so a rejected claim needs it added here. (No `human_approved`
     / `human_rejected` claim statuses: the *reason* lives in the audit entry; the
     claim's terminal status is the existing `settled` / `aborted`.)

Forward-only in practice: the downgrade re-adds the narrower CHECKs, which FAIL if
any `human` audit rows or `aborted` claims already exist (Postgres validates the
new constraint against existing data). That failure is correct — the ledger is
append-only and a rejected claim's status is real data — so the downgrade documents
it rather than working around it.

Revision ID: 0002_audit_human_agent
Revises: 0001_initial_schema
Create Date: 2026-06-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_audit_human_agent"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Agent CHECK values, per direction.
_AGENT_SEVEN = (
    "'system', 'doc_parser', 'validator', 'adjuster', 'guardrail', "
    "'orchestrator', 'human'"
)
_AGENT_SIX = (
    "'system', 'doc_parser', 'validator', 'adjuster', 'guardrail', 'orchestrator'"
)

# claims.status CHECK values, per direction.
_STATUS_EIGHT = (
    "'received', 'extracted', 'coverage_verified', 'estimated', "
    "'guardrail_checked', 'settled', 'awaiting_human', 'aborted'"
)
_STATUS_SEVEN = (
    "'received', 'extracted', 'coverage_verified', 'estimated', "
    "'guardrail_checked', 'settled', 'awaiting_human'"
)


def upgrade() -> None:
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_agent_check")
    op.execute(
        f"ALTER TABLE audit_log ADD CONSTRAINT audit_log_agent_check "
        f"CHECK (agent IN ({_AGENT_SEVEN}))"
    )
    op.execute("ALTER TABLE claims DROP CONSTRAINT claims_status_check")
    op.execute(
        f"ALTER TABLE claims ADD CONSTRAINT claims_status_check "
        f"CHECK (status IN ({_STATUS_EIGHT}))"
    )


def downgrade() -> None:
    # Re-adding the narrower CHECKs fails if any `human` audit rows or `aborted`
    # claims exist — Postgres validates the constraint against current data. That
    # is the intended, loud failure: we do not delete ledger entries or rewrite a
    # rejected claim's status to make a downgrade succeed.
    op.execute("ALTER TABLE claims DROP CONSTRAINT claims_status_check")
    op.execute(
        f"ALTER TABLE claims ADD CONSTRAINT claims_status_check "
        f"CHECK (status IN ({_STATUS_SEVEN}))"
    )
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_agent_check")
    op.execute(
        f"ALTER TABLE audit_log ADD CONSTRAINT audit_log_agent_check "
        f"CHECK (agent IN ({_AGENT_SIX}))"
    )
