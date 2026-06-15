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

### 2026-05-11 — Phase 3: Remaining agents (Doc-Parser, Adjuster, Guardrail)

**Phase / Prompt:** Phase 3 — [`docs/prompts/04-phase-3-remaining-agents.md`](prompts/04-phase-3-remaining-agents.md)

**Plan (approved):** [`docs/prompts/04-phase-3-remaining-agents-plan.md`](prompts/04-phase-3-remaining-agents-plan.md) (approved 2026-05-11T13:34:43Z)

**Plan iterations:** 0 rejected.

**Report:** [`docs/prompts/04-phase-3-remaining-agents-report.md`](prompts/04-phase-3-remaining-agents-report.md)

**Prompt summary:** Build the three remaining agents on top of the Phase 2 plumbing — Doc-Parser (Claude Haiku, structured field extraction from FNOL narratives), Adjuster (Mistral Large, market-data lookup + within-range LLM pick + range-enforcement guard), Guardrail (Claude Haiku, deterministic regex floor for PII / hallucinated-citation / bias plus an LLM-side semantic check, fail-closed combine). Each agent is independent (no shared base class), each uses externalised prompts via `PromptLoader`, each writes a full audit-log entry. Plus the preamble fix-up (`pyproject.toml` version `0.2.0 → 0.3.0`).

**What changed:**

