# Phase 8.5 — Test-isolation fix — PLAN

Status: awaiting confirmation. No code written yet.

## Problem (re-verified against source)

| Fact | Evidence |
| --- | --- |
| `db_settings` is bare `Settings()` — resolves `DATABASE_URL` from env/`.env` | `conftest.py:57-66` |
| `migrated_db` propagates that URL to Alembic | `conftest.py:69-96` |
| `clean_db` runs `TRUNCATE … RESTART IDENTITY CASCADE` and commits | `conftest.py:108-114` |
| `clean_db` is the **only** destructive fixture | grep: sole `TRUNCATE`/`DELETE`/`DROP` in `conftest.py` is line 111 |
| No `.neon.tech` guard anywhere in the fixtures | absent |
| Local `.env` `DATABASE_URL` → deployed Neon | confirmed Phase 8.4; host `…neon.tech` |
| CI sets `DATABASE_URL` to localhost Postgres, no `TEST_DATABASE_URL` | `ci.yml:32` |
| `python-dotenv` already a dependency | `settings.py:30` (`from dotenv import dotenv_values`) |
| Settings applies named `DATABASE_URL` alias **last** (highest precedence) | `settings.py:475-498` |

Running `uv run pytest` resolves `db_settings` → `Settings()` → `.env` → Neon, and
`clean_db` then TRUNCATEs Neon. Any pytest run on a laptop whose `.env` points at Neon
wipes production. That is what happened in Phase 8.4.

## 1. Files to modify

| File | Change |
| --- | --- |
| `backend/tests/conftest.py` | Rewrite `db_settings` with the four-branch resolution + Neon guard; add a defensive Neon guard in `clean_db`. New pure helpers `_resolve_test_database_url` / `_is_neon_host`. |
| `backend/tests/test_db_isolation.py` | **New** — three discriminator tests against the pure resolver (no DB needed). |
| `.env.test.example` | **New** — documents `TEST_DATABASE_URL` with the recommended local value. |
| `.gitignore` | Add `!.env.test.example` negation (see finding below). |
| `README.md` | New "Local test database setup" section. |
| `CLAUDE.md` | Clarify dev DB vs test DB in the "Local dev environment" decision; update Current Status. |
| `pyproject.toml` | `0.8.4` → `0.8.5`. |
| `docs/build-log.md` | Phase 8.5 entry. |
| `docs/prompts/13-phase-8.5-test-isolation-fix-report.md` | **New** — post-execution report. |

`scripts/setup-dev-db.sh` is **not** modified (Option A — see point 4).

### Finding not in the prompt — `.gitignore` needs a new negation

`.gitignore` has `.env.*` with *exact* negations `!.env.example`, `!frontend/.env.example`.
`.env.test` is correctly ignored. But the **new committed** `.env.test.example` is also
matched by `.env.*` and no negation covers it (`git check-ignore .env.test.example`
confirms it is ignored). So deliverable 6 needs one extra line — `!.env.test.example` —
or the template can't be committed. Folding that into the `.gitignore` change.

## 2. Approach — recommended and rejected

**Recommended:** a `TEST_DATABASE_URL` env var, read preferentially by `db_settings`,
with a categorical `.neon.tech` guard. The resolver is a **pure function** taking the two
candidate URL strings and returning a safe URL or raising — so the discriminator tests
exercise it with no DB and no env mutation. `db_settings` reads the two candidates
(`TEST_DATABASE_URL` from env/`.env.test`, `DATABASE_URL` from env/`.env`), calls the
resolver, then injects the result via `os.environ["DATABASE_URL"]` before constructing
`Settings()`.

*Why `os.environ` injection rather than an init kwarg:* Settings applies the named
`DATABASE_URL` alias last (`settings.py:497`), so `Settings(database=…)` as a kwarg would
be silently overridden by the `.env` Neon value. Setting `os.environ["DATABASE_URL"]`
uses the existing highest-precedence path, and has the bonus that *any* bare
`open_connection()`/`Settings()` constructed during the session also targets the test DB —
closing the hazard for code paths that don't take an explicit settings object.

**Rejected — add `database.test_url` to the production `Settings` model:** pollutes
production code with a test-only concern. The override belongs in `conftest.py`.

**Rejected — `ALLOW_DESTRUCTIVE_TESTS_AGAINST_NEON=1` opt-in:** an env-var bypass is
exactly what gets set once and forgotten. The guard must be categorical. Legitimate
destructive Neon maintenance uses a separate script, never the test suite.

**Rejected — guard inside production `open_connection`/`AuditWriter`:** puts test-only
safety in production code. The guard belongs in the fixture layer.

## 3. `db_settings` resolution decision tree

Encoded in the pure helper `_resolve_test_database_url(test_url, database_url) -> str`:

| `TEST_DATABASE_URL` | `DATABASE_URL` | Result |
| --- | --- | --- |
| set, host **not** `.neon.tech` | (ignored) | **use `TEST_DATABASE_URL`** |
| set, host **is** `.neon.tech` | (ignored) | **raise** `RuntimeError` naming the host + README pointer |
| unset | set, host **not** `.neon.tech` | **use `DATABASE_URL`** (the CI path) |
| unset | set, host **is** `.neon.tech` | **raise** `RuntimeError` naming the host + README pointer |
| unset | unset | **raise** `RuntimeError` — missing config + README pointer |

