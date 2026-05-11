# Build Log

A chronological record of every phase, task, or significant fix applied to this repository.

Each entry follows the format below. Entries are appended in build order — newest at the bottom.

---

## Entry format

Every entry contains:

- **Date** — ISO date, e.g. `2026-05-08`
- **Phase / Prompt** — the phase number and a link to the prompt file in `docs/prompts/` (where applicable)
- **Plan (approved)** — link to the saved plan file in `docs/prompts/`. The plan is saved verbatim before approval; the approval timestamp and message are appended at the bottom of the same file.
- **Plan iterations** — count of rejected revisions, if any, with links to each rejected plan file (preserved as numbered siblings, each carrying a `## Rejection` footer).
- **Report** — link to the report file in `docs/prompts/`. Authored by Claude Code after execution, capturing files changed, test counts, deviations from the plan, guard clauses added, and outstanding items.
- **Prompt summary** — one or two sentences describing what was asked.
- **What changed** — files created, modified, or deleted, with a one-line note on each.
- **Tests** — count and pass rate (e.g. `42 passing, 0 failing`); any new test categories introduced.
- **Issues discovered** — anything unexpected, including pre-existing issues surfaced by this work; notes on follow-up needed.
- **Next** — the phase that comes next.

The four-artefact set per phase (prompt + approved plan + report + build-log entry) gives a complete audit trail. Together they record intent, design (with full revision history including any rejected plan iterations), and outcome.

---

## Entries

### 2026-05-07 — Pre-build setup (manual)

**Phase:** Pre-Phase-0. Establishing the documentation foundation, the prompts archive, and the build-log convention before any code is written. This work was performed by the architect directly via filesystem tooling, not via a Claude Code prompt — there is no corresponding prompt, plan, or report file in `docs/prompts/`.

**Prompt summary:** Not applicable — manual setup work to align the kickoff package with the global standards at `~/.claude/CLAUDE.md`, and to author Prompt 01 so Claude Code can begin Phase 0 cleanly.

**What changed:**

- `CLAUDE.md` — restructured to match the global standards pattern. References `~/.claude/CLAUDE.md` at the top. Adds Project Overview, Tech Stack (uv-based), Project Structure (target post-Phase-0), Build Approach, Current Status, Standing Instructions (plan-first, build-log update, defensive programming, function size, settings hierarchy, externalised prompts, system/user separation, commit protocol, security, interface stability, dependency discipline, anonymisation), Architectural Decisions (Locked), Repository Name, what's public vs not.
- `BUILD-PLAN.md` — rewritten to incorporate global standards. Plan-first workflow noted at the top. Package manager locked to uv. Each phase includes settings architecture work where relevant, externalised prompts pattern, APILogger pattern. Each phase's "Definition of done" includes appending a build-log entry and saving the prompt to `docs/prompts/`. Prompt file numbering aligned so Phase 0 maps to `01-`, Phase 1 to `02-`, and so on.
- `docs/build-log.md` — created (this file).
- `docs/prompts/` — directory created.
- `docs/prompts/README.md` — created. Documents the four-artefact pattern (prompt + plan + report + build-log entry), the plan-save-then-approve workflow, the rejected-plan archiving rule, and the report-after-execution rule.
- `docs/prompts/01-phase-0-repository-scaffold.md` — authored. The first prompt for Claude Code; instructs it to produce and save a plan, await an explicit approval or rejection, archive any rejected versions with timestamped footers, and only proceed to execution once the canonical plan carries an `## Approval` footer.
- `README.md` — added a "Reproducible build" section linking to `docs/prompts/` and `docs/build-log.md`.

**Tests:** None — documentation changes only.

**Issues discovered:** None.

**Next:** Claude Code begins Phase 0 by reading and executing `docs/prompts/01-phase-0-repository-scaffold.md`.

---

### 2026-05-08 — Phase 0: Repository scaffold

**Phase / Prompt:** Phase 0 — [`docs/prompts/01-phase-0-repository-scaffold.md`](prompts/01-phase-0-repository-scaffold.md)

**Plan (approved):** [`docs/prompts/01-phase-0-repository-scaffold-plan.md`](prompts/01-phase-0-repository-scaffold-plan.md) (approved 2026-05-08T11:50:06Z)

**Plan iterations:** 0 rejected. The architect approved the canonical plan with answers to three flagged choices and three amendments to the "What I need from you" section; those decisions were folded into the plan body before the approval footer was appended, so no rejection cycle was needed.

**Report:** [`docs/prompts/01-phase-0-repository-scaffold-report.md`](prompts/01-phase-0-repository-scaffold-report.md)

