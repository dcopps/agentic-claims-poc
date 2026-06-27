# Phase 8.5 — Test-isolation fix — REPORT

**Date:** 2026-06-27
**Prompt:** [`13-phase-8.5-test-isolation-fix.md`](13-phase-8.5-test-isolation-fix.md)
**Plan (approved):** [`13-phase-8.5-test-isolation-fix-plan.md`](13-phase-8.5-test-isolation-fix-plan.md)

## Summary

`uv run pytest` resolved its database from `.env` (which points at deployed Neon), and
the `clean_db` fixture TRUNCATEs `claims`, `audit_log`, and `policy_chunks` — so any
laptop pytest run wiped production. This is the hazard that depopulated the deployed DB
during Phase 8.4. The fix lives entirely in the test layer: the fixtures now resolve a
dedicated `TEST_DATABASE_URL`, fall back to `DATABASE_URL` only when it is non-Neon (the
CI path), and **categorically refuse to run against any `*.neon.tech` host**, converting
a silent wipe into a loud `RuntimeError` at fixture setup.

## What changed

| File | Change |
| --- | --- |
| `backend/tests/conftest.py` | New pure resolver `_resolve_test_database_url` + `_is_neon_host` + `_read_env_candidate`; `db_settings` rewritten to resolve through the guard and pin the session via `os.environ["DATABASE_URL"]`; `clean_db` gains a defence-in-depth Neon check before TRUNCATE. |
| `backend/tests/test_db_isolation.py` | **New** — three discriminator tests against the pure resolver (no DB, no side effects). |
| `.env.test.example` | **New** — documents `TEST_DATABASE_URL` and the one-time setup. |
| `.gitignore` | Added `!.env.test.example` so the template is committable (`.env.test` stays ignored). |
| `README.md` | New "Local test database setup" section. |
| `CLAUDE.md` | "Local dev environment" decision clarified (dev DB vs test DB); Current Status updated. |
| `pyproject.toml` | `0.8.4` → `0.8.5`. |

No production source touched. `Settings` is read, not modified.

## Resolution decision tree (in `_resolve_test_database_url`)

| `TEST_DATABASE_URL` | `DATABASE_URL` | Result |
| --- | --- | --- |
| set, non-Neon | (ignored) | use `TEST_DATABASE_URL` |
| set, Neon | (ignored) | **raise** (host named + README pointer) |
| unset | set, non-Neon | use `DATABASE_URL` (CI path) |
| unset | set, Neon | **raise** (the laptop foot-gun) |
| unset | unset | **raise** (missing config) |

## Design decisions

- **`os.environ` injection, not a `Settings(database=…)` kwarg.** `Settings` applies the
  named `DATABASE_URL` alias last (highest precedence), so a kwarg would be silently
  overridden by the `.env` Neon value. Setting `os.environ["DATABASE_URL"]` uses that same
  path and also covers bare `Settings()`/`open_connection()` calls made anywhere in the
  session.
- **Categorical guard, no opt-in.** No `ALLOW_…=1` bypass — that is the kind of flag that
  gets set once and forgotten. Legitimate destructive Neon maintenance uses a separate
  script, never the test suite.
- **Setup via Option A.** `scripts/setup-dev-db.sh` is reused unchanged through its
  existing `DEV_DB_NAME` parameter; no script edit.
- **No new dependency.** `python-dotenv` is already used by `settings.py`.

## Interface stability

None. Test-infrastructure only — no production code path, JSON schema, HTTP shape, SSE
event, or DB column changed. The only intended observable change is `/health` → `0.8.5`.

## Finding beyond the prompt — `.gitignore` negation

`.gitignore` has `.env.*` with *exact* negations (`!.env.example`). The new committed
`.env.test.example` was therefore ignored (`git check-ignore` confirmed). Added
`!.env.test.example`; verified the template is now committable and `.env.test` stays
ignored.

## Verification performed (in-session, safe)

- **Discriminator tests pass:** `uv run pytest backend/tests/test_db_isolation.py` → 3
  passed in 0.01s, no database touched.
- **`ruff` + `mypy` clean** on `conftest.py` and `test_db_isolation.py`.
- **Guard fires end-to-end:** running `backend/tests/test_audit_persistence.py` with the
  current Neon `.env` and no `.env.test` now **errors at `db_settings` setup with the
  guard's `RuntimeError`**, before reaching `clean_db`'s TRUNCATE. The deployed database
  is protected. Error messages use only the parsed hostname, never the full URL/password.

## Verification pending (needs the local test DB)

The full backend suite passing at **338** against `agentic_claims_test`. This requires the
one-time local setup below; I did not run the suite against a live test DB in-session (per
the agreed "I run setup, you guide" mode), and it is now impossible to run it against Neon
by accident — the guard refuses.

## Setup steps to run before the next suite run (copy-paste)

```bash
# 1. Create the local test database (reuses setup-dev-db.sh via DEV_DB_NAME)
DEV_DB_NAME=agentic_claims_test ./scripts/setup-dev-db.sh

# 2. Create .env.test from the template
cp .env.test.example .env.test

# 3. Edit .env.test → set TEST_DATABASE_URL to your local test DB
#    (substitute your Postgres user; must NOT be a .neon.tech host)
#    TEST_DATABASE_URL=postgresql://USER@localhost:5432/agentic_claims_test

# 4. Run the suite — expect 338 passing
uv run pytest
```

If `uv run pytest` is run before step 3, it now fails fast with a clear
`RuntimeError` pointing at the README — not a silent wipe.

## Issues encountered

None blocking. One observation: pytest's failure traceback dumps local variables, which
included the resolved connection string. That is pytest's own rendering, not application
output — the fix's own diagnostics deliberately surface only the parsed hostname. No
secret is written to any persistent sink by this change.

## Test counts

Before: 335 backend passing. After: **338 backend** (3 new discriminator tests; the
existing 335 unchanged and will run against the local test DB once `TEST_DATABASE_URL` is
set). Frontend unchanged (36). `ruff`/`mypy` clean.
