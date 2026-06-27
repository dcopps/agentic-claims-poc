# Phase 8.5 — Test-isolation fix

## Context

During Phase 8.4 verification we found a serious structural hazard: running `uv run pytest` against the repo destructively truncates whatever database `.env`'s `DATABASE_URL` points at. Because the project's local `.env` is configured to point at the deployed Neon production database for convenience during local development, this means **any pytest invocation on a developer's laptop can wipe production data** — `claims`, `audit_log`, and `policy_chunks` all get truncated.

This is exactly what happened during the Phase 8.4 test runs. Claude Code's accountability report after the repopulation confirmed: the four new `test_audit_persistence.py` regression tests, depending on the `clean_db` fixture, executed `TRUNCATE TABLE policy_chunks, audit_log, claims RESTART IDENTITY CASCADE` and committed against the Neon production database. The Phase 8.4 tests passed locally but the cost was production state.

This is **not** caused by Phase 8.4 specifically. The `clean_db` fixture has always done this; the bare `Settings()` in `db_settings` has always resolved to whatever `.env` says. Phase 8.4 was simply when the suite happened to run in that configuration after production state mattered. Any future developer or Claude Code session running `pytest` on the repo as-is would reproduce the wipe. The latent hazard has been there since Phase 1 when the database fixtures were written.

## Current state — verified by reading `backend/tests/conftest.py` and `.github/workflows/ci.yml`

| Fact | Evidence |
| --- | --- |
| `db_settings` is bare `Settings()` — resolves `DATABASE_URL` from env or `.env` | `conftest.py:57-66` |
| `migrated_db` propagates that URL to Alembic | `conftest.py:69-96` |
| `clean_db` runs `TRUNCATE … RESTART IDENTITY CASCADE` and commits | `conftest.py:99-115` |
| No guard against destructive operations on a `.neon.tech` host | `conftest.py` — absent |
| Local `.env` `DATABASE_URL` points at deployed Neon | Confirmed by Phase 8.4 investigation |
| CI is unaffected — uses an in-workflow Postgres service container | `.github/workflows/ci.yml:13-32` (`DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agentic_claims_test`) |
| Setup script already supports parameterised DB name | `scripts/setup-dev-db.sh:19` (`DEV_DB_NAME` env var) |

CI cannot wipe Neon — it has no Neon credentials and runs against its own throwaway service-container Postgres. The hazard is local-development-only.

## Plan-first

Before writing any code, produce a written plan in `docs/prompts/13-phase-8.5-test-isolation-fix-plan.md` covering:

1. **Files to modify** — `backend/tests/conftest.py` is the only existing source file change. New files: `backend/tests/test_db_isolation.py` (discriminator tests), `.env.test.example` (convention doc). Setup script may or may not need modification depending on the approach chosen (see point 4). Confirm by inspection.

2. **Approach — recommended and rejected alternatives.** Document the design space with reasoning:
   - **Recommended:** introduce a new `TEST_DATABASE_URL` env var, read preferentially by `db_settings` in `conftest.py`. Fall back to `DATABASE_URL` only if it does NOT end in `.neon.tech`. Add a guard in `clean_db` (and any other destructive fixture) that inspects the resolved URL host and raises loudly if it is a `.neon.tech` host — fail-loud, no opt-in, no environment-variable bypass.
   - **Alternative rejected — modify production `Settings` model to add `database.test_url`:** rejected because Settings is production code and shouldn't be polluted with test concerns. The test override belongs in `conftest.py`.
   - **Alternative rejected — provide an `ALLOW_DESTRUCTIVE_TESTS_AGAINST_NEON=1` opt-in:** rejected because environment-variable opt-ins are exactly the kind of thing that gets accidentally set and forgotten. The guard should be categorical: tests never run destructive ops against a `.neon.tech` host. If a developer needs to do destructive maintenance against Neon for some legitimate one-off reason, they run a separate maintenance script, not the test suite.
   - **Alternative rejected — guard inside production `open_connection` or `AuditWriter`:** rejected because that puts test-only safety in production code. The guard belongs in the test fixture layer.

3. **Settings resolution logic in `db_settings`** — document the exact decision tree:
   - If `TEST_DATABASE_URL` is set AND its host does not end in `.neon.tech` → use it.
   - If `TEST_DATABASE_URL` is set AND its host ends in `.neon.tech` → raise with a clear diagnostic explaining why and pointing at the README setup section.
   - If `TEST_DATABASE_URL` is unset AND `DATABASE_URL` is set AND its host does not end in `.neon.tech` → use `DATABASE_URL` (this is the CI path — CI sets `DATABASE_URL` to a localhost Postgres in its workflow, no `TEST_DATABASE_URL` needed).
   - If `TEST_DATABASE_URL` is unset AND `DATABASE_URL` is set AND its host ends in `.neon.tech` → raise with a clear diagnostic explaining why and pointing at the README setup section.
   - If both are unset → raise with a clear diagnostic.

4. **Setup script approach.** Two options to choose between in the plan, with reasoning for the chosen one:
   - **Option A:** developer invokes `scripts/setup-dev-db.sh` once for the dev DB, then again with `DEV_DB_NAME=agentic_claims_test` for the test DB. The script already supports this via the existing `DEV_DB_NAME` env var (`scripts/setup-dev-db.sh:19`). Document in the README.
   - **Option B:** modify `scripts/setup-dev-db.sh` to also create the test DB on a single invocation (new `--include-test-db` flag or always-create-both behaviour).
   - I lean toward **Option A** because it reuses the existing script unchanged and the convention is documentable in a single README sentence. Make the case in the plan.

