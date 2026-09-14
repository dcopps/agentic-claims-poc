# Phase 8.5.1 — Migration-test autocommit fix — REPORT

**Date:** 2026-09-14
**Prompt + Plan:** [`14-phase-8.5.1-migration-test-autocommit-fix.md`](14-phase-8.5.1-migration-test-autocommit-fix.md)

> **Archive note.** Phase 8.5.1 arose from an investigation rather than a
> pre-written phase prompt, so the prompt, diagnostic, and plan are archived
> together in the single `…-fix.md` file instead of the usual
> prompt / plan / report triple.

## Summary

Phase 8.5's pending verification (run the suite against the local test DB) turned
up **336 passed, 2 failed, 7 skipped**. Both failures traced to a single test that
performed DDL without an explicit transaction. Under the `autocommit=True`
contract introduced by Phase 8.4, its `ALTER TABLE … DROP CONSTRAINT` committed
immediately and its trailing `conn.rollback()` became a no-op — permanently
stripping `audit_log_agent_check` from the test database on first run, and failing
every run thereafter. Fixed by wrapping the surgery in `clean_db.transaction()`,
plus a self-checking post-assertion that makes the test a genuine discriminator
against DDL leaks. Suite now **338 passed, 0 failed, 7 skipped**.

## What changed

| File | Change |
| --- | --- |
| `backend/tests/test_migration_0002.py` | `test_downgrade_constraint_rejects_existing_human_rows` wraps its DDL in `clean_db.transaction()`; no-op `clean_db.rollback()` removed; new post-assertion verifies the constraint survived. |
| `pyproject.toml` | Version `0.8.5` → `0.8.5.1` (first point release; establishes the hotfix naming pattern). |
| `agentic_claims_test` (local DB, not version-controlled) | `audit_log_agent_check` re-added by hand — repairing damage the pre-fix test had already done. |
| `docs/build-log.md` | Phase 8.5.1 entry appended. |
| `CLAUDE.md` | Current Status updated to 0.8.5.1 / Phase 8.5.1. |

No production code touched. No migration added or altered. `/health` needed no
change: it resolves the version from `importlib.metadata`
(`backend/app/api/health.py:42-45`), so the `pyproject.toml` bump propagates on
its own.

## The fix

```python
# The DDL surgery MUST be wrapped in an explicit transaction. Connections run
# in autocommit mode (Phase 8.4), so a bare DROP commits the instant it
# executes — the failed re-add would then leave the shared test schema
# permanently without its agent CHECK, and `clean_db` only TRUNCATEs rows, so
# nothing would ever restore it. Under autocommit `conn.transaction()` emits a
# real top-level BEGIN…COMMIT, and its __exit__ rolls back before the
# CheckViolation reaches the enclosing `pytest.raises`.
with (
    pytest.raises(psycopg.errors.CheckViolation),
    clean_db.transaction(),
    clean_db.cursor() as cur,
):
    cur.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_agent_check")
    cur.execute(_SIX_VALUE_CHECK)
# Asserting the rollback actually happened is what makes this test a
# discriminator against a DDL leak, not just against the re-add being refused.
# Without it the test passes identically whether the DROP was rolled back or
# committed — which is exactly how the autocommit regression stayed invisible.
with clean_db.cursor() as cur:
    cur.execute(
        "SELECT 1 FROM pg_constraint WHERE conname = 'audit_log_agent_check'"
    )
    assert cur.fetchone() is not None
```

### Design notes

- **Context-manager ordering is load-bearing.** The three managers exit in
  reverse order: cursor closes, then `transaction()` rolls back, then the
  `CheckViolation` reaches `pytest.raises`. Putting `pytest.raises` anywhere but
  outermost would let the exception escape before the rollback runs.
- **Combined into one `with` statement** rather than nesting, because ruff's
  SIM117 flags the nested form. The parenthesised multi-manager syntax needs
  Python ≥ 3.10; the project requires ≥ 3.11.
- **The no-op `rollback()` was removed, not left in place.** It encoded a
  transaction contract that Phase 8.4 abolished; leaving it would have
  misdescribed the code to the next reader.

## Verification

| Check | Result |
| --- | --- |
| Full backend suite | **338 passed, 0 failed, 7 skipped** (345 collected), exit 0 |
| `test_migration_0002.py` run **twice consecutively** | 4 passed, 4 passed — no DDL leak between runs |
| `audit_log_agent_check` present after suite | confirmed via `pg_constraint` |
| `ruff check .` (whole repo) | All checks passed |
| `mypy backend/tests/test_migration_0002.py` | Success, no issues |
| Version `/health` would report | `0.8.5.1` (via `importlib.metadata`) |

### Discriminator proof

The post-assertion was not taken on trust. The pre-fix form was deliberately
reinstated (no explicit transaction, no-op rollback) with the new assertion kept
in place, and the test re-run:

```
backend/tests/test_migration_0002.py:136: in test_downgrade_constraint_rejects_existing_human_rows
    assert cur.fetchone() is not None
E   assert None is not None
FAILED test_downgrade_constraint_rejects_existing_human_rows
```

The code that previously **passed** while destroying the schema now **fails**.
The fix was then restored and the constraint repaired (the deliberate break had
dropped it again), and the full suite re-run green.

## Test count reconciliation

`CLAUDE.md` claimed 338 backend tests; the suite collects 345. The difference is
exactly the 7 skipped tests — the 338 figure is the non-skipped count. Both
numbers are now stated explicitly in the build log so the discrepancy does not
resurface.

| | Before | After |
| --- | --- | --- |
| Collected | 345 | 345 |
| Passed | 336 | **338** |
| Failed | 2 | **0** |
| Skipped | 7 | 7 |

Frontend unchanged (36).

## Interface stability

None. Test-layer only. No production code path, JSON schema, HTTP response
shape, SSE event, database column, or migration changed. The `/health` response
shape is unchanged — only the value of its existing `version` field moves, which
is its documented purpose.

## Suggestions (not actioned)

- **A guard against the general class of bug.** This test was the only DDL
  performer in the suite, but nothing structurally prevents another. A
  session-scoped fixture that snapshots `pg_constraint` before and after the run
  and fails on a diff would catch any future schema leak, not just this one.
- **`agentic_claims_dev` is empty** — no tables, no `alembic_version`. The app
  has been running against Neon rather than local dev. Out of scope for this
  hotfix by direction; logged here as a future item.