- `pyproject.toml` — version bumped `0.2.0 → 0.3.0`.
- `backend/settings.py` — `LLMSettings` extended with six per-call defaults (`doc_parser_max_tokens`/`temperature`, `adjuster_max_tokens`/`temperature`, `guardrail_max_tokens`/`temperature`). New `AdjusterSettings` sub-model with `market_data_path`, threaded into `Settings`.
- `backend/settings.yaml.template` — matching `llm.*` block extensions and a new `adjuster:` block.
- `backend/data/market_data.yaml` — new static lookup table (six claim_types × three severities = 18 cells). Severity-bands and ranges sized so the locked demo amounts ($85k water_damage, $850k fire, $1.4M storm_complex) land comfortably inside their cells. Schema version field for future-proofing.
- `backend/data/market_data.py` — new loader module. `MarketRange` Pydantic model, `MarketDataTable.lookup(claim_type, reported_amount) -> MarketRange` combining sanitise/validate/abort/execute with severity derivation. Module-level path-keyed cache; `clear_market_data_cache()` for tests.
- `backend/app/agents/_shared.py` — new module exposing `extract_json_block`, `excerpt`, `clamp_unit`, `new_correlation_id`. Replaces the per-agent copies the Validator carried; the four agents now import the same helpers.
- `backend/app/agents/validator.py` — refactored to import from `_shared.py`. No interface change; the local helpers were removed and replaced with aliased imports so call sites stay identical. The `_extract_json_block` wrapper delegates to the shared helper with the Validator's agent label.
- `backend/app/agents/doc_parser_models.py` — `DocParserOutput` (loss_date, jurisdiction, claim_type, claimed_amount, claimant_identifier, narrative_summary) and `DocParserResult` (wraps output + claim_id, correlation_id, model, latency_ms). Field bounds enforce schema at the Pydantic boundary.
- `backend/app/agents/doc_parser.py` — `DocParser` class with constructor injection. `evaluate(claim_id, correlation_id)` orchestrates: load narrative from DB → call Haiku via Gateway → parse strict JSON → audit. Fail-fast on malformed JSON / bad date / non-positive amount / oversized summary; the audit log captures the failure path.
- `backend/app/prompts/system/doc_parser.md` and `backend/app/prompts/user/doc_parser_template.md` — externalised prompts. System prompt locks the persona, the JSON schema, the controlled-vocabulary list for `claim_type`, and the no-prose-no-fencing rule. User template has a single `{claim_narrative}` placeholder.
- `backend/app/agents/adjuster_models.py` — `AdjusterOutput` (recommended_settlement, confidence, reasoning) and `AdjusterResult` (wraps output + market_range + run metadata). `AdjusterResult` carries a `model_validator(mode="after")` that re-asserts the within-range invariant, so direct construction (e.g. from an audit-log replay) cannot break the contract.
- `backend/app/agents/adjuster.py` — `Adjuster` class. `evaluate(claim_id, correlation_id, parsed_claim, validator_verdict)` orchestrates: lookup `(claim_type, severity)` in `MarketDataTable` → call Mistral via Gateway with JSON-mode → parse and **re-validate** the value is in `[floor, ceiling]` (out-of-bounds raises `ValueError`, never silently clamps) → audit. The reasoning prompt is constrained not to cite policy.
- `backend/app/prompts/system/adjuster.md` and `backend/app/prompts/user/adjuster_template.md` — externalised prompts. System prompt names the role, the within-range constraint in strong language ("MUST be between floor and ceiling inclusive"), the no-policy-citation rule, and the reasoning style.
- `backend/app/agents/guardrail_models.py` — `GuardrailFlagKind` Literal (`pii | bias | hallucinated_citation`), `GuardrailFlagSource` Literal (`rule | llm`), `GuardrailFlag` (kind, detail, source), `GuardrailOutput` (passed, flags, summary), `GuardrailResult` wrapper. `GuardrailOutput` carries a `model_validator` enforcing fail-closed (`flags non-empty ⇒ passed=False` and `not flags ⇒ passed=True`).
- `backend/app/agents/guardrail_rules.py` — `GuardrailRuleEngine` deterministic detector. PII patterns (SSN, email, US phone, credit-card-like — four explicit regexes). Citation-candidate regex with chunk-content allow-set check (substring containment). Protected-characteristic terms matched with word-boundary regex (catches the `age`-inside-`damage` foot-gun).
- `backend/app/agents/guardrail.py` — `Guardrail` class. `evaluate(claim_id, correlation_id, adjuster_result, retrieved_chunks)` orchestrates: run rule engine → call Haiku via Gateway with the rule findings inlined into the prompt (so the LLM does not duplicate them) → parse LLM flags → combine and decide fail-closed → audit.
- `backend/app/prompts/system/guardrail.md` and `backend/app/prompts/user/guardrail_template.md` — externalised prompts. System prompt enumerates the three check kinds, locks the JSON schema (no `passed` field — the agent computes it), instructs the LLM not to duplicate the rule-engine findings.
- `backend/app/agents/__init__.py` — extended exports cover `DocParser`, `DocParserOutput`, `DocParserResult`, `Adjuster`, `AdjusterOutput`, `AdjusterResult`, `Guardrail`, `GuardrailRuleEngine`, `GuardrailOutput`, `GuardrailResult`, `GuardrailFlag`, `GuardrailFlagKind`, `GuardrailFlagSource`.
- `backend/tests/test_market_data.py` — 14 tests: real YAML load, lookup for each demo amount, severity boundaries inclusive on upper, case-insensitive claim_type input, unknown claim_type, non-positive amount, empty claim_type, missing file, malformed YAML, unsupported schema version, missing severity, ceiling-below-floor, `MarketRange` negative bounds, `MarketRange.contains` inclusive on both ends.
- `backend/tests/test_doc_parser.py` — 11 tests (10 unit + 1 gated): happy path, claim-not-found, empty narrative, non-JSON response with audit, schema-failing JSON (negative amount), bad ISO date, oversized summary, provider-raises with audit, audit narrative truncation, plus 1 gated real-call test.
- `backend/tests/test_doc_parser_prompts.py` — 2 golden-shape tests.
- `backend/tests/test_adjuster.py` — 10 tests (9 unit + 1 gated): happy path (in-range), out-of-range above ceiling, out-of-range below floor, `AdjusterResult` direct construction re-validation, unknown claim_type lookup, non-JSON response, schema-failing JSON, provider-raises with audit, fire/severe range threading, plus 1 gated real-call test.
- `backend/tests/test_adjuster_prompts.py` — 2 golden-shape tests.
- `backend/tests/test_guardrail.py` — 16 collected (parameterised PII test expands to four cases; 12 base test functions): clean reasoning passes, PII patterns (SSN/email/phone/credit_card_like — four parameterised cases), hallucinated citation fires, legitimate citation does not flag, protected-characteristic term flags, LLM flags merge with rule flags, non-JSON response raises, missing `flags` key, `flags` not a list, empty retrieved chunks (rule engine), fail-closed model validator, provider-raises with audit, plus 1 gated real-call test.
- `backend/tests/test_guardrail_prompts.py` — 2 golden-shape tests.
- `CLAUDE.md` — Current Status updated to "Phase 3 complete; Phase 4 next".
- `docs/prompts/04-phase-3-remaining-agents-plan.md` — saved before approval; approval footer appended at 2026-05-11T13:34:43Z.
- `docs/prompts/04-phase-3-remaining-agents-report.md` — written after execution.