**Prompt summary:** Stand up the runnable skeleton — uv-managed FastAPI backend with `/health`, React + Vite + TS + Tailwind frontend, initial Pydantic `Settings` model with YAML overlay, native local Postgres + pgvector via a setup script (no Docker), GitHub Actions CI for both stacks, Render Blueprint for deployment, standard tooling configs. Initialise git, make the Phase 0 commit, push to a freshly-created GitHub repo via `gh`.

**What changed:**

- `pyproject.toml` — top-level uv project, Python 3.11+, deps (`fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `pyyaml`) and dev deps (`pytest`, `httpx`, `ruff`, `mypy`, `types-pyyaml`); ruff + mypy + pytest config inline.
- `uv.lock` — generated by `uv sync`.
- `.gitignore` — excludes `BUILD-PLAN.md`, `HANDOFF.md`, `.env*`, Python caches, `node_modules`, build outputs, DB dumps, OS junk.
- `.editorconfig` — UTF-8/LF, 2-space default, 4-space Python.
- `render.yaml` — Render Blueprint declaring the Web Service (free tier, runtime python, `uv sync` build, uvicorn start, `/health` healthcheck, autodeploy on `main`). Postgres deferred to Phase 1.
- `backend/__init__.py`, `backend/app/__init__.py`, `backend/app/api/__init__.py`, `backend/tests/__init__.py`, `backend/data/.gitkeep` — package skeleton.
- `backend/settings.py` — Pydantic `BaseSettings` model + defensive YAML overlay loader (sanitise → validate → abort → execute).
- `backend/settings.yaml.template` — overlay template with the Phase 0 keys.
- `backend/app/main.py` — FastAPI factory `create_app()` with CORS middleware; module-level `app` for uvicorn.
- `backend/app/api/health.py` — `/health` endpoint, version sourced from `importlib.metadata.version("agentic-claims-poc")`.
- `backend/tests/conftest.py` — TestClient fixture.
- `backend/tests/test_health.py` — health endpoint contract test.
- `backend/tests/test_settings.py` — settings defaults + five YAML-loader guard triggering tests (missing file, empty file, malformed YAML, non-mapping YAML, directory-not-file).
- `frontend/` — Vite + React 19 + TS scaffold, Tailwind v4 via `@tailwindcss/vite`, Vitest + React Testing Library + jsdom, ESLint flat config (Vite default), Prettier.
- `frontend/package.json` — renamed to `agentic-claims-poc-frontend`; scripts `dev`, `build`, `preview`, `lint`, `typecheck`, `test`, `format`.
- `frontend/vite.config.ts` — Vite + Tailwind plugins, dev proxy for `/health` and `/api`, Vitest jsdom config inline.
- `frontend/src/main.tsx`, `frontend/src/App.tsx` — page renders project title and a backend health indicator that fetches `/health` on mount.
- `frontend/src/App.test.tsx` — two tests: heading renders; "backend: ok" appears when fetch resolves 200.
- `frontend/src/index.css` — single `@import "tailwindcss";` line.
- `frontend/src/setupTests.ts` — jest-dom matcher extension for Vitest.
- `frontend/.prettierrc`, `frontend/.env.example` — formatter config and env-var template.
- `frontend/index.html` — title set, default favicon link removed (no public/ directory in scaffold).
- `scripts/setup-dev-db.sh` — bash script with sanitise/validate/abort/execute pattern; checks psql on PATH, server reachable, Postgres major >= 16, pgvector availability; creates `agentic_claims_dev` database; enables `vector` extension. Idempotent. Made executable.
- `infra/.gitkeep` — placeholder so the directory ships now; `azure-devops-pipeline.yml` arrives in Phase 7.
- `.github/workflows/ci.yml` — two jobs (`backend`: ruff + mypy + pytest via uv; `frontend`: eslint + tsc + vitest via npm); triggers on PR and pushes to `main`.
- `README.md` — added a Local development section (Postgres 17 install, dev DB script, backend run, frontend run, test/lint/typecheck commands).
- `CLAUDE.md` — Current Status block updated to "Phase 0 complete; Phase 1 next".
- `docs/prompts/01-phase-0-repository-scaffold-plan.md` — saved before approval; approval footer appended after the architect approved with the three answers and three amendments. Body updated to record the answers, the amendments, and the postgresql@16 → postgresql@17 switch (see Issues below).
- `docs/prompts/01-phase-0-repository-scaffold-report.md` — added retrospectively after the architect introduced the report-file convention. Captures the same Phase 0 outcomes Claude Code reported in chat, in the canonical four-artefact location.

**Tests:** 9 passing, 0 failing.

- Backend (pytest): 7 — `test_health` (1), `test_settings` (6: defaults + 5 YAML-loader guards).
- Frontend (vitest): 2 — heading renders; backend status reads "ok" on 200.
- All ruff, mypy, eslint, tsc checks clean.

**Issues discovered:**

- **Homebrew pgvector bottle does not include `postgresql@16`.** The architect's amendment A specified `brew install postgresql@16 && brew install pgvector`. The brew install commands all reported success (exit 0), but the `pgvector` formula's pre-built bottle ships extension files only for `postgresql@17` and `postgresql@18` — there is no extension dir under `/opt/homebrew/share/postgresql@16/`, so `CREATE EXTENSION vector` against `@16` would fail. Per the amendment ("if at any point brew, postgresql@16, or pgvector fails to install or start cleanly, stop and report"), execution paused and the architect chose to switch to `postgresql@17`. CLAUDE.md and BUILD-PLAN.md retain "Postgres 16+" wording (still accurate); the README's Local development section pins to 17 explicitly with a note about the bottle limitation. The `setup-dev-db.sh` script enforces only the 16+ floor, so future moves to 18 won't require a script change.
- **uv 0.9.11 default Python is 3.14.** `uv init` set `requires-python = ">=3.14"` because the latest installed Python on the dev machine is 3.14. Overridden to `>=3.11` per the project's stack target. CI installs 3.11 explicitly.
- **Vite scaffold ships React 19 + TypeScript 6 + Vite 8 + Vitest 4.** All cutting-edge, all green against the tooling we configured. No version pins beyond the major bumps Vite chose; flagging in case a future upstream change breaks the build.
- **Frontend lockfile platform-gap on first CI run.** The lockfile generated locally on darwin-arm64 was missing top-level entries for `@emnapi/core` and `@emnapi/runtime` (transitive deps of `@tailwindcss/oxide`'s wasm-shim path that Linux x64 needs). `npm ci` rejected the lockfile on the GitHub Actions runner with EUSAGE on the first push. Fix: removed `node_modules` and `package-lock.json`, re-ran `npm install` cleanly, committed the regenerated lockfile (commit `3ef8b31`). CI then green on both jobs. No source-code change required.

**Next:** Phase 1 — Data layer and settings infrastructure.

---

### 2026-05-08 — Phase 1: Data layer and settings infrastructure

**Phase / Prompt:** Phase 1 — [`docs/prompts/02-phase-1-data-layer.md`](prompts/02-phase-1-data-layer.md)

**Plan (approved):** [`docs/prompts/02-phase-1-data-layer-plan.md`](prompts/02-phase-1-data-layer-plan.md) (approved 2026-05-08T15:39:42Z)

**Plan iterations:** 0 rejected. The architect approved the canonical plan as proposed across all seven headline decisions (Alembic with raw SQL; chain formula and canonicalisation as documented; full schema with status enum and `scenario_tag` up front; five settings sub-models with Decimal monetary and dimension pinned to 384; CI changes including the optional `pip-audit` and `npm audit`; new dependencies as flagged; docs fix-up Render Postgres → Neon).

**Report:** [`docs/prompts/02-phase-1-data-layer-report.md`](prompts/02-phase-1-data-layer-report.md)

**Prompt summary:** Land the persistent foundation — versioned database schema (claims, audit_log, policy_chunks), settings architecture extended with five named sub-models, cryptographically chained audit vault written defensively, a 2–3 page generic commercial-property policy excerpt indexed via `bge-small-en-v1.5`, and a synthetic claim generator covering the three locked demo scenarios. Plus the documentation fix-ups (Render Postgres → Neon) and a Postgres+pgvector service container in CI so the new tests run against a real database.

**What changed:**

- `pyproject.toml` — added `psycopg[binary]>=3.2`, `pgvector>=0.3`, `alembic>=1.13`, `sqlalchemy>=2.0`, `sentence-transformers>=3.0`; dev `pip-audit>=2.7`. Mypy override stanza for the third-party libraries that ship without `py.typed` markers (`pgvector`, `sentence_transformers`, `transformers`).
- `uv.lock` — regenerated by `uv add`.
- `.env.example` — repo-root template documenting `DATABASE_URL` (required), `ANTHROPIC_API_KEY` and `MISTRAL_API_KEY` (Phase 2 placeholders).
- `backend/alembic.ini` — Alembic config; `script_location = backend/db/migrations`; URL is read at runtime from `Settings`, not baked into the file.
- `backend/db/__init__.py`, `backend/db/connection.py` — single source of truth for opening psycopg connections; registers `pgvector.psycopg` adapter at module import; applies session `statement_timeout` from settings (literal-interpolated as Postgres `SET` doesn't accept parameters).
- `backend/db/migrations/env.py` — Alembic environment; reads `DATABASE_URL` from `Settings`; rewrites the URL to `postgresql+psycopg://` so SQLAlchemy picks the psycopg-3 driver (we don't install psycopg2). `target_metadata=None` because there is no ORM.
- `backend/db/migrations/script.py.mako` — Alembic template.
- `backend/db/migrations/__init__.py`, `backend/db/migrations/versions/__init__.py` — package markers so mypy treats the tree as importable.
- `backend/db/migrations/versions/0001_initial_schema.py` — initial migration: `CREATE EXTENSION IF NOT EXISTS vector`; `claims` (with `scenario_tag` and full status enum); `audit_log` with `CHAR(64)` hash columns and `agent` CHECK; `policy_chunks` with `VECTOR(384)`, HNSW + cosine ops index, UNIQUE on (`source_path`, `chunk_index`); BTREE indexes on `status`, `scenario_tag`, `correlation_id`, `claim_id`, `created_at`, `source_path`.
- `backend/settings.py` — five new sub-models: `DatabaseSettings` (URL, pool sizing, `statement_timeout_ms`, `echo_sql`; scheme validator), `LLMSettings` with nested `AnthropicSettings` and `MistralProviderSettings`, `EmbeddingSettings` (model name, dimension pinned to 384, normalisation, batch size), `LangfuseSettings` (disabled by default; "enabled requires both keys" model validator), `EscalationSettings` (Decimal `auto_approve_ceiling`, validator/adjuster confidence floors, `hard_rules` Literal list, `policy_path`). `Settings` gains a `_apply_overlays` before-validator that merges YAML, then named env aliases (`DATABASE_URL`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`) on top so the named form trumps the nested form. `database` field uses a `default_factory` (`_resolve_database_settings`) so the type system stays honest while the runtime requirement (`DATABASE_URL` must be present) is preserved by the factory.
- `backend/settings.yaml.template` — extended with `database`, `llm` (with `anthropic` and `mistral` sub-blocks), `embedding`, `langfuse`, `escalation` blocks. Secret fields are commented as "loaded from env — do not put values here".
- `backend/app/audit/__init__.py` — public surface: `AuditEvent`, `AuditWriter`, `AuditRow`, `verify_chain`, `ChainVerification`, `AuditBreak`.
- `backend/app/audit/event.py` — `AuditEvent` Pydantic model: `correlation_id`, `claim_id`, `agent` Literal, `step` (non-empty after strip), `payload`, `created_at` (validator rejects naive datetimes; normalises to UTC).
- `backend/app/audit/canonical.py` — `canonicalise(event)` with `sort_keys=True`, `separators=(",",":")`, Pydantic dump in `mode="python"` so the JSON encoder's `default` callback (`_encode_or_reject`) sees raw types: encodes UUIDs / datetimes / dates, refuses `Decimal`, `set`, `bytes`, naive datetimes with diagnostic messages.
- `backend/app/audit/chain.py` — `compute_row_hash(canonical: bytes) -> str`, `compute_chain_hash(row_hash, prev_chain_hash) -> str`. Named constants `GENESIS_CHAIN_HASH = "0" * 64` and `HASH_HEX_LENGTH = 64`. Defensive guards: type, length, hex, lowercase.
- `backend/app/audit/writer.py` — `AuditWriter.append`: sanitise (canonicalise upfront) → validate (advisory lock + claim FK lookup) → abort (`ValueError` with payload excerpt) → execute (single `INSERT ... RETURNING`). Lock keyed to `0x4144_4954`. Translates `psycopg.errors.ForeignKeyViolation` to `ValueError` for callers.
- `backend/app/audit/verify.py` — `verify_chain(conn) -> ChainVerification`. Walks `audit_log` in `audit_id` order, recomputes both hashes per row, returns the first break with kind `row_hash_mismatch` or `chain_hash_mismatch`.
- `backend/app/escalation/__init__.py` — directory placeholder for Phase 4's `policy.yaml`.
- `backend/app/prompts/__init__.py`, `backend/app/prompts/system/.gitkeep`, `backend/app/prompts/user/.gitkeep` — externalised prompt directory ready for Phase 2.
- `backend/data/__init__.py` — package marker.
- `backend/data/sample_policy.txt` — generic commercial-property excerpt (no insurer or client names): General Conditions, Definitions, Named Perils Covered, Exclusions (with explicit "flood endorsement is NOT attached" pointer), Sub-Limits, Business Interruption, Duties After Loss.
- `backend/data/seed_claims.py` — `generate_claims()` (reproducible, RNG seed `20260508`) producing nine claims: three scripted scenarios tagged `auto_approve` ($85k water damage), `threshold_escalation` ($850k fire), `guardrail_escalation` ($1.4M storm-complex with reference to an "unlisted endorsement"), plus six untagged background claims spanning sprinkler leakage, vandalism, theft, smoke, hail, windstorm. `insert_claims(conn, claims, *, truncate_first)` aborts on a non-empty table unless `truncate_first=True`. CLI flag `--allow-truncate`.
- `backend/data/index_policy.py` — `chunk_markdown_sections(text, source_path, tokenizer, *, target_min, target_max)` produces `PolicyChunk` records, never crossing a section boundary, packed near the 200–300 token range using the embedding model's tokenizer. End-to-end pipeline loads the model, embeds with cosine-normalised vectors at `batch_size=32`, deletes prior rows for the same `source_path` and bulk-inserts in one transaction. Asserts the model's output dimension matches `EmbeddingSettings.dimension`.
- `backend/tests/conftest.py` — added `db_settings` (session-scoped `Settings()`), `migrated_db` (session-scoped: runs `alembic upgrade head`), `clean_db` (function-scoped: yields a connection with all three Phase 1 tables truncated and identities restarted).
- `backend/tests/test_settings_phase1.py` — 11 tests: named alias, scheme validator, pool/timeout defaults, locked LLM model identifiers, embedding dimension lock, embedding defaults, Langfuse default-disabled, Langfuse enabled-without-keys guard, escalation defaults, escalation float-range guards, top-level `extra='forbid'` rejection.
- `backend/tests/test_audit_canonical.py` — 7 tests: deterministic across orderings, no whitespace, naive-datetime rejection, Decimal/set/bytes rejection, empty-step rejection.
- `backend/tests/test_audit_chain.py` — 8 tests: genesis constant, SHA-256 round-trip, type/empty/length/hex/case guards on the inputs, golden chain output.
- `backend/tests/test_audit_writer.py` — 7 tests: genesis prev for first append, three-event chain linkage, missing-claim diagnostic, empty-step / naive-datetime guard triggers, JSONB round-trip, two-thread concurrency under the advisory lock (10 events, no fork).
- `backend/tests/test_audit_verify.py` — 4 tests: empty table OK, clean three-row chain OK, payload tamper detected, chain-hash tamper detected.
- `backend/tests/test_seed_claims.py` — 8 tests: count, scenario coverage, jurisdictions, reproducibility, claim-number uniqueness, positive amounts, refuse-non-empty, truncate-overwrites.
- `backend/tests/test_index_policy.py` — 8 tests + 1 conditional: file presence, all expected sections covered, positive token counts, practical token cap, sequential indexes, empty-text guard, no-headings guard, inverted target-range guard. Conditional `RUN_EMBEDDING_TESTS=1` end-to-end indexing test.
- `backend/tests/test_schema.py` — 5 tests: column sets per table, audit_log indexes, policy_chunks indexes (HNSW + source_path), FK from audit_log to claims, vector extension enabled.
- `.github/workflows/ci.yml` — backend job gains `services.postgres: pgvector/pgvector:pg16` (health check, port 5432), `DATABASE_URL` env, an `alembic upgrade head` step before pytest, and an advisory `pip-audit --strict` step. Frontend job gains an advisory `npm audit --audit-level=high` step.
- `docs/architecture-stack-reference.md` — three table rows and two prose locations updated from Render-Postgres wording to Neon (`eu-central-1` Frankfurt, Postgres 17, pgvector 0.8.0). Production-side wording (Azure SQL Managed Instance) unchanged.
- `CLAUDE.md` — Tech Stack > Data, Hosting & CI line, Architectural Decisions (Database, Hosting) updated for Neon. Current Status updated to Phase 1 complete.
- `README.md` — Local development section gains "Configure environment variables", "Run database migrations", and "Seed and index" steps, with Neon-from-local override documented.
- `docs/prompts/02-phase-1-data-layer-plan.md` — saved before approval; approval footer appended at 2026-05-08T15:39:42Z.
- `docs/prompts/02-phase-1-data-layer-report.md` — written after execution.

**Tests:** 67 passing, 1 skipped (the optional `RUN_EMBEDDING_TESTS=1` end-to-end indexing test), 0 failing.

- Backend (pytest): 65 passing, 1 skipped — settings (11), audit canonical (7), audit chain (8), audit writer (7), audit verify (4), seed_claims (8), index_policy (8 + 1 conditional), schema (5), plus the Phase 0 health (1) and the original Phase 0 settings (6).
- Frontend (vitest): 2 passing — unchanged from Phase 0.
- All ruff, mypy, eslint, tsc checks clean.

**Issues discovered:**

- **`postgres SET` does not accept parameterised values.** Initial `cur.execute("SET statement_timeout = %s", (...))` produced `psycopg.errors.SyntaxError: syntax error at or near "$1"`. Fixed in `backend/db/connection.py` by validating the integer at the boundary and interpolating it as a literal (`f"SET statement_timeout = {timeout_ms}"`). Type-safe because the value is constrained `ge=0` by Pydantic and re-cast to `int` before formatting.
- **SQLAlchemy defaulted to psycopg2.** Alembic's URL went through SQLAlchemy, which loaded the `psycopg2` DBAPI by default. We don't install psycopg2 (we use psycopg-3). Fixed by rewriting the URL scheme to `postgresql+psycopg://` in `backend/db/migrations/env.py`. Documented inline.
- **Pydantic `mode="json"` silently transforms `Decimal`, `set`, `bytes`.** Original canonicaliser used `model_dump(mode="json")` and a `default=` callback to refuse ambiguous types — but `mode="json"` had already converted them, so the callback never fired. Fixed by switching to `mode="python"` and moving JSON-safe encoding (UUID, datetime, date) into the same `default` callback so the rejection cases for Decimal / set / bytes get to see the raw types first.
- **mypy did not understand the model_validator-based env injection.** `Settings()` calls failed type-checking with `Missing named argument "database"`. Fixed by giving `database` a `default_factory=_resolve_database_settings` that reads `DATABASE_URL` from env (or `.env`) at construction time. The runtime requirement is preserved (a missing URL raises in the factory); the type system is now honest.
- **Frontend tests touched only by the toolchain refresh.** No frontend code changes in this phase; the `npm audit --audit-level=high` advisory step is the only frontend CI delta.
- **Anonymisation review.** `grep -i 'aspen\|axa\|chubb\|swiss re\|munich re' .` against the working tree returned no matches; sample policy and seed narratives use generic claimant names.

**Next:** Phase 2 — LLM Gateway and Validator agent.

---

### 2026-05-11 — Phase 2: LLM Gateway and Validator agent

**Phase / Prompt:** Phase 2 — [`docs/prompts/03-phase-2-llm-gateway-and-validator.md`](prompts/03-phase-2-llm-gateway-and-validator.md)

**Plan (approved):** [`docs/prompts/03-phase-2-llm-gateway-and-validator-plan.md`](prompts/03-phase-2-llm-gateway-and-validator-plan.md) (approved 2026-05-11T11:18:07Z)

**Plan iterations:** 0 rejected.

**Report:** [`docs/prompts/03-phase-2-llm-gateway-and-validator-report.md`](prompts/03-phase-2-llm-gateway-and-validator-report.md)

**Prompt summary:** Build the LLM Gateway abstraction (`LLMProvider` ABC plus `AnthropicProvider` and `MistralProvider`), the `APILogger` that emits one structured JSON record per LLM call, the `PromptLoader` that reads externalised prompts from `backend/app/prompts/system/` and `backend/app/prompts/user/`, and the Validator agent that embeds a claim narrative, retrieves the top-3 policy chunks via pgvector cosine distance, calls Mistral Large with strict system/user separation, parses the JSON verdict (with an anti-hallucination cross-check on cited chunk IDs), and writes a complete audit-log entry. Plus the two preamble fix-ups (pyproject version bump and tightened Render build command).

**What changed:**

- `pyproject.toml` — version bumped `0.0.1 → 0.2.0`; added `anthropic>=0.40` and `mistralai>=1.5` runtime deps; mypy override block extended to ignore the bundle-less `mistralai.*` package.
- `uv.lock` — regenerated by `uv add`. Resolved versions: `anthropic 0.100.0`, `mistralai 2.4.5`.
- `render.yaml` — `buildCommand` tightened from `uv sync` to `uv sync --no-dev` so the production container drops pytest / ruff / mypy / pip-audit. CI is unaffected (it still uses `uv sync` to install the dev group).
- `backend/settings.py` — added `LoggingSettings` (api_log_enabled, api_log_excerpt_chars, api_log_path), `RetrievalSettings` (policy_source_path, top_k), and four new fields on `LLMSettings` (validator_max_tokens, validator_temperature, request_timeout_s, pricing). Bounds tight enough that a typo at config time is rejected with a clear ValidationError message.
- `backend/settings.yaml.template` — extended with matching `logging` and `retrieval` blocks plus the new `llm` fields; pricing example commented out.
- `backend/app/prompts/__init__.py` — re-exports the loader public surface.
- `backend/app/prompts/loader.py` — new `PromptLoader` class with strict placeholder substitution (missing placeholders raise `PromptFormatError`), path-traversal guard, 64KB size cap, and module-level content cache.
- `backend/app/prompts/system/validator.md` — first externalised system prompt: defines the coverage-validator persona, the strict JSON output schema, and the anti-hallucination citation rule.
- `backend/app/prompts/user/validator_template.md` — first externalised user template with `{claim_narrative}` and `{retrieved_chunks}` placeholders.
- `backend/app/prompts/system/.gitkeep`, `backend/app/prompts/user/.gitkeep` — removed; real files now exist.
- `backend/app/logging/__init__.py` — re-exports `APICallRecord`, `APILogger`, `compute_cost_usd`.
- `backend/app/logging/api_logger.py` — new module. `APICallRecord` Pydantic model with the locked JSON shape (correlation_id, agent, step, provider, model, prompt/response excerpts, tokens, cost, latency, started/completed timestamps, optional error). `APILogger` class with enabled-flag gating, configurable excerpt budget, optional redactor, default stdlib-logger sink, and optional sidecar file sink. `compute_cost_usd` computes USD cost from the Settings pricing table; returns null when no rate is configured.
- `backend/app/llm/__init__.py` — re-exports `LLMProvider`, `ProviderResponse`, `LLMProviderError`, `AnthropicProvider`, `MistralProvider`, `get_provider`.
- `backend/app/llm/provider.py` — `LLMProvider` ABC. `complete(...)` is keyword-only with separate `system` and `user` string args plus required `correlation_id`, `agent`, `step` metadata for the APILogger record. `ProviderResponse` frozen dataclass with text, model, token counts, latency, and `raw` SDK dump. `LLMProviderError` is the single funnel error.
- `backend/app/llm/anthropic_provider.py` — wraps `anthropic.Anthropic`. Passes `system` as a top-level parameter; `user` content goes in `messages=[{role:user,...}]`. Coerces `response.content[0].text`, `response.usage.input_tokens`/`output_tokens`. Translates `anthropic.APIError` → `LLMProviderError`. Refuses empty / non-text first content block. Empty API key refused at construction.
- `backend/app/llm/mistral_provider.py` — wraps `mistralai.client.Mistral`. Places the system message as the first list entry (Mistrals SDK convention); user message second. Requests native JSON mode via `response_format={"type":"json_object"}` when `response_format="json"`. Translates `mistralai.client.errors.SDKError` → `LLMProviderError`. Refuses empty choices / empty / non-string content. Empty API key refused at construction.
- `backend/app/llm/factory.py` — `get_provider(settings, vendor)` keyed cache (module-level dict, not lru_cache, because Settings is unhashable). Constructs a fresh `APILogger` per Settings instance; passes the settings pricing table through to the provider. `clear_provider_cache()` exposed for tests.
- `backend/app/agents/__init__.py` — re-exports the Validator types.
- `backend/app/agents/validator_models.py` — `RetrievedChunk` (chunk_id, section, content, similarity 0..1), `CitedChunk` (chunk_id, section), `ValidatorVerdict` (covered, confidence 0..1, reasoning, policy_basis, cited_chunks 1..3), `ValidatorResult` (claim_id, correlation_id, verdict, retrieved_chunks, model, latency_ms).
- `backend/app/agents/validator.py` — `Validator` class with collaborator injection (provider, prompt_loader, embedder, connection_factory, settings). `evaluate(claim_id, correlation_id)` orchestrates: open connection → load narrative → embed → retrieve top-K via cosine distance (with `%s::vector` cast on the parameter to satisfy pgvector) → format chunks for prompt → call provider with JSON mode → parse verdict → cross-check cited chunk IDs against retrieved set → write audit log entry → return `ValidatorResult`. Audit log written on every exit path including provider failures. Embedding model loaded lazily via module-level `lru_cache(maxsize=1)`; tests pass a stub embedder so the SentenceTransformer cold-load is paid only by the gated e2e test.
- `backend/tests/conftest.py` — extended with `prompt_loader` (cache-clearing), `stub_embedder` (deterministic 384-dim hash-based), `mock_provider` (capturing `LLMProvider` stub), `null_api_logger` (discarding sink), plus the `MockProvider` and `MockProviderCall` dataclasses.
- `backend/tests/test_settings_phase2.py` — 13 tests covering the new sub-models and field bounds.
- `backend/tests/test_prompt_loader.py` — 11 tests covering the happy path against the real prompt files plus every guard in `_load` and `_read_prompt_file` against per-test tmp_path trees.
- `backend/tests/test_api_logger.py` — 13 tests covering canonical-JSON emission, disabled no-op, error-path record shape, redactor application, excerpt truncation, file sink, pricing calculation including missing-rate-returns-None and negative-rate-rejection, zero-budget guard.
- `backend/tests/test_llm_provider_anthropic.py` — 5 tests via `monkeypatch.setattr` on the SDK client: empty-key refusal, request shape (system top-level + user in messages list), `anthropic.APIError` → `LLMProviderError`, empty-system-prompt rejection, empty-content-block rejection.
- `backend/tests/test_llm_provider_mistral.py` — 5 tests: empty-key refusal, request shape (system first message, JSON-mode flag, timeout_ms conversion), `SDKError` → `LLMProviderError`, empty-content rejection, no-choices rejection.
- `backend/tests/test_validator.py` — 9 unit tests using the real `clean_db` fixture (so SQL + audit chain are real) and the mocked provider/embedder: happy path with assertions on prompt shape and audit payload, claim-not-found, empty-narrative, no-chunks-indexed, embedder-wrong-dimension, non-JSON response, schema-failing JSON, cited-chunk-not-in-retrieved-set (anti-hallucination), provider-raises (audit row written before exception propagates). Plus 1 gated `test_validator_real_call` (skipped unless `RUN_LLM_E2E_TESTS=1` and `MISTRAL_API_KEY` are set).
- `backend/tests/test_validator_prompts.py` — 3 golden-shape tests for the externalised prompts.
- `CLAUDE.md` — Current Status updated to "Phase 2 complete; Phase 3 next".
- `docs/prompts/03-phase-2-llm-gateway-and-validator-plan.md` — saved before approval; approval footer appended at 2026-05-11T11:18:07Z.
- `docs/prompts/03-phase-2-llm-gateway-and-validator-report.md` — written after execution.

**Tests:** 124 passing, 2 skipped (the Phase-1 `RUN_EMBEDDING_TESTS=1` indexing test and the Phase-2 `RUN_LLM_E2E_TESTS=1` Validator real-call test), 0 failing.

- Backend (pytest): 122 passing, 2 skipped. Phase 2 adds **59 new tests + 1 new conditional skip**: settings (13), prompt_loader (11), api_logger (13), anthropic_provider (5), mistral_provider (5), validator unit + integration (9), validator prompts (3); the conditional skip is the gated Mistral e2e.
- Gated e2e test was executed once locally against the live Mistral API (7.35s including the round trip); the call returned a typed `ValidatorVerdict` with `covered=true`, confidence > 0.0, and a citation that survived the anti-hallucination cross-check.
- Frontend (vitest): 2 passing — unchanged.
- All `uv run ruff check .`, `uv run mypy backend` clean (53 source files).

**Issues discovered:**

- **pgvector `<=>` operator requires a `vector`-typed parameter.** Initial validator query `WHERE embedding <=> %s` failed with `operator does not exist: vector <=> double precision[]` because psycopg binds the parameter as `double precision[]`, not `vector`. Fixed by casting at the SQL level: `embedding <=> %s::vector` in both the `SELECT` similarity expression and the `ORDER BY` clause. Documented inline.
- **Mistral SDK 2.x lives at `mistralai.client.Mistral`, not `mistralai.Mistral`.** The plan referenced `mistralai>=1.5`; the resolved version is 2.4.5 and the top-level `mistralai` package re-exports nothing. The provider imports from `mistralai.client` and from `mistralai.client.errors`. Documented in the provider module header.
- **Anthropic 0.100.0 `APIError` requires a real `httpx.Request`.** Tests that raise `anthropic.APIError(message=..., request=SimpleNamespace(...))` fail mypy with `Argument "request" has incompatible type "SimpleNamespace"; expected "Request"`. Fixed the test by constructing a real `httpx.Request` instance.
- **Mistral SDK 2.x `SDKError` constructor takes `raw_response: httpx.Response`, not `status_code/body/headers`.** Updated the test accordingly.
- **Lint required import-block organisation.** Two ruff `I001` errors auto-fixed.
- **mypy refused `lru_cache`-decorated `SentenceTransformer` return.** The third-party library does not ship `py.typed`. Resolved by typing `_load_embedding_model` as returning `Any` with a docstring note; callers still receive the real instance.

**Next:** Phase 3 — Remaining agents (Doc-Parser, Adjuster, Guardrail).

---
