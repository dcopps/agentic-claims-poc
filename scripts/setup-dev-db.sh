#!/usr/bin/env bash
# setup-dev-db.sh — one-shot local dev database bootstrap.
#
# Strategy: sanitise → validate → abort → execute.
#   1. Sanitise input  — read DEV_DB_NAME from env, trim, lowercase, validate shape.
#   2. Validate stack  — psql on PATH, server reachable, version >= 16, pgvector available.
#   3. Abort cleanly   — on any precondition failure, exit non-zero with diagnostics.
#                        Never silently fall back to a broken state.
#   4. Execute         — create the database if absent, enable pgvector, confirm.
#
# Idempotent: safe to run repeatedly. Designed for native Postgres on macOS
# (Postgres.app or Homebrew). Linux users will need to adapt the install
# instructions in README.md.

set -euo pipefail

# ─── Sanitise ────────────────────────────────────────────────────────────────

DEV_DB_NAME_RAW="${DEV_DB_NAME:-agentic_claims_dev}"
DEV_DB_NAME="$(printf '%s' "$DEV_DB_NAME_RAW" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"

# Postgres identifiers without quoting must match this shape; this is the
# stricter contract our setup script enforces so the database name is safe to
# splat into psql invocations and connection strings without escaping.
if ! [[ "$DEV_DB_NAME" =~ ^[a-z][a-z0-9_]*$ ]]; then
    echo "error: DEV_DB_NAME must match ^[a-z][a-z0-9_]*$ — got: '$DEV_DB_NAME_RAW'" >&2
    exit 2
fi

# Minimum supported Postgres major version. Locked at 16 to match the project's
# "Postgres 16+" stack reference in CLAUDE.md / BUILD-PLAN.md. The local install
# is currently postgresql@17 because the Homebrew pgvector bottle does not
# include a build for postgresql@16; both 17 and 18 satisfy the 16+ floor.
MIN_PG_MAJOR=16

# ─── Validate ────────────────────────────────────────────────────────────────

if ! command -v psql >/dev/null 2>&1; then
    cat >&2 <<'EOF'
error: psql is not on PATH.

Local dev requires native Postgres. Install via Homebrew (recommended):

    brew install postgresql@17 pgvector
    brew services start postgresql@17

Then add Postgres to your PATH (postgresql@17 is keg-only):

    export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"

Re-run this script once psql is reachable.
EOF
    exit 3
fi

if ! pg_isready -q; then
    echo "error: Postgres server is not accepting connections (pg_isready failed)." >&2
    echo "       Start it with: brew services start postgresql@17" >&2
    exit 4
fi

# Parse "psql (PostgreSQL) 17.9 (Homebrew)" → 17
PG_VERSION_LINE="$(psql --version)"
PG_MAJOR="$(printf '%s' "$PG_VERSION_LINE" | sed -nE 's/.*PostgreSQL\) ([0-9]+)\..*/\1/p')"

if [[ -z "$PG_MAJOR" ]]; then
    echo "error: could not parse Postgres major version from '$PG_VERSION_LINE'." >&2
    exit 5
fi

if (( PG_MAJOR < MIN_PG_MAJOR )); then
    echo "error: Postgres $PG_MAJOR is below the minimum supported version $MIN_PG_MAJOR." >&2
    echo "       Upgrade: brew install postgresql@17 && brew services start postgresql@17" >&2
    exit 6
fi

PGVECTOR_AVAILABLE="$(psql -d postgres -tAc \
    "SELECT 1 FROM pg_available_extensions WHERE name='vector' LIMIT 1" \
    || true)"

if [[ "$PGVECTOR_AVAILABLE" != "1" ]]; then
    cat >&2 <<EOF
error: the pgvector extension is not available to this Postgres install.

This usually means the pgvector Homebrew bottle does not ship a build for the
running Postgres major version (currently $PG_MAJOR). The bottle ships builds
only for the current and previous-current PG majors.

Fix: align your Postgres major to one of the supported versions:

    brew services stop postgresql@$PG_MAJOR
    brew install postgresql@17
    brew services start postgresql@17

Then re-run this script.
EOF
    exit 7
fi

# ─── Execute ─────────────────────────────────────────────────────────────────
# All preconditions satisfied — psql reachable, server up, version >= 16,
# pgvector available. Now create the DB if missing and enable the extension.

DB_EXISTS="$(psql -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='$DEV_DB_NAME'")"

if [[ "$DB_EXISTS" == "1" ]]; then
    echo "database '$DEV_DB_NAME' already exists — skipping createdb."
else
    createdb "$DEV_DB_NAME"
    echo "created database '$DEV_DB_NAME'."
fi

psql -d "$DEV_DB_NAME" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
PGVECTOR_INSTALLED_VERSION="$(psql -d "$DEV_DB_NAME" -tAc \
    "SELECT extversion FROM pg_extension WHERE extname='vector'")"

echo
echo "✔ dev database ready"
echo "  database:        $DEV_DB_NAME"
echo "  postgres:        $PG_VERSION_LINE"
echo "  pgvector:        $PGVECTOR_INSTALLED_VERSION"