**Tests:** 178 passing, 5 skipped (the Phase-1 `RUN_EMBEDDING_TESTS=1` indexing test, plus four `RUN_LLM_E2E_TESTS=1` gated tests — Phase 2's Validator real-call plus the three new Phase 3 real-call tests for Doc-Parser, Adjuster, Guardrail), 0 failing.

- Backend (pytest): 178 passing, 5 skipped. Phase 3 adds **56 passing new tests + 3 new conditional skips**: market_data (14), doc_parser unit (10), doc_parser prompts (2), adjuster unit (9), adjuster prompts (2), guardrail unit+rules (15 effective, with one parameterised PII test expanding to 4 cases), guardrail prompts (2).
- Frontend (vitest): 2 passing — unchanged.
- All `uv run ruff check .`, `uv run mypy backend` clean (69 source files).

**Issues discovered:**

- **Bias substring match fired on the substring "age" inside "damage".** The first cut of `GuardrailRuleEngine._bias_flags` used plain substring containment against `{"race", "ethnicity", ..., "age"}`. The first test run failed `test_clean_reasoning_passes` because the test's "damage scope supports the value" reasoning contains "age" as a substring of "damage". Fixed by switching the protected-characteristic list from a `frozenset[str]` to a tuple of `(name, compiled_word_boundary_regex)` pairs, matched via `pattern.search(text)`. Word boundaries also cover the equivalent "manager" / "stage" / "image" false-positives without listing them. Documented inline.
- **mypy `unused-ignore` on the market-data loader.** The first cut of `_parse_claim_type_entry` had `# type: ignore[index]` comments after `bands[severity] = _SeverityBand(...)` and `ranges[severity] = {...}` lines. mypy didn't need them (the loop variable's narrowed Literal type satisfies the dict indexer). Removed both comments; static checks clean.
- **Ruff `I001` import-block formatting on every new module.** Auto-fixed by `uv run ruff check --fix .`.
- **Ruff `SIM110` on `_citation_is_in_allow_set`.** Replaced the `for / return True / return False` loop with `return any(name in entry for entry in allow_set)`.
- **Anonymisation review.** `grep -i 'aspen\|axa\|chubb\|swiss re\|munich re' .` against the working tree returned no matches; new fixtures and prompts use generic claimant names.

**Next:** Phase 4 — Pipeline orchestrator.

---

## Phase 4 — Pipeline Orchestrator

**Date:** 2026-06-14

**Phase / Prompt:** Phase 4 — [`docs/prompts/05-phase-4-pipeline-orchestrator.md`](prompts/05-phase-4-pipeline-orchestrator.md)
**Plan (approved):** [`docs/prompts/05-phase-4-pipeline-orchestrator-plan.md`](prompts/05-phase-4-pipeline-orchestrator-plan.md) — approved 2026-06-14T14:00:04Z
**Plan iterations:** 0 rejected revisions (approved first pass, with one amendment applied at the gate: `" and "` dropped from `cross_jurisdictional_markers`).
**Report:** [`docs/prompts/05-phase-4-pipeline-orchestrator-report.md`](prompts/05-phase-4-pipeline-orchestrator-report.md)

**Prompt summary.** Wire the four Phase 2/3 agents into a single end-to-end pipeline under one correlation_id; add a typed escalation policy engine driven by `policy.yaml` (OR semantics, hard + threshold rules); expose a synchronous trigger endpoint and an SSE progress-stream endpoint; verify the three locked demo scenarios; bump the version to 0.4.0.

**What changed:**

- `backend/app/escalation/policy.yaml` — new. The single authoritative rule set: version, watchlists, `cross_jurisdictional_markers` (`/`, `multi-jurisdiction`, `cross-border` — `" and "` deliberately excluded), four hard rules, three threshold rules.
- `backend/app/escalation/models.py` — new. `PipelineState`, `FiredRule`, `EscalationDecision`, `RuleType`. Placed in the escalation package so the orchestrator depends on it one-directionally (no circular import).
- `backend/app/escalation/policy.py` — new. `EscalationPolicy.load_from_yaml` (all I/O + schema validation at load; Literal-typed `PolicyDocument` rejects unknown rule names / fields / comparators) and `evaluate(state) -> EscalationDecision` (pure, OR semantics, fail-closed on any per-rule error). Exact `Decimal` comparisons throughout.
- `backend/app/escalation/__init__.py` — exports the engine and the shared types.
- `backend/app/orchestrator/models.py` — new. `PipelineResult`, `PipelineStatus`, `FailingAgent`, the six-member `PipelineEvent` union, `EventEmitter`. Re-exports the escalation types for one import surface.
- `backend/app/orchestrator/event_bus.py` — new. `PipelineEventBus`: one `asyncio.Queue` per correlation_id, buffered late-subscriber delivery, terminal-driven teardown after a grace period, thread-safe `publish_threadsafe`.
- `backend/app/orchestrator/pipeline.py` — new. `PipelineOrchestrator` wiring Doc-Parser → Validator → Adjuster → Guardrail → Escalation → Outcome. `run(claim_id, *, correlation_id=None, emit=None)` reads as named helper calls; the abort matrix (doc-parser/validator/adjuster throw → `aborted`; guardrail throw → `awaiting_human` fail-closed) is locked. Agent collaborators typed as Protocols. Writes three pipeline-level audit entries under `agent="orchestrator"`.
- `backend/app/orchestrator/__init__.py` — new. Public surface exports.
- `backend/app/api/pipeline.py` — new. `POST /api/pipeline/run/{claim_id}` (synchronous, optional `correlation_id`, blocking orchestrator offloaded via `run_in_threadpool`, thread→loop emit bridge) and `GET /api/pipeline/stream/{correlation_id}` (SSE via `EventSourceResponse`). Pre-flight unknown-claim → 404; malformed UUID → 422; pipeline outcomes (settled/awaiting_human/aborted) → 200.
- `backend/app/api/__init__.py` — mounts the pipeline router under `/api`.
- `backend/app/main.py` — added a `lifespan` that loads the policy (fail-fast) and builds the event bus at startup; the orchestrator is built lazily on first request (avoids the embedder cold-load on every startup). `create_app` stashes settings on `app.state`.
- `backend/settings.py` — new `PipelineSettings` (`event_grace_period_s`, `event_queue_maxsize`) with named-constant defaults; threaded into `Settings` as `pipeline`. `EscalationSettings` docstring notes its numeric fields are superseded by `policy.yaml`.
- `backend/settings.yaml.template` — new `pipeline:` block; escalation comment updated.
- `pyproject.toml` — version `0.3.0 → 0.4.0`; added `sse-starlette>=2.1`; added `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls = ["fastapi.Depends"]` so B008 does not flag the FastAPI DI pattern.
- `uv.lock` — regenerated (`sse-starlette` 3.4.4 added).
- `backend/tests/test_escalation_policy.py` — new, 20 tests.
- `backend/tests/test_pipeline_event_bus.py` — new, 8 tests.
- `backend/tests/test_pipeline_orchestrator.py` — new, 10 tests.
- `backend/tests/test_api_pipeline.py` — new, 6 tests.
- `backend/tests/test_pipeline_scenarios.py` — new, 3 integration + 1 gated.
- `CLAUDE.md` — Current Status updated to "Phase 4 complete; Phase 5 next".

