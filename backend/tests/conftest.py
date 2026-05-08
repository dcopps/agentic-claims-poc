"""
Shared pytest fixtures.

Phase 0 contributed `client` (a `TestClient` over a fresh FastAPI app);
Phase 1 adds three database-backed fixtures:

  - `db_settings` — a `Settings()` instance, validated. Required for any
    test that touches Postgres so a missing `DATABASE_URL` surfaces as a
    clear collection-time error rather than a buried connection failure.
  - `migrated_db` (session-scoped) — runs `alembic upgrade head` once
    against the configured database. Subsequent tests inherit the
    schema; rerunning is a no-op because Alembic tracks state.
  - `clean_db` (function-scoped) — yields a connection to the migrated
    database with `claims`, `audit_log`, and `policy_chunks` truncated.
    Each test starts from an empty state.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.db.connection import open_connection
from backend.settings import Settings


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """A TestClient bound to a fresh app instance per test."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def db_settings() -> Settings:
    """
    Resolve Settings once per test session.

    Phase 1 makes `database.url` required; instantiating fails fast if
    `DATABASE_URL` is unset, which surfaces as a single readable error
    rather than a flood of connection refusals from later fixtures.
    """
    return Settings()


@pytest.fixture(scope="session")
def migrated_db(db_settings: Settings) -> Settings:
    """
    Ensure migrations are applied to the configured database.

    Runs `alembic upgrade head` from the repo root. Idempotent: a
    repeat run is a no-op because Alembic stamps `alembic_version`.
    """
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    # Propagate the resolved DATABASE_URL so Alembic's env.py picks up
    # the same value Settings did (matters when Settings sourced it from
    # `.env` rather than the shell).
    env["DATABASE_URL"] = db_settings.database.url.get_secret_value()

    result = subprocess.run(
        ["uv", "run", "alembic", "--config", "backend/alembic.ini", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head failed during test session setup; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return db_settings


@pytest.fixture()
def clean_db(migrated_db: Settings) -> Iterator[psycopg.Connection]:
    """
    Yield a fresh connection with all Phase 1 tables truncated.

    `RESTART IDENTITY` resets the `audit_log.audit_id` sequence so
    chain-hash assertions across tests aren't sensitive to the order
    pytest happens to pick.
    """
    with open_connection(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE policy_chunks, audit_log, claims "
                "RESTART IDENTITY CASCADE"
            )
        conn.commit()
        yield conn
