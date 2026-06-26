# Phase 8.4 — Audit-write transaction fix — REPORT

**Date:** 2026-06-26
**Prompt:** [`12-phase-8.4-audit-write-fix.md`](12-phase-8.4-audit-write-fix.md)
**Plan (approved):** [`12-phase-8.4-audit-write-fix-plan.md`](12-phase-8.4-audit-write-fix-plan.md) — approved with one amendment (the two trailing script `conn.commit()` calls folded into scope as a direct knock-on of the contract change).

## Summary

A production-only silent data-loss bug discarded three of every four agent audit
rows. Doc-Parser, Validator, and Adjuster each ran a SELECT before their audit write;
under the connection's `autocommit=False` setting that opened an implicit transaction,
which demoted `AuditWriter`'s `conn.transaction()` to a nested SAVEPOINT. The savepoint
"committed" on exit but was only durable if the enclosing implicit transaction
committed — and `open_connection` closes the connection with no outer commit, so
Postgres rolled the implicit transaction (and the audit INSERT) back. Guardrail and the
orchestrator writes survived because they perform no SQL before the audit write, so
their `conn.transaction()` was the top-level boundary on a clean connection.

The fix flips the connection to `autocommit=True`, making every `conn.transaction()`
block the top-level transactional boundary that commits for real. A four-test
regression module — using a two-connection design that reads the audit row through a
*separate* connection from the one that wrote it — locks the behaviour in.

## What changed

| File | Change |
| --- | --- |
| `backend/db/connection.py` | `psycopg.connect(..., autocommit=False)` → `autocommit=True`; removed the now-redundant `conn.commit()` after `SET statement_timeout`; rewrote the docstring to state the new transaction contract and the Phase 8.4 rationale. |
| `backend/data/seed_claims.py` | Removed the trailing `conn.commit()` after `insert_claims` (which already wraps its work in `conn.transaction()`); added a comment explaining why no outer commit is needed. |
| `backend/data/index_policy.py` | Removed the trailing `conn.commit()` after `_persist` (same reasoning). |
| `backend/tests/test_audit_persistence.py` | **New** — four regression tests, one per agent, two-connection design. |
| `pyproject.toml` | `version` `0.8.3` → `0.8.4`. `/health` is sourced from package metadata, so a successful redeploy reports `0.8.4`. |

No other production source changed. The full caller sweep (in the plan) confirmed every
multi-statement write in the codebase already wraps itself in an explicit
`conn.transaction()`, so nothing depended on the implicit-transaction atomicity the fix
removes.

## Interface stability

No public-facing contract touched — no JSON schema, HTTP response shape, SSE event, or
database column changed. All audit payload contracts (including the Phase 8.3
`llm_call.prompt` block) are unchanged. The only intended observable changes: `/health`
reports `0.8.4`, and audit rows that previously vanished now persist.

## The regression-test gap that let this ship

The existing agent suites inject a connection factory that yields the **same** `clean_db`
connection used to read the audit row back. Reading a row through the connection that
wrote it sees it inside that connection's own transaction — so the rollback-on-close was
invisible to every one of the 331 tests. The new tests close the gap by reading through a
**separate** connection opened after `evaluate` returns, which is the only shape that
observes durability.

## Verification performed

**Discriminator proof (local).** I exercised three code states against the new tests:

| Connection state | Result | Interpretation |
| --- | --- | --- |
| Fixed (`autocommit=True`, no post-SET commit) | **4/4 pass** | rows durable |
| True original bug (`autocommit=False` **with** post-SET commit) | **3 fail, 1 pass** | reproduces the rehearsal exactly — Doc-Parser/Validator/Adjuster lost, Guardrail survives |
| `autocommit=False` **without** post-SET commit | **4/4 fail** | confirms the two changes are coupled: the post-SET commit was load-bearing under autocommit-off; removing it alone would have lost all four |

The middle row is the faithful reproduction of the deployed `0.8.3` defect: the three
agents that SELECT before writing lose their audit rows, and Guardrail (no pre-write SQL)
survives — matching the rehearsal observation precisely.

**Test suite.** Backend 331 → **335 passing**, 7 skipped (four new regression tests); all
green. `ruff` clean, `mypy` clean on the changed files. Frontend untouched.

## Deployed verification (pending redeploy)

After Render redeploys the bumped package:
1. `/health` reports `0.8.4`.
2. Re-run the threshold-escalation scenario end-to-end.
3. All four agent expand panels show filled prompts and JSON responses with **no**
   "Audit entry not found" banners.
4. The audit log for that correlation_id holds **seven** entries: four agent steps
   (`doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`) plus three
   orchestrator steps (`pipeline_started`, `escalation_decision`,
   `pipeline_awaiting_human`).

## Issues encountered

- **The two-changes-are-coupled discovery.** The plan treated the post-SET `conn.commit()`
  removal as a cosmetic cleanup. The discriminator run revealed it is only safe *because*
  of the autocommit flip: under `autocommit=False`, that commit closed the implicit
  transaction opened by the `SET statement_timeout` execute, giving each agent's
  `conn.transaction()` a clean slate. Removing it without the autocommit flip would have
  broadened the bug to all four agents. The shipped change makes both edits together, so
  the coupling is satisfied; documented here so a future reader does not "tidy up" the
  autocommit flip in isolation.