**Tests:** 225 backend passing, 6 skipped (the Phase-1 embedding test + five `RUN_LLM_E2E_TESTS=1` gated tests, now including the Phase 4 pipeline real-call). Frontend 2 passing. Repository total **227 passing, 6 skipped, 0 failing**. Phase 4 adds **47 passing new tests + 1 gated**:

| Area | Tests |
|---|---|
| Escalation policy engine | 20 |
| Pipeline event bus | 8 |
| Pipeline orchestrator | 10 |
| Pipeline API | 6 |
| Integration scenarios | 3 (+1 gated) |

`uv run ruff check .` clean; `uv run mypy backend` clean (81 source files).

**Issues discovered:**

- **`cross_jurisdictional` has no native data signal.** Each claim carries a single `jurisdiction` string. Resolved by configured substring markers in `policy.yaml`; the architect dropped `" and "` at the approval gate (it false-positives on "Trinidad and Tobago" etc.). A regression test pins this.
- **Two sources of truth for the thresholds.** `EscalationSettings` (Phase 1) already held the numbers; `policy.yaml` is now authoritative and the settings fields are documented as superseded with identical values.
- **Eager orchestrator construction would cold-load the embedder on every startup.** Resolved by lazy first-request construction; the lifespan loads only the cheap policy + event bus.
- **B008 on FastAPI `Depends` defaults.** Resolved via ruff `extend-immutable-calls` rather than per-line `# noqa`.
- **Circular import risk** (orchestrator ↔ escalation). Resolved by placing the shared types in `escalation/models.py` and re-exporting from the orchestrator.
- **Anonymisation review.** `grep -i` for client/competitor names against the new files returned no matches.

**Next:** Phase 5 — Decoupling and replay.

---

## Phase 5 — Decoupling and Replay

**Date:** 2026-06-14

**Phase / Prompt:** Phase 5 — [`docs/prompts/06-phase-5-decoupling-and-replay.md`](prompts/06-phase-5-decoupling-and-replay.md)
**Plan (approved):** [`docs/prompts/06-phase-5-decoupling-and-replay-plan.md`](prompts/06-phase-5-decoupling-and-replay-plan.md) — approved 2026-06-14T16:14:04Z
**Plan iterations:** 0 rejected revisions (approved first pass, with two amendments applied at the gate: D1 → option (a) full Adjuster reasoning in audit; D6 → Validator audit reports the actual provider/model).
**Report:** [`docs/prompts/06-phase-5-decoupling-and-replay-report.md`](prompts/06-phase-5-decoupling-and-replay-report.md)

**Prompt summary.** Decouple submission from processing (`POST /api/claims` before any agent fires); write the claim-status lifecycle as the pipeline runs; add a configured replay variant; reconstruct any past run from the audit_log; expose runs/comparison APIs; build a functional (unpolished) frontend; bump the version to 0.5.0.

**What changed:**

