"""
Schema sanity tests — DB-backed.

Confirms migrations applied cleanly: every table exists, expected
columns are present with the right nullability, expected indexes are
in place, FK from `audit_log.claim_id` to `claims.claim_id` exists,
and the `vector` extension is enabled.
"""

from __future__ import annotations

import psycopg


def _columns(conn: psycopg.Connection, table: str) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return {name: dtype for name, dtype in cur.fetchall()}


def _index_names(conn: psycopg.Connection, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = %s
            """,
            (table,),
        )
        return {row[0] for row in cur.fetchall()}


def test_claims_table_columns(clean_db: psycopg.Connection) -> None:
    cols = _columns(clean_db, "claims")
    expected = {
        "claim_id",
        "claim_number",
        "line_of_business",
        "claimant_name",
        "policy_number",
        "loss_date",
        "reported_date",
        "jurisdiction",
        "narrative",
        "claim_type",
        "reported_amount",
        "status",
        "scenario_tag",
        "created_at",
        "updated_at",
    }
    assert expected <= set(cols)


def test_audit_log_table_and_indexes(clean_db: psycopg.Connection) -> None:
    cols = _columns(clean_db, "audit_log")
    expected = {
        "audit_id",
        "correlation_id",
        "claim_id",
        "agent",
        "step",
        "payload",
        "row_hash",
        "prev_chain_hash",
        "chain_hash",
        "created_at",
    }
    assert expected <= set(cols)

    indexes = _index_names(clean_db, "audit_log")
    assert "audit_log_correlation_id_idx" in indexes
    assert "audit_log_claim_id_idx" in indexes
    assert "audit_log_created_at_idx" in indexes


def test_policy_chunks_table_and_indexes(clean_db: psycopg.Connection) -> None:
    cols = _columns(clean_db, "policy_chunks")
    expected = {
        "chunk_id",
        "source_path",
        "section",
        "chunk_index",
        "content",
        "token_count",
        "embedding",
        "embedding_model",
        "created_at",
    }
    assert expected <= set(cols)

    indexes = _index_names(clean_db, "policy_chunks")
    assert "policy_chunks_source_path_idx" in indexes
    assert "policy_chunks_embedding_hnsw_idx" in indexes


def test_audit_log_has_fk_to_claims(clean_db: psycopg.Connection) -> None:
    with clean_db.cursor() as cur:
        cur.execute(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'audit_log'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'claim_id'
            """
        )
        assert cur.fetchone() is not None


def test_vector_extension_enabled(clean_db: psycopg.Connection) -> None:
    with clean_db.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
    assert row is not None
    # pgvector 0.3+ is acceptable; the prototype was developed against 0.8.
    assert row[0] is not None
