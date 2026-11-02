"""Add `mcp_tool_calls` — the record of every question an AI client asked.

Phase 10 mounts a Model Context Protocol endpoint over the audit trail. Every
tool call it serves is recorded here: which tool, with what arguments, about
which claim or run, by which caller, with what outcome and latency. This is the
"who asked what of the system" trail the DORA register points at.

**Deliberately not part of `audit_log`.** The hash chain is the record of
decisions taken on claims; questions asked *about* that record are a different
thing and must not be interleaved with it — a burst of read-only questions
would otherwise sit inside the chain of settlement decisions. This table is
plain, unchained and append-only by convention.

Additive: no existing table or column changes. The downgrade drops the table,
which discards the access record; that is acceptable only because the same
records are also written as structured log lines at call time.

Revision ID: 0003_mcp_tool_calls
Revises: 0002_audit_human_agent
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_mcp_tool_calls"
down_revision: str | None = "0002_audit_human_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE mcp_tool_calls (
            call_id      BIGSERIAL PRIMARY KEY,
            called_at    TIMESTAMPTZ NOT NULL,
            tool         TEXT NOT NULL CHECK (length(tool) > 0),
            arguments    JSONB NOT NULL,
            target_kind  TEXT NULL CHECK (target_kind IN ('claim', 'run')),
            target_id    UUID NULL,
            caller       TEXT NOT NULL CHECK (length(caller) > 0),
            outcome      TEXT NOT NULL CHECK (outcome IN ('ok', 'error')),
            error_class  TEXT NULL,
            latency_ms   INTEGER NOT NULL CHECK (latency_ms >= 0),
            -- A target id without a kind (or the reverse) is a caller bug;
            -- refuse it at the table so the record never carries half a target.
            CONSTRAINT mcp_tool_calls_target_pair
                CHECK ((target_kind IS NULL) = (target_id IS NULL))
        )
        """
    )
    op.execute("CREATE INDEX mcp_tool_calls_called_at_idx ON mcp_tool_calls (called_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mcp_tool_calls")
