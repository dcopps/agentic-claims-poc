# Phase 8.4 — Audit-write transaction fix — PLAN

Status: awaiting confirmation. No code written yet.

## Root cause (re-verified against source)

| Fact | Evidence |
| --- | --- |
| Connections open with `autocommit=False` | `backend/db/connection.py:42` |
| Agents hold one connection across SELECT + audit write | `doc_parser.py:150`, `validator.py:142`, `adjuster.py:156` (single `with` block) |
| Doc-Parser SELECTs before the audit write | `doc_parser.py:151` `_load_claim_record` |
| `AuditWriter.append` uses `conn.transaction()` | `writer.py:89` |
| `open_connection` closes without committing | `connection.py:71-72` (`finally: conn.close()`, no `commit()`) |

psycopg3's `conn.transaction()` is context-aware. On a clean connection it emits a
real `BEGIN…COMMIT`. Inside an already-open transaction it degrades to a
`SAVEPOINT…RELEASE`. The agents' first SELECT opens an **implicit** transaction;
`AuditWriter.append` then runs as a **savepoint**, which "commits" on `__exit__`
but is only durable if the enclosing implicit transaction commits. It never does —
`open_connection`'s `finally` closes the connection, Postgres rolls back the outer
transaction, and the audit INSERT is rolled back with it. Silent loss.

Guardrail (`guardrail.py:145`) runs **no SQL before the audit write**, so its
`conn.transaction()` is the outermost transaction on a clean connection and commits
cleanly. The orchestrator's `_audit` (`pipeline.py:567`) and human-decision writer
(`human.py:108`) likewise put the audit write first on a fresh connection. That is
why those four entry kinds survived the rehearsal and the agent three did not.

## 1. Files to modify

| File | Change | Why |
| --- | --- | --- |
| `backend/db/connection.py` | `autocommit=False` → `autocommit=True`; remove redundant `conn.commit()` at line 62; update docstring (lines 33-35) to state the new contract | The fix |
| `backend/tests/test_audit_persistence.py` | **new** — 4 regression tests | Close the test gap |
| `pyproject.toml` | `version = "0.8.3"` → `"0.8.4"` | `/health` is sourced from `importlib.metadata.version("agentic-claims-poc")` via `backend/app/api/health.py:44`; bumping the package version is the only change needed |
| `docs/build-log.md` | Phase 8.4 entry | Convention |
| `docs/prompts/12-phase-8.4-audit-write-fix-report.md` | **new** — post-execution report | Convention |
| `CLAUDE.md` | Current Status section | Handoff |

No other production source file changes. The sweep (section 3) confirms it.

## 2. Approach — recommended vs alternative

**Recommended (chosen): `autocommit=True`.**
With autocommit on, every `conn.transaction()` block in the codebase becomes the
outermost transaction on its connection and emits a real `BEGIN…COMMIT` — exactly
the pattern psycopg's context manager is designed for. The agents' pre-audit SELECTs
no longer open a lingering implicit transaction, so there is nothing left to roll
back at `close()`. The `SET statement_timeout` at line 61 applies immediately under
autocommit, so the `conn.commit()` at line 62 is now a no-op and is removed.

**Alternative (rejected): keep `autocommit=False`, add `conn.commit()` in the
`finally` before `close()`.**
Rejected because it commits *unconditionally on every exit path, including
exceptions*. A failed agent run that should roll back would instead commit whatever
partial state sat in the implicit transaction. That trades a silent-loss bug for a
silent-corruption bug. It also leaves the fragile savepoint-degradation behaviour in
place — any future code that SELECTs before an audit write would reintroduce the
defect. The recommended fix removes the failure mode at its source.

## 3. Callers-of-`open_connection` sweep

Every call site, and whether it relies on implicit-transaction atomicity:

