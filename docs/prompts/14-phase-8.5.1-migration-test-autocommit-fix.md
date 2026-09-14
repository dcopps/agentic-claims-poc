# Phase 8.5.1 — Migration-test autocommit fix — PROMPT + DIAGNOSTIC + PLAN

This file combines the session prompt with the diagnostic and fix plan that
answered it. Phase 8.5.1 began as an investigation ("what is the most recent
activity on this project?" → "run the suite"), not as a pre-written phase
prompt, so the diagnostic *is* the plan and they are archived together.

---

## Prompt (verbatim)

> what is the most recent activity on this project?

then, after the suite was offered:

> yes

then, after the diagnostic and proposed fix were presented:

> Go. Proceed with the fix as proposed, plus the self-checking post-assertion
> (the SELECT 1 FROM pg_constraint … assert cur.fetchone() is not None block).
> That's a small, cheap piece of insurance and it turns the test into a genuine
> discriminator against DDL-leak-out-of-transaction regressions rather than only
> against constraint-refuses-to-re-add.
>
> Version treatment: point release. Bump pyproject.toml 0.8.5 → 0.8.5.1 and
> update /health accordingly. This establishes the naming pattern for future
> small hotfixes and makes the deployed state distinguishable from raw Phase 8.5.
>
> Standing protocol applies: archive your diagnostic + fix plan to
> docs/prompts/14-phase-8.5.1-migration-test-autocommit-fix.md, drop the
> execution report at
> docs/prompts/14-phase-8.5.1-migration-test-autocommit-fix-report.md, append a
> Phase 8.5.1 entry to docs/build-log.md covering root cause + the two-piece fix
> + the self-checking assertion + why CI missed it, update CLAUDE.md's Current
> Status to reflect the new version and phase, and commit + push as one clean
> logical unit.
>
> Also fold in the diagnostic-quality context in the build-log entry: preserve
> the three insight points verbatim (CI-immunity via ephemeral containers; test
> passes while doing damage; TRUNCATE covers rows not DDL). Those are
> load-bearing lessons for whoever hits the next test-suite regression — they
> explain why the bug was invisible for so long, which is more valuable than
> just documenting the fix.
>
> The empty agentic_claims_dev observation stays out of scope. Logged as a
> separate future item; do not fold in.
>
> Expected test count after fix: 336 → 338 passing (the two failing tests now
> pass) + 7 skipped, matching what CLAUDE.md claimed pre-hotfix. Report the
> actual final count in the build-log so the discrepancy is closed.

---

## How the problem surfaced

Phase 8.5 left one item pending: Dermot to create the local test DB and confirm
338 backend tests pass. That setup turned out to be already done —
`agentic_claims_test` exists, migrated to `0002_audit_human_agent`, `vector`
extension enabled, `.env.test` pointing at `localhost:5432/agentic_claims_test`.

Running `uv run pytest` gave **336 passed, 2 failed, 7 skipped** (345 collected;
the "338" figure in `CLAUDE.md` is the non-skipped count).

Both failures in `backend/tests/test_migration_0002.py`:

- `test_agent_check_constraint_includes_human`
- `test_downgrade_constraint_rejects_existing_human_rows`

## Diagnostic (verified against source and live schema)

| Fact | Evidence |
| --- | --- |
| `audit_log_agent_check` is **absent** from the test DB | `pg_constraint` on `agentic_claims_test` lists only `audit_log_step_check` |
| …yet migration 0002 is recorded as applied | `alembic_version` = `0002_audit_human_agent` |
| Migration 0002 drops and re-adds that constraint by name | `0002_audit_human_agent.py:61-65` |
| Migration 0001 declares it as an inline column CHECK (Postgres auto-names it `audit_log_agent_check`) | `0001_initial_schema.py:84-92` |
| The hazard test drops the constraint with **no explicit transaction** | `test_migration_0002.py:118` (pre-fix) |
| Connections are opened `autocommit=True` | `backend/db/connection.py:59` |
| The autocommit contract requires `conn.transaction()` for multi-statement atomicity | `connection.py` docstring, lines 36-40 |
| `clean_db` resets rows only, never schema | `conftest.py:216-223` (`TRUNCATE … RESTART IDENTITY CASCADE`) |
| This is the only test in the suite doing DDL or calling `.rollback()` | grep across `backend/tests` — single hit each |

### Root cause

`test_downgrade_constraint_rejects_existing_human_rows` proves a documented
downgrade hazard: with a `human` audit row present, re-adding the six-value
agent CHECK must fail. Pre-fix it did so like this:

```python
with pytest.raises(psycopg.errors.CheckViolation), clean_db.cursor() as cur:
    cur.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_agent_check")
    cur.execute(_SIX_VALUE_CHECK)
# Roll back the aborted DDL transaction so the seven-value constraint stands.
clean_db.rollback()
```

This depended on both statements sharing one implicit transaction: the `ADD`
raises `CheckViolation`, the transaction aborts, the `DROP` is undone.

**Phase 8.4 removed that implicit transaction.** Under `autocommit=True` the
`DROP` commits the instant it executes, the `ADD` then fails as expected — so
`pytest.raises` is satisfied and the test *passes* — and `clean_db.rollback()`
is a no-op because no transaction is open. The constraint is gone permanently.
Every subsequent run then fails: this test, and
`test_agent_check_constraint_includes_human`, which asserts the constraint
exists.

Phase 8.5 did not cause this. It created the first conditions under which it is
observable — a *persistent* test database.

### Why CI never caught it

CI provisions a fresh localhost Postgres service container per run. On a virgin
schema all four tests pass (the poisoning test runs last in the file) and the
container is discarded. The damage is only visible on a persistent test DB, so
CI is green and will stay green.

## Plan

**1. Repair the test database** (one statement, no code):

```sql
ALTER TABLE audit_log ADD CONSTRAINT audit_log_agent_check
  CHECK (agent IN ('system','doc_parser','validator','adjuster',
                   'guardrail','orchestrator','human'));
```

Safe — all existing `agent` values already satisfy it.

**2. Fix the test** — `backend/tests/test_migration_0002.py` only:

- Wrap the DDL surgery in `clean_db.transaction()` so the `DROP` rolls back
  under autocommit. Context-manager ordering matters: the transaction is inner
  relative to `pytest.raises`, so it exits first (rollback), then the
  `CheckViolation` propagates to the outer `pytest.raises`.
- Drop the trailing `clean_db.rollback()` — it encodes a transaction contract
  that no longer exists, and leaving it would misdescribe the code.
- Add a self-checking post-assertion (`SELECT 1 FROM pg_constraint …`) so the
  test discriminates against a DDL leak, not merely against the re-add being
  refused.

**3. Version** — `pyproject.toml` `0.8.5` → `0.8.5.1`. `/health` resolves the
version via `importlib.metadata` (`backend/app/api/health.py:42-45`), so the
`pyproject.toml` bump is the single source; no code change needed. No version
literals exist anywhere in code or tests (`test_health.py` deliberately asserts
only that the string is non-empty).

**Interface stability:** none. Test-layer only. No production code, no
migration, no schema change, no contract crossing a boundary. The module
docstring's claim that the surgery happens "inside a transaction it rolls back"
becomes true again rather than needing a rewrite.

**Dependencies:** none added.

## Out of scope (logged, not actioned)

`agentic_claims_dev` is empty — no tables, no `alembic_version`. The app has
been running against Neon rather than local dev. Not a defect; recorded as a
separate future item at Dermot's direction.