5. **Documentation updates** — list each file to touch:
   - `README.md` — add a "Local test database setup" section
   - `CLAUDE.md` — update the "Local dev environment" entry under Architectural Decisions to clarify dev DB vs test DB
   - `.env.test.example` — new file documenting the `TEST_DATABASE_URL` convention; include the recommended local value (`postgresql://USER@localhost:5432/agentic_claims_test`)
   - `.gitignore` — confirm `.env.test` is covered by the existing `.env*` pattern (no change needed if so; add explicitly if not)

6. **Risks** — atomicity, CI compatibility, developer onboarding friction. The recommended approach should be free of CI risk because CI's `DATABASE_URL` already targets a non-Neon localhost Postgres, which the fallback path accepts. Local developers see a one-time setup cost (create the test DB, set `TEST_DATABASE_URL` in their `.env.test`).

7. **Interface stability** — none. This is a test-infrastructure change. No production code paths touched, no JSON schema or HTTP shape changes, no DB column changes. Acknowledge explicitly in the plan that no public-facing contract is touched.

8. **Discriminator test design — `backend/tests/test_db_isolation.py`** — three tests proving the guard fires correctly:
   - **Test 1 (guard fires on Neon):** with `TEST_DATABASE_URL` set to a `.neon.tech` URL, calling the resolution helper raises `RuntimeError` with a diagnostic message naming the host. The test asserts both the exception type and that the message mentions the host.
   - **Test 2 (guard allows local):** with `TEST_DATABASE_URL` set to a localhost URL, the resolution helper returns the URL unchanged.
   - **Test 3 (missing config — clear diagnostic):** with both `TEST_DATABASE_URL` and `DATABASE_URL` unset (or both pointing at Neon), the resolution helper raises with a message pointing at the README setup section.
   These tests must be runnable without a real database (they exercise the resolution logic in isolation). They are the proof that the safety property holds; they should fail if anyone reverts the guard in future.

9. **Version bump** — `pyproject.toml` `0.8.4` → `0.8.5` so a successful redeploy is detectable from `/health`.

10. **Verification steps after the change is committed** — confirm:
    - The full backend test suite still passes (`uv run pytest`) when `TEST_DATABASE_URL` is set to a local test database.
    - The full backend test suite raises a clear error (not a silent wipe) when `TEST_DATABASE_URL` is unset and `DATABASE_URL` points at Neon.
    - CI still passes (no CI workflow changes should be needed).
    - `/health` reports `0.8.5` once Render redeploys.

Wait for explicit confirmation of the plan before writing any code.

## Deliverables (after plan is approved)

1. `backend/tests/conftest.py` — `db_settings` resolution rewritten with the four-branch decision tree above; `clean_db` (and any other destructive fixture) inspects the resolved URL and raises loudly if the host is `.neon.tech`.
2. `backend/tests/test_db_isolation.py` — three discriminator tests proving the guard fires.
3. `.env.test.example` — new file documenting the `TEST_DATABASE_URL` convention and the recommended local value.
4. `README.md` — new "Local test database setup" section explaining: install Postgres (already documented), run `DEV_DB_NAME=agentic_claims_test ./scripts/setup-dev-db.sh` to create the test DB, copy `.env.test.example` to `.env.test` and set `TEST_DATABASE_URL`.
5. `CLAUDE.md` — update the "Local dev environment" architectural-decision entry to clarify dev DB vs test DB; update the "Current Status" section before the final commit.
6. `.gitignore` — confirm `.env.test` is excluded (add explicitly if the existing `.env*` pattern does not cover it).
7. `pyproject.toml` — version bump to `0.8.5`.
8. `docs/build-log.md` — Phase 8.5 entry documenting root cause, the fix, what would have broken without the fix, test counts before and after, and the verification steps performed.
9. `docs/prompts/13-phase-8.5-test-isolation-fix-report.md` — the standard post-execution report.

## Test pass-rate target

Before/after: 335 backend tests passing → 338 backend tests passing (the three new discriminator tests). The existing 335 must continue to pass once `TEST_DATABASE_URL` is set correctly on the local dev machine. If any existing test breaks because it was implicitly depending on writes against the production DB persisting beyond the test boundary, that's a test-isolation bug being correctly exposed and must be fixed before the change ships.

Frontend tests are unchanged.

## Setup steps the developer (Dermot) will need to run before re-running the suite

Document these explicitly in the report so the next test-suite run doesn't immediately fail with a "TEST_DATABASE_URL unset" error:

1. Create the test database:
   ```
   DEV_DB_NAME=agentic_claims_test ./scripts/setup-dev-db.sh
   ```
2. Create `.env.test` from the template:
   ```
   cp .env.test.example .env.test
   ```
3. Edit `.env.test` to set `TEST_DATABASE_URL` to the local test DB URL (e.g., `postgresql://USER@localhost:5432/agentic_claims_test`, substituting the right user).

The report should include the verbatim commands so the user can copy-paste.

## Standing project conventions

Honour `CLAUDE.md`'s standing instructions throughout — defensive ordering (sanitise → validate → abort → execute), no silent fallbacks, function size limits (30-line prompt to reconsider, 50-line hard limit), settings hierarchy (defaults → settings.yaml → CLI → env vars), externalised prompts, system/user separation, frequent commits with descriptive messages, push after every logical unit of work, security discipline (no secrets in code), dependency discipline (flag any new dependency in the plan and wait for confirmation), interface stability acknowledgement.