| Call site | Operation | Atomic via explicit `transaction()`? | Verdict under autocommit=True |
| --- | --- | --- | --- |
| `agents/doc_parser.py:150` | SELECT then `AuditWriter.append` | append wraps itself | **fixed** — no dangling tx |
| `agents/validator.py:142,189` | SELECT (+pgvector) then append | append wraps itself | **fixed** |
| `agents/adjuster.py:156` | SELECT fixture then append | append wraps itself | **fixed** |
| `agents/guardrail.py:145` | append only | append wraps itself | unchanged (already worked) |
| `audit/writer.py:89` | `conn.transaction()` | yes | real BEGIN/COMMIT — unchanged semantics |
| `claims/repository.py:55,141` | `insert` / `update_status` in `conn.transaction()` | yes | atomic, commits |
| `orchestrator/pipeline.py:567` | append on fresh conn | append wraps itself | unchanged |
| `orchestrator/pipeline.py:593` | `update_status` on fresh conn | repo wraps itself | atomic, commits |
| `api/human.py:108` | append **then** `update_status` | each wraps itself separately | **no cross-statement atomicity today** (two `transaction()` blocks) — unchanged; audit is authoritative, status best-effort by design |
| `api/claims.py:82,89,94,99` | insert (wrapped) / reads | insert wraps itself | unchanged |
| `api/pipeline.py:239,244,258` | reads only | n/a | reads, no tx needed |
| `api/audit.py:93,114` | reads only | n/a | reads |
| `api/runs.py:63,68` | reads only | n/a | reads |
| `data/seed_claims.py:382` | `insert_claims` in `conn.transaction()` then `conn.commit()` | yes | atomic; trailing `commit()` becomes a no-op |
| `data/index_policy.py:287` | `_persist` in `conn.transaction()` then `conn.commit()` | yes | atomic; trailing `commit()` becomes a no-op |

**Conclusion: no call site relies on implicit-transaction atomicity.** Every
multi-statement write is already wrapped in an explicit `conn.transaction()`. The two
trailing `conn.commit()` calls in the scripts (`seed_claims.py:384`,
`index_policy.py:289`) become harmless no-ops.

**In-scope cleanup (approved):** the two trailing script `conn.commit()` calls
(`seed_claims.py:384`, `index_policy.py:289`) **will be removed**. Under
`autocommit=True` they are no-ops, but leaving them encodes the old
`autocommit=False` contract in the source — a cognitive landmine for the next
reader. The removal is a direct knock-on of the contract change, so it belongs in
this change, not a separate scope.

## 4. Risks

- **Atomicity regression:** none found — see the sweep. If any of the existing 331
  tests fail under autocommit=True, that is a hidden dependency the sweep missed and
  I will stop and surface it before shipping, per the prompt.
- **`human.py` audit+status not atomic together:** pre-existing and intentional
  (two separate `transaction()` blocks today; audit log is authoritative, status is
  best-effort). The fix does not change this. Noted so it is not mistaken for a
  regression.
- **pgvector `register_vector` under autocommit:** runs after the `SET`; it issues no
  transactional writes, so autocommit mode is irrelevant to it.

## 5. Interface stability

**No public-facing contract is touched.** No JSON schema, HTTP response shape, SSE
event, or database column changes. All audit payload contracts (including the
Phase 8.3 `llm_call.prompt` block) are unchanged. This is an internal correctness fix.
The only externally observable change is intended: the `/health` version string moves
to `0.8.4`, and audit rows that previously vanished now persist.

## 6. Test design — `backend/tests/test_audit_persistence.py`

Four tests, one per agent. The **two-connection design** is the discriminator: a test
that reads the audit row through the same connection that wrote it sees the row inside
its own transaction and masks the rollback.

Each test:
1. Uses `clean_db` + a committed seeded claim so the FK target exists on a separate
   connection (insert the claim and commit it before invoking the agent).
2. Wires the agent with mock LLM providers (reusing the existing agent-test fixtures)
   and a `connection_factory` that calls the **unmodified production
   `open_connection(db_settings)`** — no autocommit override, no commit-in-fixture.
3. Calls the agent's `evaluate(...)`.
4. Opens a **separate second** `open_connection(db_settings)` after `evaluate` returns.
5. Queries `audit_log WHERE correlation_id = %s` on that second connection and asserts
   the row exists with the expected `agent` and `step`:
   - `doc_parser` / `doc_extract`
   - `validator` / `coverage_check`
   - `adjuster` / `settlement_estimate`
   - `guardrail` / `output_check`

These tests fail on the pre-fix code (rows absent for the first three) and pass after.
Guardrail's test documents that the previously-working path stays working.

## 7. Version bump

`pyproject.toml:3` `0.8.3` → `0.8.4`. `/health` resolves via
`importlib.metadata.version("agentic-claims-poc")`, so the redeploy is detectable once
Render reinstalls the package. `test_health.py` asserts only that the version is a
non-empty string, so it stays green.

## 8. Verification after Render redeploys

1. `/health` reports `0.8.4`.
2. Re-run the threshold-escalation scenario end-to-end.
3. All four agent expand panels show filled prompts and JSON responses with **no**
   "Audit entry not found" banners.
4. The audit log for that correlation_id contains **seven** entries: four agent steps
   (`doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`) plus three
   orchestrator steps (`pipeline_started`, `escalation_decision`,
   `pipeline_awaiting_human`).

## Test pass-rate target

331 backend tests → 335 (four new regression tests). The existing 331 must stay green;
any break signals a missed atomicity dependency and halts the change.