Host test via `_is_neon_host(url)` = `urlparse(url).hostname` endswith `.neon.tech`
(case-insensitive). Defensive ordering: sanitise (parse), validate (host check), abort
(raise with diagnostic), execute (return). No silent fallback. Every raise names what was
found and points at the README "Local test database setup" section.

## 4. Setup-script approach — Option A (chosen)

The developer runs `scripts/setup-dev-db.sh` twice — once for the dev DB, once with
`DEV_DB_NAME=agentic_claims_test` for the test DB. The script already parameterises the
name (`setup-dev-db.sh:19`), so **no script change** is needed and the convention is one
README sentence. Option B (a `--include-test-db` flag) adds script surface area and a
second code path to maintain for zero benefit over a documented invocation. Chosen A.

## 5. Documentation updates

- `README.md` — "Local test database setup": create the test DB
  (`DEV_DB_NAME=agentic_claims_test ./scripts/setup-dev-db.sh`), copy
  `.env.test.example` → `.env.test`, set `TEST_DATABASE_URL`.
- `CLAUDE.md` — "Local dev environment" decision clarified to name two databases
  (`agentic_claims_dev` for the app, `agentic_claims_test` for pytest) and the
  `TEST_DATABASE_URL` + Neon-guard rule; Current Status updated before the final commit.
- `.env.test.example` — new, documents `TEST_DATABASE_URL` with recommended value
  `postgresql://USER@localhost:5432/agentic_claims_test`.
- `.gitignore` — `.env.test` already covered by `.env.*`; add `!.env.test.example` so the
  template is committable (see finding above).

## 6. Risks

- **CI compatibility:** none. CI sets `DATABASE_URL` to a localhost host and no
  `TEST_DATABASE_URL`, which is exactly the third branch (use `DATABASE_URL`). No workflow
  change. I will re-confirm by reading `ci.yml` after the change.
- **Hidden cross-test persistence dependency:** if any of the 335 existing tests
  implicitly relied on Neon-resident data surviving across the test boundary, it will now
  fail against the fresh local test DB. That would be a test-isolation bug correctly
  exposed; per the pass-rate target it must be fixed before shipping. Expected risk low —
  `clean_db` truncates per-test, so tests already seed their own data.
- **Onboarding friction:** one-time local cost (create test DB, set `TEST_DATABASE_URL`).
  Documented verbatim in the README and the report.
- **Atomicity:** unaffected — no production transaction code touched.

## 7. Interface stability

**None.** Test-infrastructure only. No production code path, JSON schema, HTTP shape, SSE
event, or DB column changes. `Settings` is read, not modified. The `/health` version
string moves to `0.8.5` (intended redeploy signal). Explicitly: no public-facing contract
is touched.

## 8. Discriminator tests — `backend/tests/test_db_isolation.py`

Three tests against the pure `_resolve_test_database_url`, no DB required:

1. **Guard fires on Neon:** `_resolve_test_database_url("postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/db", None)`
   raises `RuntimeError`; assert the type and that the message contains the host.
2. **Guard allows local:** `_resolve_test_database_url("postgresql://u@localhost:5432/agentic_claims_test", None)`
   returns the URL unchanged.
3. **Missing/Neon-only config:** both `None` (and, as a second case, `TEST` unset +
   `DATABASE_URL` Neon) raises `RuntimeError` whose message points at the README setup
   section.

These fail if anyone reverts the guard. They are the proof the safety property holds.

## 9. Version bump

`pyproject.toml` `0.8.4` → `0.8.5`. `/health` resolves from package metadata, so a
successful redeploy reports `0.8.5`. `test_health.py` asserts only a non-empty string —
stays green.

## 10. Verification after the change

1. Full backend suite passes with `TEST_DATABASE_URL` set to a local test DB → target
   **338 passing** (335 + 3 discriminator).
2. With `TEST_DATABASE_URL` unset and `DATABASE_URL` → Neon, the suite raises a clear
   `RuntimeError` at fixture setup — **not** a silent wipe. I will demonstrate this
   explicitly (the discriminator tests cover the logic; I'll also confirm the fixture
   path raises).
3. CI green — no workflow change (third branch accepts CI's localhost `DATABASE_URL`).
4. `/health` reports `0.8.5` once Render redeploys.

## Test pass-rate target

335 → 338 backend passing. The existing 335 must pass once `TEST_DATABASE_URL` points at a
local test DB. Any breakage from a hidden production-persistence dependency is a real
isolation bug to fix before shipping. Frontend unchanged.

## Developer setup before the next suite run (will be in the report verbatim)

```
DEV_DB_NAME=agentic_claims_test ./scripts/setup-dev-db.sh
cp .env.test.example .env.test
# edit .env.test → TEST_DATABASE_URL=postgresql://USER@localhost:5432/agentic_claims_test
```