- `backend/app/agents/adjuster.py` — audit payload gains full `reasoning` alongside `reasoning_excerpt` (amendment 1: the audit log is fully sufficient to reconstruct any past decision).
- `backend/app/agents/validator.py` — audit `llm_call.provider` now reports `self._provider.vendor` (amendment 2: a provider-swap variant is recorded truthfully, supporting the DORA Article 28 substitutability story); added an additive `user_template_name` constructor param.
- `backend/app/prompts/user/validator_strict.md` — new strict user template for `v2_strict_validator`.
- `backend/app/claims/{models,repository,__init__}.py` — new. `ClaimStatus`/`ClaimType`/`ScenarioTag`, `ClaimSubmission`, `ClaimRecord`; `ClaimsRepository` (insert/get/list/update_status), connection-scoped.
- `backend/app/runs/{models,repository,__init__}.py` — new. `RunSummary`/`RunComparison`/`DiffSummary`; `RunsRepository` reconstructs `PipelineResult` purely from the audit_log (`get_run`, `list_runs_for_claim`, `is_run_active`, `compare`, `compute_diff`).
- `backend/app/orchestrator/variants.yaml` + `variant_registry.py` + `variant_factory.py` — new. The variant registry (Literal-validated), `VariantSpec`, pure `resolve_validator_config`, and `build_variant_orchestrator`.
- `backend/app/orchestrator/pipeline.py` — `run(...)` gains `variant` (recorded in `pipeline_started` audit + SSE); injected `status_writer` (default DB writer); status writes at each agent completion and finalisation, non-fatal on failure.
- `backend/app/orchestrator/models.py` — `PipelineStartedEvent` gains additive `variant` field (default `"default"`).
- `backend/app/api/claims.py` + `runs.py` — new routers. `backend/app/api/pipeline.py` — `replay` endpoint, `run` gains `?variant=` and the active-run guard, orchestrator construction routed through an overridable factory.
- `backend/app/api/__init__.py`, `backend/app/main.py` — mount the new routers; lifespan loads the variant registry.
- `backend/settings.py` + `settings.yaml.template` — `PipelineSettings.variants_path`.
- `pyproject.toml` — version `0.4.0 → 0.5.0`.
- `frontend/src/` — new `api/{types,client}.ts`, `copy/tooltips.ts`, `fixtures/demoClaims.ts`, `hooks/{useClaims,useRunStream}.ts`, `components/{Tooltip,ClaimForm,ClaimList,ProgressStrip,CompareView}.tsx`, and a rewritten `App.tsx` (view toggle). No new frontend dependency (plain fetch + EventSource).
- `CLAUDE.md` — Current Status updated to "Phase 5 complete; Phase 6 next".

**Tests:** 277 backend passing, 6 skipped; 13 frontend passing. Repository total **290 passing, 6 skipped, 0 failing**. Phase 5 adds **52 backend + 11 frontend** new tests:

| Area | Tests |
|---|---|
| ClaimsRepository + submission | 13 |
| VariantRegistry + factory | 11 |
| RunsRepository reconstruction | 11 |
| Claims/runs/replay API | 12 |
| Orchestrator status + variant (added) | 4 |
| Integration (submit→run→replay→compare) | 1 |
| Frontend (Vitest) | 13 total (+11) |

`uv run ruff check .` clean; `uv run mypy backend` clean (95 source files); frontend `tsc -b --noEmit` and `eslint .` clean.

**Issues discovered:**

- **The prompt's frontend-dependency claim was wrong.** TanStack Query is not installed; Phase 5 uses plain `fetch` + hooks (no new dep), with TanStack Query deferred to Phase 6.
- **Stub agents don't write agent-step audit entries**, which runs reconstruction reads — so the runs and integration tests use *real* agents with mock providers.
- **ESLint's `react-hooks/set-state-in-effect`** flagged synchronous `setState` in the data hooks; resolved by moving every `setState` into the subscription / promise callbacks.
- **Omitted `narrative` from `ClaimRecord`** caught immediately by `extra="forbid"` at the first repository test.
- **Anonymisation review.** `grep -i` for client/competitor names across the new backend and frontend files returned no matches.

**Next:** Phase 6 — Frontend polish.

---

## Phase 6 — Frontend Polish (+ supporting backend endpoints)

**Date:** 2026-06-14

**Phase / Prompt:** Phase 6 — [`docs/prompts/07-phase-6-frontend-polish.md`](prompts/07-phase-6-frontend-polish.md)
**Plan (approved):** [`docs/prompts/07-phase-6-frontend-polish-plan.md`](prompts/07-phase-6-frontend-polish-plan.md) — approved 2026-06-14T21:16:53Z
**Plan iterations:** 0 rejected revisions (approved as written, with two report-only notes: make the chain-verify UI copy explicit it verifies the whole ledger; call out that the human panel assembles evidence from `/api/audit?correlation_id=`).
**Report:** [`docs/prompts/07-phase-6-frontend-polish-report.md`](prompts/07-phase-6-frontend-polish-report.md)

