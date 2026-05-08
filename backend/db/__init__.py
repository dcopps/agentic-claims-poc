"""
Database package — Postgres connection management and migration tooling.

Phase 1 introduces this package as the single source of truth for how the
backend talks to Postgres. The runtime app uses `psycopg` directly via
`connection.open_connection`; Alembic uses the same `Settings` to read
`DATABASE_URL`. There is no ORM layer.
"""
