"""Initial schema — claims, audit_log, policy_chunks.

Phase 1 creates the persistent foundation in a single migration:

  - The `vector` extension (pgvector) so the embedding column can be
    declared `VECTOR(384)`.
  - `claims` — the system-of-record table the React UI submits to.
  - `audit_log` — the tamper-evident chain. Hash columns are CHAR(64) to
    pin the SHA-256 hex length and let Postgres reject mistakes at the
    storage layer.
  - `policy_chunks` — the vector index, one row per chunk of the policy
    excerpt indexed by `bge-small-en-v1.5`.

All schema is hand-written SQL via `op.execute(...)`. No ORM models are
declared; the runtime app uses raw psycopg.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Extension first — vector type is referenced by `policy_chunks` below.
    # Idempotent so re-applying against a Neon DB that already has it is
    # a no-op rather than a hard failure.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE claims (
            claim_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            claim_number       TEXT         NOT NULL UNIQUE,
            line_of_business   TEXT         NOT NULL DEFAULT 'Commercial Property',
            claimant_name      TEXT         NOT NULL,
            policy_number      TEXT         NOT NULL,
            loss_date          DATE         NOT NULL,
            reported_date      DATE         NOT NULL,
            jurisdiction       TEXT         NOT NULL,
            narrative          TEXT         NOT NULL,
            claim_type         TEXT         NOT NULL,
            reported_amount    NUMERIC(14,2) NOT NULL CHECK (reported_amount > 0),
            status             TEXT         NOT NULL DEFAULT 'received'
                CHECK (status IN (
                    'received',
                    'extracted',
                    'coverage_verified',
                    'estimated',
                    'guardrail_checked',
                    'settled',
                    'awaiting_human'
                )),
            scenario_tag       TEXT         NULL
                CHECK (scenario_tag IS NULL OR scenario_tag IN (
                    'auto_approve',
                    'threshold_escalation',
                    'guardrail_escalation'
                )),
            created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX claims_status_idx ON claims (status)")
    op.execute("CREATE INDEX claims_scenario_tag_idx ON claims (scenario_tag)")

    op.execute(
        """
        CREATE TABLE audit_log (
            audit_id          BIGSERIAL    PRIMARY KEY,
            correlation_id    UUID         NOT NULL,
            claim_id          UUID         NOT NULL REFERENCES claims(claim_id),
            agent             TEXT         NOT NULL
                CHECK (agent IN (
                    'system',
                    'doc_parser',
                    'validator',
                    'adjuster',
                    'guardrail',
                    'orchestrator'
                )),
            step              TEXT         NOT NULL CHECK (length(step) > 0),
            payload           JSONB        NOT NULL,
            row_hash          CHAR(64)     NOT NULL,
            prev_chain_hash   CHAR(64)     NOT NULL,
            chain_hash        CHAR(64)     NOT NULL,
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX audit_log_correlation_id_idx ON audit_log (correlation_id)")
    op.execute("CREATE INDEX audit_log_claim_id_idx ON audit_log (claim_id)")
    op.execute("CREATE INDEX audit_log_created_at_idx ON audit_log (created_at)")

    op.execute(
        """
        CREATE TABLE policy_chunks (
            chunk_id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            source_path      TEXT         NOT NULL,
            section          TEXT         NOT NULL,
            chunk_index      INT          NOT NULL CHECK (chunk_index >= 0),
            content          TEXT         NOT NULL,
            token_count      INT          NOT NULL CHECK (token_count > 0),
            embedding        VECTOR(384)  NOT NULL,
            embedding_model  TEXT         NOT NULL,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            UNIQUE (source_path, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX policy_chunks_source_path_idx ON policy_chunks (source_path)")
    # HNSW chosen over IVFFlat: works out of the box for the prototype's
    # tens-of-rows scale, no `lists` tuning, no training pass. Cosine ops
    # because the embedding model produces normalised vectors.
    op.execute(
        "CREATE INDEX policy_chunks_embedding_hnsw_idx "
        "ON policy_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    # Drop in reverse FK order. The vector extension is intentionally NOT
    # dropped — other databases on the same server may use it.
    op.execute("DROP TABLE IF EXISTS policy_chunks")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS claims")