**Prompt summary.** Polish the functional Phase 5 UI into a routed React SPA with a design system, live pipeline visualisation, an audit viewer with chain verification, a human-review panel, and an agent test bench — plus the backend endpoints and the schema migration those surfaces require; bump to 0.6.0.

**What changed:**

- `backend/db/migrations/versions/0002_audit_human_agent.py` — new. Extends `audit_log` agent CHECK with `'human'` and `claims` status CHECK with `'aborted'` (forward-only; downgrade hazard documented).
- `backend/app/audit/event.py` — `AgentName` Literal gains `'human'`. `backend/app/claims/models.py` — `ClaimStatus` gains `'aborted'`.
- `backend/app/prompts/loader.py` — additive `raw(kind, name)` (unformatted prompt source).
- `backend/app/agents/_shared.py` — `ProbeMetadata` + `probe_metadata`.
- `backend/app/agents/{doc_parser,validator,adjuster,guardrail}.py` — additive non-audit `probe` methods (`parse`/`assess`/`estimate`/`check`); `evaluate` unchanged.
- `backend/app/api/audit.py`, `human.py`, `agents_test.py` — new routers (audit list + whole-ledger verify; human decision; 4 agent-test endpoints + prompt-source endpoint). `api/__init__.py` mounts them.
- `pyproject.toml` — version `0.5.0 → 0.6.0`.
- Backend tests: `test_migration_0002.py` (4), `test_prompt_loader.py` (+5), `test_agent_probe.py` (4), `test_audit_api.py` (5), `test_human_decision_api.py` (7), `test_agents_test_api.py` (10, 1 gated).
- `frontend/package.json` — added `@tanstack/react-query`, `react-router-dom`. `main.tsx` — QueryClient + BrowserRouter. `App.tsx` — router shell, six routes.
- `frontend/src/styles/tokens.ts` + `components/ui.tsx` (design system); `pages/` (Claims, ClaimDetail, RunDetail, Compare, Audit, Agents); `components/` (AgentCard, HumanReviewPanel, AgentTestPanel); `hooks/queries.ts` + rewired `useRunStream.ts`; `api/{client,types}.ts` extended; `test/utils.tsx`.
- Removed superseded Phase 5 components (ClaimList, ProgressStrip, CompareView) and their tests.
- `CLAUDE.md` — Current Status updated to "Phase 6 complete; Phase 7 next".

**Tests:** 311 backend passing, 7 skipped; 22 frontend passing. Repository total **333 passing, 7 skipped, 0 failing**. Phase 6 adds **34 backend** + **~18 frontend** new tests (Migration 4, PromptLoader.raw 5, Agent probe 4, Audit API 5, Human decision 7, Agent test API 9+1 gated; frontend 22 total). `ruff` clean; `mypy backend` clean (104 files); frontend `tsc` + `eslint` clean.

**Issues discovered:**

- **`aborted` was not a valid claim status.** The prompt assumed human-rejection → `aborted` would work, but the `claims.status` CHECK had only the seven lifecycle values. Migration 0002 also extends `claims.status` with `aborted`; `ClaimStatus` gains it.
- **Chain verification is whole-ledger, not per-run** — the verify endpoint runs the full-ledger verifier; the UI copy says so (approval note 1).
- **The agent test bench needed a no-audit path** — resolved by additive `probe` methods (existing agent tests stay green).
- **Anonymisation review.** No client/competitor names in the new files.

**Next:** Phase 7 — Demo polish and documentation.

---

## Phase 7 — Demo Polish and Documentation

**Date:** 2026-06-15

**Phase / Prompt:** Phase 7 — [`docs/prompts/08-phase-7-demo-polish-and-documentation.md`](prompts/08-phase-7-demo-polish-and-documentation.md)
**Plan (approved):** [`docs/prompts/08-phase-7-demo-polish-and-documentation-plan.md`](prompts/08-phase-7-demo-polish-and-documentation-plan.md) — approved 2026-06-15T10:30:53Z
**Plan iterations:** 0 rejected revisions (approved as written; architect performs a one-time manual grep of the real client name before push, with the candidate-list test as the standing guard).
**Report:** [`docs/prompts/08-phase-7-demo-polish-and-documentation-report.md`](prompts/08-phase-7-demo-polish-and-documentation-report.md)

**Prompt summary.** Expand the README to its final demo-ready form; ship the change-governance, DORA register, design-decisions, walkthrough, verification docs and the Azure pipeline reference; close the scenario-3 live-reproducibility gap with a deterministic Adjuster demo fixture; land the audit-payload addendum in CLAUDE.md; run a final anonymisation pass; bump to 0.7.0.

