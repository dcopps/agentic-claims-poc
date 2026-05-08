# Report 02 — Phase 1: Data Layer and Settings Infrastructure

## Summary

**Recap.** Phase 1 lands the persistent foundation — versioned schema, settings sub-models, the SHA-256 chained audit vault written defensively, the indexed sample policy, and the synthetic claim generator covering the three demo scenarios. Phase 2 next introduces the LLM Gateway and the Validator agent.

**Completed at:** 2026-05-08T16:37:58Z
**Phase:** 1 — Data layer and settings infrastructure
**Status:** Complete (no deferrals)

**Links**

- Prompt: [`docs/prompts/02-phase-1-data-layer.md`](02-phase-1-data-layer.md)
- Plan (approved): [`docs/prompts/02-phase-1-data-layer-plan.md`](02-phase-1-data-layer-plan.md) — approved 2026-05-08T15:39:42Z
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 1 entry)
- Repository: <https://github.com/> (push to `main` triggers Render auto-deploy after the architect sets `DATABASE_URL`)

**CI status.** Backend job extended with the `pgvector/pgvector:pg16` service container, `alembic upgrade head` step, and advisory `pip-audit`. Frontend job gains advisory `npm audit --audit-level=high`. Local equivalents (`uv run alembic ... upgrade head`, `uv run pytest`, `uv run mypy backend`, `uv run ruff check .`, `npm test -- --run`) all clean.

---

## Files created

### Database / migrations

- `backend/db/__init__.py` — package marker.
- `backend/db/connection.py` — `open_connection(settings)` context manager. Registers the `pgvector.psycopg` adapter at module import and applies the session-level `statement_timeout` (literal-interpolated; Postgres `SET` rejects parameterised values).
- `backend/alembic.ini` — Alembic configuration; URL is read at runtime from `Settings`, not baked into the file.
- `backend/db/migrations/env.py` — Alembic environment. Reads `DATABASE_URL` from `Settings` and rewrites the scheme to `postgresql+psycopg://` so SQLAlchemy picks the psycopg-3 driver (we do not install psycopg2). `target_metadata = None` because there is no ORM.
- `backend/db/migrations/script.py.mako` — Alembic template.
- `backend/db/migrations/__init__.py`, `backend/db/migrations/versions/__init__.py` — package markers.
- `backend/db/migrations/versions/0001_initial_schema.py` — initial migration: `vector` extension, `claims`, `audit_log`, `policy_chunks`, all indexes.

### Audit vault

- `backend/app/audit/__init__.py` — public surface.
- `backend/app/audit/event.py` — `AuditEvent` Pydantic model.
- `backend/app/audit/canonical.py` — deterministic JSON encoding with type-rejection.
- `backend/app/audit/chain.py` — `compute_row_hash`, `compute_chain_hash`, `GENESIS_CHAIN_HASH = "0" * 64`, `HASH_HEX_LENGTH = 64`.
- `backend/app/audit/writer.py` — `AuditWriter.append`. Defensive ordering: sanitise (canonicalise upfront) → validate (advisory lock + claim FK lookup) → abort (`ValueError` with payload excerpt) → execute (`INSERT ... RETURNING` in one statement). Translates `psycopg.errors.ForeignKeyViolation` to `ValueError` for consistent caller handling.
- `backend/app/audit/verify.py` — `verify_chain(conn) -> ChainVerification`. Stops at the first divergence; reports kind (`row_hash_mismatch` or `chain_hash_mismatch`) plus expected and actual values.

### Settings

- `backend/settings.py` — extended in place.
- `backend/settings.yaml.template` — extended in place.

### Sample policy + seeders

