# Phase 8.4 — Audit-write transaction fix

## Context

During Phase 8.3 rehearsal we found a serious silent-failure bug in the audit pipeline. Re-running a threshold-escalation scenario on the deployed `0.8.3` build, three of the four agents (`doc_parser`, `validator`, `adjuster`) showed ✓ completed in the UI but their audit-log entries were missing entirely. Only `guardrail`'s entry persisted alongside the orchestrator's `pipeline_started`, `escalation_decision`, and `pipeline_awaiting_human` entries. The Phase 8.3 *"Audit entry not found for this completed agent — this may indicate a write failure"* red banner correctly identified the symptom in the response panel of each affected agent card.

The 331 backend tests pass; production silently loses three of every four agent audit rows. This breaks the load-bearing architectural property named in `CLAUDE.md`: *"the audit log alone is sufficient to reconstruct and explain any past decision."*

## Root cause (verified by reading the four agents, `connection.py`, and `writer.py`)

`backend/db/connection.py:42` opens psycopg connections with `autocommit=False`. The agents hold one long-lived connection across the LLM call and the audit write (`with self._connection_factory() as conn:`).

Doc-Parser, Validator, and Adjuster each perform SELECTs against the database **before** calling `AuditWriter.append`:

- `doc_parser.py:151` — `_load_claim_record(conn, claim_id)` reads the claim row
- `validator.py:143,145` — `_load_narrative` then `_retrieve_top_chunks` (pgvector cosine-similarity SELECT)
- `adjuster.py:160` — `_load_demo_fixture(conn, claim_id, market_range)` reads the fixture row

Each first SELECT starts an **implicit transaction** on the connection. When `AuditWriter.append` then runs `with self._conn.transaction()` at `writer.py:89`, psycopg degrades the `transaction()` block to a **SAVEPOINT** (not a top-level transaction) because the connection is already inside a transaction. The savepoint commits successfully on `__exit__`. But the outer implicit transaction is never committed. When the agent's `with` block exits, `open_connection`'s `finally:` at `connection.py:71-72` calls `conn.close()` with no `conn.commit()`. Postgres rolls back the entire outer transaction. The audit INSERT goes with it. **Silent loss.**

Guardrail's `evaluate` (`guardrail.py:145-169`) is the only one that performs **no SQL on the connection before the audit write** — it receives `adjuster_result` and `retrieved_chunks` from the orchestrator's in-memory pipeline state, and the rule engine is pure Python. So `AuditWriter.append`'s `transaction()` is the **outermost** transaction context on a clean connection, and commits cleanly. Same explanation applies to the orchestrator's `_audit` writes (`pipeline.py`), which open a fresh connection per call.

The 331 tests pass because the test fixtures inject a connection factory that is either autocommit=True or commits explicitly. The production `open_connection` path is the only one carrying the defect.

## Plan-first

Before writing any code, produce a written plan in `docs/prompts/12-phase-8.4-audit-write-fix-plan.md` covering:

1. **Files to modify.** `backend/db/connection.py` is the only known code change. Confirm by inspection.

2. **Approach.** The recommended fix is to flip `psycopg.connect(url, autocommit=False)` to `autocommit=True` at `connection.py:42`, and remove the now-redundant `conn.commit()` at `connection.py:62` after the `SET statement_timeout`. With `autocommit=True`, the `AuditWriter.append`'s explicit `conn.transaction()` block becomes the only transactional boundary on the connection — which is exactly the pattern psycopg's `transaction()` context manager is designed for. Document the alternative (keep `autocommit=False` and add an explicit `conn.commit()` in `open_connection`'s `finally:` before `conn.close()`) and justify why the recommended option is preferred.

3. **Callers-of-`open_connection` sweep.** Grep every call site of `open_connection` and identify any that depend on the *implicit-transaction* behaviour — i.e., assume that multiple statements are atomic without explicit `conn.transaction()` wrapping. For each such call site, decide: wrap in an explicit `conn.transaction()` block, or accept that the individual statements are independent. Document the full list and the per-call decision in the plan. Pay special attention to `backend/data/seed_claims.py`, any RAG indexing scripts under `backend/`, the orchestrator's `pipeline.py`, the migration runner under `backend/db/`, and `ClaimsRepository`.

4. **Risks.** Atomicity assumptions in the codebase that switching to autocommit=True would silently break. The sweep above should surface these. If any are found, the plan must address them before the code change ships.

5. **Interface stability.** None. This is an internal correctness fix. No JSON schema, HTTP shape, or database column changes. Existing audit payload contracts are unchanged. Acknowledge explicitly in the plan that no public-facing contract is touched.

6. **Test design.** A new test module `backend/tests/test_audit_persistence.py` with one test per agent (`doc_parser`, `validator`, `adjuster`, `guardrail`). Each test:
   - Invokes the agent's `evaluate(...)` with the **unmodified production `open_connection`** (no autocommit override, no commit-in-fixture).
   - Opens a **separate second connection** after `evaluate` returns.
   - Queries `audit_log WHERE correlation_id = ?` on that second connection.
   - Asserts the row exists with the expected `agent` and `step` values.

   The two-connection design is the discriminator: it is the only test shape that would have caught this bug. A test that reads the audit row through the same connection that wrote it would have masked the rollback because the row is visible inside its own transaction.

7. **Version bump.** `/health` from `0.8.3` to `0.8.4` so a successful redeploy is detectable from the deployed URL.

8. **Verification steps after Render redeploys.** Confirm `/health` reports `0.8.4`; re-run the Northwood threshold scenario end-to-end; confirm all four agent expand panels show filled prompts and JSON responses with no *"Audit entry not found"* banners; confirm the audit log for that correlation_id contains seven entries (four agent steps plus three orchestrator steps: `pipeline_started`, `escalation_decision`, `pipeline_awaiting_human`).

Wait for explicit confirmation of the plan before writing any code.

## Deliverables (after plan is approved)

1. `backend/db/connection.py` — the one-line `autocommit=True` fix plus the redundant-commit cleanup.
2. Any explicit `conn.transaction()` wrappers identified by the sweep, in their respective files.
3. `backend/tests/test_audit_persistence.py` — four new regression tests, one per agent, using the two-connection design above.
4. The version-bump location (`backend/app/main.py`, `backend/settings.py`, or wherever the `/health` version sticker is sourced) — bump to `0.8.4`.
5. `docs/build-log.md` — Phase 8.4 entry documenting root cause, the fix, the regression-test gap that allowed it to ship, test counts before and after, and the verification steps performed.
6. `docs/prompts/12-phase-8.4-audit-write-fix-report.md` — the standard post-execution report covering what was changed, what tests now pass, any issues encountered, and the deployed verification outcome.
7. `CLAUDE.md` — update the *Current Status* section before the final commit.

## Test pass-rate target

Before/after: 331 backend tests passing → 335 backend tests passing (the four new regression tests). The existing 331 must continue to pass; if any of them break under `autocommit=True`, that's a real atomicity dependency the sweep missed, and the plan must address it before the code change ships.

## Standing project conventions

Honour `CLAUDE.md`'s standing instructions throughout — defensive ordering (sanitise → validate → abort → execute), no silent fallbacks, function size limits (30-line prompt to reconsider, 50-line hard limit), settings hierarchy, externalised prompts, system/user separation, frequent commits with descriptive messages, push after every logical unit of work, security discipline (no secrets in code), dependency discipline (flag any new dependency in the plan and wait for confirmation), interface stability acknowledgement.