**What changed:**

- `backend/data/demo_fixtures/guardrail_adjuster.json` — new. Deterministic Adjuster output with a planted "Endorsement Coastal Surge Rider" the policy lacks.
- `backend/app/agents/adjuster.py` — one fixture branch in `evaluate` keyed on the claim's `scenario_tag` (`_load_demo_fixture` / `_read_scenario_tag` / `_load_fixture_output`, fail-closed), additive `demo_fixture: bool` in the audit payload with a truthful `llm_call` block.
- `backend/data/seed_claims.py` — comment noting the `guardrail_escalation` tag drives the fixture (no schema change).
- `backend/tests/test_demo_fixture.py` — new (5): fixture schema; loader fail-closed guards (missing/non-JSON/schema); end-to-end deterministic guardrail escalation asserting the Adjuster LLM is never called and the audit records `demo_fixture: true`.
- `backend/tests/test_anonymisation.py` — new (10): parameterised grep over shipping artefacts for candidate client-name patterns; expected zero matches.
- `CLAUDE.md` — "Locked interface extensions since Phase 4" subsection; Current Status → "Phase 7 complete; clone-and-run verification next".
- `README.md` — expanded to the locked nine-section structure (elevator pitch, headline diagram inline, what-this-demonstrates, one-command setup, live demo + three scenarios, four diagrams in `<details>`, design decisions, production architecture + dev→prod table, reproducible build, governance/DORA links).
- `docs/change-governance.md`, `docs/dora-third-party-register.md`, `docs/design-decisions.md`, `docs/walkthrough.md`, `docs/verification/phase-7/scenarios.md` — new.
- `infra/azure-devops-pipeline.yml` — new (was an empty `.gitkeep`): build → test → security scan → CAB gate → migration → staging deploy → smoke → production deploy → post-deploy verification, each stage naming the production equivalent.
- `scripts/verify-demo-scenarios.py` — new: stdlib runner that submits + runs the three scenarios against a deployed backend and asserts outcomes.
- `pyproject.toml` — version `0.6.0 → 0.7.0`.

**Tests:** 326 backend passing, 7 skipped; 22 frontend passing. Repository total **348 passing, 7 skipped, 0 failing**. Phase 7 adds **15 backend** tests. **Scenario-3 fixture test:** `test_guardrail_escalation_reproduces_deterministically` — asserts `awaiting_human` + `guardrail_failed`, the Adjuster LLM is never called (`MockProvider.calls == []`), and the audit `demo_fixture: true`. `ruff` clean; `mypy backend` clean (106 files); frontend tsc/eslint/vitest unchanged and green.

**Anonymisation pass:** the parameterised test greps the shipping artefacts (backend + frontend code, README, CLAUDE.md, user-facing `docs/`, `infra/`, `scripts/`, `diagrams/`) for candidate regulated/specialty-insurer identifiers — **zero matches**. The build meta-record (`docs/prompts/`, `docs/build-log.md`) is excluded because it legitimately documents the grep methodology; `backend/app/prompts/` (deliverables) is scanned. The architect performs a one-time manual grep of the real client name before push.

**Verification pass:** scenarios 1 and 2 reproduce live via the real agents; scenario 3 is now deterministic via the demo fixture and verified end-to-end in test. The architect runs `scripts/verify-demo-scenarios.py` against the deployed backend and fills `docs/verification/phase-7/scenarios.md`.

**Issues discovered:**

- **`infra/azure-devops-pipeline.yml` did not exist** (the prompt called it a stub; `infra/` held only `.gitkeep`) — created fresh.
- **The citation regex requires the endorsement name to start with a letter**, so "Endorsement 7" would not match; the fixture uses "Endorsement Coastal Surge Rider" for a deterministic regex catch.
- **`AdjusterOutput` is `extra="forbid"`**, so the fixture's `_comment` key is stripped (JSON-comment convention) before validation by `_load_fixture_output`.

**Next:** Clone-and-run verification.

---

## Phase 8 — Demo Polish Fixes from Rehearsal Discoveries

**Date:** 2026-06-15

**Phase / Prompt:** Phase 8 — [`docs/prompts/09-phase-8-demo-polish-fixes.md`](prompts/09-phase-8-demo-polish-fixes.md)
**Plan (approved):** [`docs/prompts/09-phase-8-demo-polish-fixes-plan.md`](prompts/09-phase-8-demo-polish-fixes-plan.md) — approved 2026-06-15T13:45:28Z
**Plan iterations:** 0 rejected revisions (approved as written; the architect asked that the D3, D6, and D1 reasoning be carried into the report).
**Report:** [`docs/prompts/09-phase-8-demo-polish-fixes-report.md`](prompts/09-phase-8-demo-polish-fixes-report.md)