- `backend/data/__init__.py` — package marker.
- `backend/data/sample_policy.txt` — generic commercial-property excerpt: General Conditions, Definitions, Named Perils Covered, Exclusions (with explicit "flood endorsement is NOT attached" pointer that the demo's guardrail-escalation scenario can hallucinate against), Sub-Limits, Business Interruption, Duties After Loss.
- `backend/data/seed_claims.py` — nine claims, three scripted scenarios + six background, reproducible RNG (`random.seed(20260508)`), `--allow-truncate` flag.
- `backend/data/index_policy.py` — `chunk_markdown_sections` (model-free, unit-testable) plus the end-to-end embed-and-write pipeline.

### Prompts directory + escalation directory

- `backend/app/prompts/__init__.py`, `backend/app/prompts/system/.gitkeep`, `backend/app/prompts/user/.gitkeep` — Phase 2-ready.
- `backend/app/escalation/__init__.py` — Phase 4-ready.

### Tests

- `backend/tests/conftest.py` — extended with `db_settings`, `migrated_db`, `clean_db`.
- `backend/tests/test_settings_phase1.py` — 11 tests.
- `backend/tests/test_audit_canonical.py` — 7 tests.
- `backend/tests/test_audit_chain.py` — 8 tests.
- `backend/tests/test_audit_writer.py` — 7 tests, all DB-backed.
- `backend/tests/test_audit_verify.py` — 4 tests, all DB-backed.
- `backend/tests/test_seed_claims.py` — 8 tests (mix of pure and DB-backed).
- `backend/tests/test_index_policy.py` — 8 tests plus 1 conditional (`RUN_EMBEDDING_TESTS=1`).
- `backend/tests/test_schema.py` — 5 DB-backed tests.

### Repo-root and docs

- `.env.example` — `DATABASE_URL`, `ANTHROPIC_API_KEY` placeholder, `MISTRAL_API_KEY` placeholder.

## Files modified

- `pyproject.toml` — added `psycopg[binary]>=3.2`, `pgvector>=0.3`, `alembic>=1.13`, `sqlalchemy>=2.0`, `sentence-transformers>=3.0`; dev `pip-audit>=2.7`. Added a mypy `[tool.mypy.overrides]` stanza for the third-party libraries that ship without `py.typed` markers (`pgvector`, `sentence_transformers`, `transformers`).
- `uv.lock` — regenerated by `uv add`.
- `.github/workflows/ci.yml` — backend gains `services.postgres: pgvector/pgvector:pg16`, `DATABASE_URL` env, `alembic upgrade head` before pytest, advisory `pip-audit --strict`. Frontend gains advisory `npm audit --audit-level=high`.
- `README.md` — Local development section gains "Configure environment variables", "Run database migrations", and "Seed and index" steps, with Neon-from-local override documented.
- `docs/architecture-stack-reference.md` — three table rows and two prose locations updated from Render-Postgres wording to Neon. Production-side wording (Azure SQL Managed Instance) unchanged.
- `CLAUDE.md` — Tech Stack > Data, Hosting & CI, Architectural Decisions (Database, Hosting) updated for Neon. Current Status updated to "Phase 1 complete; Phase 2 next".

## Tests — counts and pass rates

| Module | Tests |
|---|---|
| `test_settings.py` (Phase 0, unchanged) | 6 |
| `test_health.py` (Phase 0, unchanged) | 1 |
| `test_settings_phase1.py` | 11 |
| `test_audit_canonical.py` | 7 |
| `test_audit_chain.py` | 8 |
| `test_audit_writer.py` | 7 |
| `test_audit_verify.py` | 4 |
| `test_seed_claims.py` | 8 |
| `test_index_policy.py` | 8 (+ 1 conditional, skipped by default) |
| `test_schema.py` | 5 |
| **Backend total** | **65 passing, 1 skipped, 0 failing** |
| Frontend (`vitest`) | 2 passing |
| **Repository total** | **67 passing, 1 skipped, 0 failing** |

`uv run ruff check .` — clean. `uv run mypy backend` — clean (35 source files). `npm run lint` and `npm run typecheck` (frontend) — clean.

## Deviations from the plan, with reasons

1. **`Settings.database` declared with `default_factory`, not as a no-default required field.** The plan asked for a no-default required field; mypy refused every `Settings()` call site as `Missing named argument "database"`. The runtime contract is preserved by `_resolve_database_settings`, which raises `ValueError` if `DATABASE_URL` is absent — same fail-fast semantics, but the type system stays honest. No interface change for callers.
2. **Statement timeout interpolated as a SQL literal, not parameterised.** Postgres `SET` does not accept `%s`-style parameters. The integer is validated to be `ge=0` by Pydantic and re-cast to `int` before f-string interpolation. Documented inline.
3. **Alembic URL rewritten to `postgresql+psycopg://`.** SQLAlchemy defaults to the psycopg2 DBAPI; we do not install psycopg2. The rewrite makes Alembic load psycopg-3, which is what the runtime app uses. Documented inline.
4. **Canonicaliser uses `mode="python"`, not `mode="json"`.** With `mode="json"` Pydantic silently transforms `Decimal`, `set`, and `bytes` before the `default` callback ever sees them, which means the type-rejection contract was unenforceable. `mode="python"` plus a `default` callback that handles UUID / datetime / date encoding *and* refuses Decimal / set / bytes restores the contract.
5. **Concurrent-write test uses 2×5 events.** The plan called for "two threads writing"; the realised test runs five appends per thread to make a missed-fork detectable across more chain links. Pure strengthening of the test, not a contract change.

No other deviations.

## Guard clauses added

Every guard clause has a triggering test that asserts on the message content, not just on the exception type.

- `DatabaseSettings.url` — non-Postgres scheme rejected with both prefixes named in the message.
- `EmbeddingSettings.dimension` — anything other than 384 rejected with the locked-model name in the message.
- `EmbeddingSettings.batch_size` — `ge=1` clamps non-positive values.
- `LangfuseSettings` — model validator rejects `enabled=True` with either key missing; message reports which key is set.
- `EscalationSettings.validator_confidence_floor`, `adjuster_confidence_floor` — `ge=0.0, le=1.0` clamps out-of-range values.
- `Settings` — `extra="forbid"` rejects typo'd top-level keys (and applies through the YAML overlay merge path).
- `AuditEvent.step` — strip-then-non-empty rejection rejects `"   "`.
- `AuditEvent.created_at` — naive datetime rejected; non-UTC tz-aware values normalised to UTC.
- `canonicalise._encode_or_reject` — Decimal, set/frozenset, bytes/bytearray, naive datetimes, and any unsupported type rejected with diagnostic messages naming the offending type.
- `compute_row_hash` — non-bytes and empty-bytes rejected.
- `compute_chain_hash` / `_require_hex_digest` — non-string, wrong-length, non-hex, uppercase-hex inputs all rejected.
- `AuditWriter.append` — claim FK lookup before insert; foreign-key race translated to `ValueError`; `INSERT ... RETURNING` no-row branch surfaced as `RuntimeError` rather than silently constructing a half-formed row.
- `chunk_markdown_sections` — empty text, missing headings, inverted target range all rejected.
- `_embed_chunks` — model output dimension mismatch rejected loudly.
- `_persist` — chunk count vs vector count mismatch rejected.
- `seed_claims.insert_claims` — non-empty `claims` table rejected unless `truncate_first=True`.
- `seed_claims.generate_claims` — non-positive jitter result rejected (defensive guard against future template tweaks).

## Optional enhancements recommended for follow-on work

These were flagged in the plan as optional and remain so. Recommend folding into the phases noted.

1. **`verify_audit_chain` CLI wrapper** (~10 lines, Phase 5/6) — exposes the chain check as a one-line command for the demo, alongside the audit-log viewer in the UI.
2. **Async psycopg connection** (deferred) — net win is small for Phase 1; revisit when the orchestrator's hot path needs concurrency.
3. **Tighter version pinning** (Phase 7 polish) — current resolutions are caret-bounded.
4. **Pre-commit hooks** (Phase 7 polish) — `ruff`, `prettier`, an anonymisation grep, optionally `pip-audit`.
5. **Promote `pip-audit` from advisory to blocking** once the dependency tree is stable; same for `npm audit`.
6. **Full-walk audit verification** — current verifier stops at the first break. A "report all breaks" variant is straightforward and would fit alongside the CLI wrapper above.

## Outstanding items requiring architect involvement

1. **Set `DATABASE_URL` on Render's Environment tab** to the Neon connection string. Render will auto-redeploy on the env-var change. The repository already pushes to `main` so the Phase 1 commit triggers a build; the deploy will fail at startup until `DATABASE_URL` is set.
2. **Verify the deployed backend reaches Neon at startup** — the simplest check is the Render service logs ("Application startup complete." after a successful boot). Optionally hit the public `/health` endpoint.

That's the full residual list. The repository can run end-to-end locally without further architect input.
