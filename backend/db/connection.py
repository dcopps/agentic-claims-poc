"""
Postgres connection management.

Single source of truth for opening connections to the database. The app
gets a configured `psycopg.Connection` from `open_connection`; the same
function is used in scripts (seed, indexing) and in tests (the migrated
test schema fixture).

The `pgvector.psycopg.register_vector` adapter is registered at import
time so `vector` columns round-trip as Python lists / numpy arrays
without per-call boilerplate. Registering at module import keeps the
contract simple — every connection opened through this module
understands `vector`, no caller needs to remember to enable it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from backend.settings import Settings


@contextmanager
def open_connection(settings: Settings | None = None) -> Iterator[psycopg.Connection]:
    """
    Open a psycopg connection using the configured `DATABASE_URL`.

    Yields a connection with the pgvector type adapter registered and the
    session-level `statement_timeout` applied. The connection is closed on
    context exit; transactions are the caller's responsibility (psycopg
    autocommit is off by default — explicit `conn.commit()` or rollback).

    `settings` is injectable so tests can pass an alternative configuration
    without monkey-patching the global Settings cache.
    """
    cfg = settings or Settings()
    url = cfg.database.url.get_secret_value()
    conn = psycopg.connect(url, autocommit=False)

    try:
        # Apply session-level statement timeout. Set as a server-side
        # parameter so a runaway query at any layer (driver, ORM, raw SQL)
        # is bounded — we cannot rely on every caller to set its own.
        # Postgres `SET` does not accept parameterised values, so the
        # integer is validated to be a non-negative int and then
        # interpolated as a literal. (Pydantic already enforces `ge=0`.)
        timeout_ms = int(cfg.database.statement_timeout_ms)
        if timeout_ms < 0:
            # Defensive: should be unreachable because the Pydantic
            # field has ge=0, but the SQL boundary is the wrong place
            # for trust.
            raise ValueError(
                "statement_timeout_ms must be non-negative; "
                f"got {timeout_ms}"
            )
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {timeout_ms}")
        conn.commit()

        # Enable round-tripping of `vector` columns to Python lists /
        # numpy arrays. Must run after the extension exists in the DB,
        # which the initial migration guarantees before any application
        # code uses the connection.
        register_vector(conn)

        yield conn
    finally:
        conn.close()