**Prompt summary.** A focused six-fix pack from the Phase-7 demo rehearsal: (1) restore live pipeline visualisation (the run page must mount and start watching *before* the 27s run completes); (2) handle the in-flight "no run data yet" 404 gracefully; (3) give each AgentCard a "running" state with an expected duration, a description, and an animated progress bar; (4) embed dollar figures in the three demo narratives so Doc-Parser extracts `claimed_amount`; (5) tune the Guardrail prompt so the Adjuster's market vocabulary is not mistaken for a hallucinated policy citation; (6) surface POST failures via an `ErrorBanner`; (7, bonus) enumerate the audit-payload addendum in the README. Bump to 0.8.0.

**What changed:**

- `frontend/src/pages/ClaimsPage.tsx` — **Fix #1 + #6.** `trigger` is now synchronous: it mints a correlation id, `navigate`s to the run page *immediately*, then fires the run/replay POST fire-and-forget. The POST's `.catch` records the failure under a `['runError', cid]` query-cache key. Dropped the per-claim `busy` state (navigate-immediately unmounts the page, so a `setState` on the unmounted component would only warn). Process always enabled; Re-process gated on `REPLAYABLE`.
- `frontend/src/pages/RunDetailPage.tsx` — **Fix #2 + #6.** Tolerates the in-flight 404 (`run.data` absent) by deriving status from the SSE stream; an `awaiting-hint` shows until the first event. Reads the `['runError', cid]` cache key reactively (`useQuery({ enabled: false })`) and renders an `ErrorBanner` for both a failed POST and a `pipeline_aborted` SSE event.
- `frontend/src/components/AgentCard.tsx` — **Fix #3.** New "running" block: per-agent expected duration (`AGENT_EXPECTED_MS`), a description from `agent-descriptions`, and a `role="progressbar"` driven by a `useProgress` hook (a `setInterval` percentage, not a CSS transition — jsdom can observe the JS value, vitest fake timers can advance it).
- `frontend/src/components/ui.tsx` — **Fix #6.** New `ErrorBanner` (`role="alert"`).
- `frontend/src/copy/agent-descriptions.ts` — new. Per-agent "what's happening" copy.
- `backend/data/seed_claims.py` — **Fix #4.** The three demo narratives now state their figures in the text ($85,000 / $850,000 / $1,400,000) so Doc-Parser extracts `claimed_amount` instead of aborting on `0.00`. `reported_amount` Decimals unchanged.
- `backend/app/prompts/system/guardrail.md` — **Fix #5.** Added a paragraph teaching the Guardrail that market-data vocabulary ("market band", "within range", "lookup table") is settlement framing, not a policy citation, and must not be flagged; only absent policy clauses/endorsements/sub-limits count.
- `README.md` — **Fix #7.** The "audit log is the trusted record" design-decision bullet now enumerates the six additive audit-payload extensions, with a note that all are additive and the locked list lives in CLAUDE.md.
- `pyproject.toml` — version `0.7.0 → 0.8.0`.

**Tests:** 330 backend passing, 7 skipped; 30 frontend passing. Phase 8 adds **4 backend** tests (`test_demo_narrative_contains_dollar_figure` ×3 in `test_seed_claims.py`; `test_market_vocabulary_is_not_flagged` in `test_guardrail.py`) and **8 frontend** tests (new `ClaimsPage.test.tsx` ×2, new `RunDetailPage.test.tsx` ×3, `AgentCard` running-state ×3). `ruff` clean; `mypy backend` clean (106 files); frontend tsc/eslint clean.

**Design decisions worth recording (per approval):**

- **D3 — JS-driven progress, not CSS.** A CSS-interpolated width is invisible to jsdom; the `setInterval` percentage is both observable in jsdom and advanceable with vitest fake timers, so "the bar advances over time" is a real assertion rather than a visual hope.
- **D6 — two independent error signals.** A failed *start* (POST rejects) is recorded in the query cache under `['runError', cid]`; a failed *run* (pipeline aborts mid-flight) arrives as a `pipeline_aborted` SSE event. `EventSource.onerror` is deliberately **not** used as an error signal because it also fires on a normal stream close, which would surface spurious banners on every completed run.
- **D1 — drop the `busy` state.** Navigating immediately unmounts `ClaimsPage`, so the old "grey the button while awaiting" state had no component left to live on; keeping it would only produce a setState-on-unmounted warning.

**Issues discovered:** none beyond the rehearsal findings the pack was scoped to fix. Root cause of #1: Phase 6 had collapsed the Phase-5 "open the stream, then trigger" ordering into `await runPipeline(...)` then `navigate(...)`, serialising the whole 27s run before the watching page mounted; the event bus's late-subscriber buffering makes the navigate-first ordering safe.

**Next:** Clone-and-run verification.

---
