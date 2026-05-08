# Plan 02 — Phase 1: Data Layer and Settings Infrastructure

## Goal

Land the persistent foundation the agents will sit on top of in Phases 2–4: a versioned database schema (`claims`, `audit_log`, `policy_chunks`), a settings architecture extended with named sub-models, a cryptographically chained audit vault written defensively, a 2–3 page generic commercial-property policy excerpt indexed via `bge-small-en-v1.5`, and a synthetic claim generator covering the three locked demo scenarios. Plus the documentation fix-ups (architecture stack reference now reflects Neon, not Render Postgres) and a Postgres+pgvector service container in CI so the new tests run against a real database.

No agents, no LLM calls, no orchestrator, no UI changes. Phase 1 is purely the data foundation.

## Files and directories I will create or modify

### Database / migrations (new top-level area)

- `backend/db/__init__.py` — package marker.
- `backend/db/connection.py` — single source of truth for the Postgres connection. Returns a `psycopg.Connection` (or async `AsyncConnection`) configured from `Settings`. Registers the `pgvector.psycopg` type adapter at module import so `vector` columns round-trip as Python `list[float]`/`numpy.ndarray` without per-call boilerplate. Synchronous psycopg is the recommended default for Phase 1 — Phase 2's LLM calls are I/O-bound but they don't gate on DB latency, and a sync connection keeps the audit-chain code straightforward and testable. (Optional enhancement: switch to `psycopg.AsyncConnection` later — flagged below.)
- `backend/db/migrations/` — Alembic migration tree. `env.py` reads `DATABASE_URL` from `Settings`, never from a hardcoded URL. Migration files are pure SQL via `op.execute()` — no SQLAlchemy ORM models declared. Reasoning under "Migration tooling choice" below.
- `backend/db/migrations/versions/0001_initial_schema.py` — creates `claims`, `audit_log`, `policy_chunks`, all indexes, and the `vector` extension (`CREATE EXTENSION IF NOT EXISTS vector`). Single migration for Phase 1; subsequent phases get their own version files.
- `backend/db/migrations/script.py.mako` — Alembic template, default content.
- `backend/alembic.ini` — Alembic config. `script_location = backend/db/migrations`. No connection string baked in; `env.py` pulls it from `Settings`.

### Audit vault

- `backend/app/audit/__init__.py` — re-exports `AuditEvent`, `AuditWriter`, `verify_chain`.
- `backend/app/audit/event.py` — Pydantic v2 `AuditEvent` model: `correlation_id: UUID`, `claim_id: UUID`, `agent: Literal[...]`, `step: str`, `payload: dict[str, Any]`, `created_at: datetime` (UTC). The `agent` literal is the locked enumeration of agent names plus `'system'` (for orchestrator-level events). Validators reject empty `step`, naive datetimes, and non-JSON-serialisable payloads.
- `backend/app/audit/canonical.py` — `canonicalise(event: AuditEvent) -> bytes`. Produces a deterministic UTF-8 JSON encoding (sorted keys, ISO 8601 UTC timestamps, no whitespace variation). Pure function. The canonical form is the contract: the same logical event always produces the same bytes, so the same row hash, so the same chain hash. Documented inline as an interface — changing it after Phase 1 invalidates every existing audit row.
- `backend/app/audit/chain.py` — `compute_row_hash(canonical: bytes) -> str` (SHA-256 hex), `compute_chain_hash(row_hash: str, prev_chain_hash: str) -> str` (SHA-256 hex of `row_hash + prev_chain_hash`). Two named constants: `GENESIS_CHAIN_HASH = "0" * 64` (the prev_chain_hash used when the table is empty), `HASH_HEX_LENGTH = 64`.
- `backend/app/audit/writer.py` — `AuditWriter.append(event: AuditEvent) -> AuditRow`. Defensive order:
  1. **Sanitise** — coerce `event` through Pydantic (already typed) and resolve `created_at` to UTC.
  2. **Validate** — `claim_id` exists in `claims`; agent is in the locked enum (already enforced by Pydantic but re-asserted at the DB boundary so a hand-built dict can't sneak past); payload is JSON-serialisable.
  3. **Abort** — `ValueError` with diagnostic context on any failure (truncate payloads to 500 chars in the message; full payload remains in memory for the caller).
  4. **Execute** — open a transaction, take an advisory lock keyed to the audit table (so concurrent writers can't read the same `prev_chain_hash`), `SELECT chain_hash FROM audit_log ORDER BY audit_id DESC LIMIT 1 FOR UPDATE`, compute new hashes, INSERT, commit.
- `backend/app/audit/verify.py` — `verify_chain(conn) -> ChainVerification`. Walks the table in `audit_id` order, recomputes each row's `row_hash` and `chain_hash`, returns a typed result with `ok: bool`, `rows_checked: int`, and `first_break: AuditBreak | None`. Hand-tunable to "stop on first break" or "report all breaks" — Phase 1 ships the stop-on-first-break version; full-walk variant flagged as an optional enhancement.

### Settings extension

- `backend/settings.py` — extended in place. Five new Pydantic sub-models hung off `Settings`:
  - `DatabaseSettings`: `url: SecretStr` (validation alias `DATABASE_URL`, no default — instantiation fails fast if absent), `min_pool_size: int = 1`, `max_pool_size: int = 5`, `statement_timeout_ms: int = 30_000`, `echo_sql: bool = False`. Validator rejects URLs without `postgresql://` or `postgres://` scheme.
  - `LLMSettings`: nested `anthropic` and `mistral` blocks. `anthropic.api_key: SecretStr | None` (alias `ANTHROPIC_API_KEY`, optional in Phase 1 because no LLM calls happen yet), `anthropic.orchestrator_model: str = "claude-sonnet-4-6"`, `anthropic.doc_parser_model: str = "claude-haiku-4-5-20251001"`, `anthropic.guardrail_model: str = "claude-haiku-4-5-20251001"`. `mistral.api_key: SecretStr | None` (alias `MISTRAL_API_KEY`), `mistral.validator_model: str = "mistral-large-latest"`, `mistral.adjuster_model: str = "mistral-large-latest"`. No per-call params (temperature, max_tokens, etc.) — those land in Phase 2 when the Gateway needs them.
  - `EmbeddingSettings`: `model_name: str = "BAAI/bge-small-en-v1.5"`, `dimension: int = 384` (validator pins `384` because the model is locked; changing it requires explicit code change), `normalise_embeddings: bool = True`, `batch_size: int = 32`.
  - `LangfuseSettings`: `enabled: bool = False` (Phase 1 doesn't emit traces yet), `public_key: SecretStr | None`, `secret_key: SecretStr | None`, `host: str = "https://cloud.langfuse.com"`. Validator: if `enabled is True`, both keys must be present.
  - `EscalationSettings`: matches the `CLAUDE.md` Architectural Decisions block exactly. `auto_approve_ceiling: Decimal = Decimal("250000")`, `validator_confidence_floor: float = 0.65`, `adjuster_confidence_floor: float = 0.75`, `hard_rules: list[Literal["guardrail_failed", "claim_type_watchlist", "claimant_watchlist", "cross_jurisdictional"]] = [all four by default]`, `policy_path: Path = Path("backend/app/escalation/policy.yaml")`. The actual `policy.yaml` file is created by Phase 4; Phase 1 just declares the field and validates the default path's parent directory exists in the repo (so Phase 4 can drop the file in without further plumbing). The `Decimal` type is used for monetary values to avoid float drift.
- `backend/settings.yaml.template` — extended with matching `database`, `llm`, `embedding`, `langfuse`, `escalation` blocks, every field commented. Secret fields are commented as "loaded from env — do not put values here". Maintains the existing top-level keys.

### Sample commercial property policy excerpt

- `backend/data/sample_policy.txt` — 2–3 pages of generic commercial property wording, no insurer name, no client name. Plain text with `# Section` headings to give the chunker something natural to split on. Sections, in this order:
  1. **General Conditions** — premium payment, policy period, cancellation, mid-term changes, notice requirements.
  2. **Definitions** — covered cause of loss, period of restoration, actual cash value, replacement cost, named insured, deductible.
  3. **Named Perils Covered** — fire, lightning, windstorm, hail, explosion, smoke, vandalism, sprinkler leakage, water damage from plumbing systems, civil commotion. Each with one-paragraph description.
  4. **Exclusions** — flood (with explicit pointer to a separate flood endorsement that is *not* attached, so a hallucinated reference to one is detectable), earthquake, war and terrorism, wear and tear, gradual deterioration, dishonesty by the named insured.
  5. **Sub-Limits** — debris removal (25% of direct damage), ordinance or law (10%), valuable papers ($25,000), pollutant cleanup ($10,000).
  6. **Business Interruption** — 72-hour waiting period, 80% coinsurance, actual loss sustained valuation, period-of-restoration calculation method.
  7. **Duties After Loss** — prompt notice, mitigation, inventory of damaged property, examination under oath, suit limitation (two years).

The wording is deliberately realistic but generic — recognisable as commercial property language to a knowledgeable reader, no insurer-specific phrasing. Anonymisation review applies.

### Synthetic claim generator

- `backend/data/seed_claims.py` — produces 9 commercial property claims. Run as `uv run python -m backend.data.seed_claims` (idempotent; truncates and re-seeds). Each claim is a fully populated row matching the `claims` table contract.
  - 3 scripted scenarios (one each), tagged via the `scenario_tag` column:
    - `auto_approve` — $85,000 commercial water damage, narrative cleanly within named-perils language, no exclusion overlap, well below the $250k ceiling. Demonstrates the auto-approve path.
    - `threshold_escalation` — $850,000 fire loss at a manufacturing facility, narrative cleanly within coverage but the settlement breaches the $250k ceiling.
    - `guardrail_escalation` — $1.4M loss with a complex narrative ripe for the Adjuster to hallucinate an endorsement reference. The Phase 1 row is just the claim itself; the hallucination is injected by the Adjuster in Phase 4 — but the claim is *shaped* such that an Adjuster prompted to settle would reach for citations, increasing the chance of a hallucinated endorsement that the Guardrail catches.
  - 6 untagged background claims spanning sprinkler leakage, vandalism, theft of fixtures, partial smoke damage, hail damage to roof, windstorm. Realistic but unremarkable. Diversity to make retrieval search results meaningful.
  - Every claim has: `claim_number`, `policy_number`, `claimant_name` (synthetic, no real names), `loss_date`, `reported_date`, `jurisdiction` (one of "Bermuda", "United Kingdom", "United States — New York", "Ireland"), `narrative` (multi-sentence), `claim_type`, `reported_amount`, `status = 'received'`, optional `scenario_tag`. Reproducible across runs (seeded RNG).

### Indexing script

- `backend/data/index_policy.py` — run as `uv run python -m backend.data.index_policy`. Reads `backend/data/sample_policy.txt`, splits by `# Section` heading boundaries, then within each section splits paragraphs into chunks targeting ~200–300 tokens each (using the embedding model's tokenizer for accurate token counts, not whitespace approximation). Embeds in batches of `EmbeddingSettings.batch_size` (32 by default) with cosine-normalised vectors. Writes to `policy_chunks` with `embedding_model` set to the model name from settings. Idempotent: deletes rows for the same `source_path` before re-inserting (single transaction, so a partial failure leaves the previous index intact).
- The chunker is a small standalone function (`chunk_markdown_sections`) that's unit-testable without a model loaded — important because `sentence-transformers` model load is slow.

### Tests

All under `backend/tests/`. Existing files unchanged. New files:

- `backend/tests/conftest.py` — extended with two new fixtures:
  - `db_url(monkeypatch)` — reads `DATABASE_URL` from env. Tests that need a DB skip with a clear message if it's unset locally; CI sets it via the service container.
  - `db_conn(db_url)` — opens a psycopg connection, yields it, rolls back at the end. Each test starts in a clean state.
  - `migrated_db(db_conn)` — applies Alembic migrations to a fresh schema (drops + recreates a test schema named `agentic_claims_test_<pid>`), yields, drops at end. Slow per session, fast per test.
- `backend/tests/test_settings_phase1.py` — sub-model defaults; env var override for `DATABASE_URL`; validator rejects bad URL scheme; embedding dimension lock; Langfuse "enabled but missing keys" guard; Escalation defaults match the locked decisions verbatim. ~10 tests.
- `backend/tests/test_audit_canonical.py` — same logical event always produces the same bytes; key order doesn't affect output; timezone-aware vs naive datetime guard; non-JSON-serialisable payload guard. ~5 tests.
- `backend/tests/test_audit_chain.py` — `compute_row_hash` produces 64-char hex; `compute_chain_hash` chains two known inputs to a known output (golden value); genesis constant is 64 zeros; SHA-256 length invariant. ~4 tests.
- `backend/tests/test_audit_writer.py` — DB-backed. Append a single event → row exists with row_hash, prev=`GENESIS`, chain=expected. Append three events → chain links correctly. Append with unknown `claim_id` → `ValueError` mentioning the missing UUID. Append with empty `step` → `ValueError`. Append with non-UTC `created_at` → `ValueError`. Concurrent writes serialised by advisory lock — verify two threads writing don't produce a chain break (light test, not a stress test). ~7 tests.
- `backend/tests/test_audit_verify.py` — DB-backed. Empty table verifies as ok with `rows_checked=0`. Three appended events verify ok. Tamper one row's `payload` directly via SQL → verify reports a break at that row's `audit_id`. Tamper the `chain_hash` of a middle row → verify reports a break at the *next* row (because the next row's prev pointer no longer matches). ~4 tests.
- `backend/tests/test_seed_claims.py` — 9 claims generated; exactly one row per scripted scenario tag; jurisdictions cover the four locked options; reproducibility (two runs with same seed produce identical rows); claim numbers unique; reported_amount strictly positive. ~6 tests.
- `backend/tests/test_index_policy.py` — chunker only (no embedding model) — chunks have token counts within the configured range, section boundaries respected, no chunk crosses a heading. Then a single end-to-end test (skipped unless `RUN_EMBEDDING_TESTS=1` is set) that loads the model, indexes, asserts row count and embedding dimension. ~5 tests + 1 conditional.
- `backend/tests/test_schema.py` — DB-backed. Migration applies cleanly to a fresh schema, all three tables exist with the expected columns, all expected indexes exist, FK from `audit_log.claim_id` to `claims.claim_id` exists, `vector` extension is enabled. ~5 tests.

Per `~/.claude/CLAUDE.md`: every guard clause has a triggering test asserting the error message content (not just that an exception was raised).

### CI changes

- `.github/workflows/ci.yml` — backend job extended:
  - Add a `services.postgres` block running `pgvector/pgvector:pg16` (image with the extension pre-built — keeps CI under a minute). Health check via `pg_isready`. Random external port; `DATABASE_URL` exported into the job env.
  - Add a step before `pytest` that runs `uv run alembic upgrade head` so the schema exists when the DB-backed tests fire.
  - Add `pip-audit` (or `uv-secure`) and `npm audit --audit-level=high` as additive steps. **Flagged optional** in line with the Phase 0 report's recommendation; if you want them deferred to Phase 7 polish, say so and I'll cut them. Recommended to fold in now since the dependency footprint grows in Phase 1.

### Local development changes

- `.env.example` (new, root) — documents `DATABASE_URL` (required), `ANTHROPIC_API_KEY` and `MISTRAL_API_KEY` (Phase 2; documented now as placeholders so the file is stable). `.gitignore` already excludes `.env` and `.env.*` (with a `.env.example` allowlist exception).
- `README.md` — Local development section extended:
  - Add a step "Configure environment variables" that copies `.env.example` to `.env` and sets `DATABASE_URL`. Two patterns documented: (a) local Postgres via `setup-dev-db.sh` then `DATABASE_URL=postgresql://localhost/agentic_claims_dev`; (b) optional Neon-from-local — point `DATABASE_URL` at a Neon dev branch if the developer prefers (no Docker, no local Postgres).
  - Add a "Run migrations" step: `uv run alembic upgrade head`.
  - Add a "Seed and index" step: `uv run python -m backend.data.seed_claims && uv run python -m backend.data.index_policy`.

### Documentation fix-up (preamble step inside the same Phase 1 commit)

- `docs/architecture-stack-reference.md` — replace every reference to "PostgreSQL on Render" / "Render-managed Postgres" with "Neon (managed Postgres) — `eu-central-1` / Frankfurt; pgvector 0.8.0 enabled". Three locations in the table, two locations in the prose. Production-side wording (Azure SQL Managed Instance + Ledger Tables) is unchanged.
- `CLAUDE.md` — the "Tech Stack > Data" block currently says "Production runs Render's managed Postgres". Adjust to read "Production-deployed prototype runs Neon (managed Postgres) with pgvector enabled". Change limited to the data tier description; the rest of the file is untouched until the Step 6 status update below.

### Externalised prompts directory placeholders

The prompt notes that the prompts directory should exist ready for Phase 2. I'll create:

- `backend/app/prompts/__init__.py`
- `backend/app/prompts/system/.gitkeep`
- `backend/app/prompts/user/.gitkeep`

Empty placeholders. No prompts written; Phase 2 owns that.

## Migration tooling choice — recommendation: Alembic with raw SQL

**Recommend Alembic.** Reasoning:

- Provides version tracking out of the box (`alembic_version` table). Plain SQL files would force a homegrown runner that reads a directory and tracks state — small but new code surface, easy to get wrong.
- Re-runnable against a fresh DB (`alembic upgrade head`) and replayable on Neon and CI without modification.
- Standard tool, expected by anyone reviewing this repo.
- We don't pay the SQLAlchemy ORM cost: migration files use `op.execute()` with raw SQL strings, no ORM models declared. The runtime app uses `psycopg` directly. Alembic just sequences the SQL.

The alternative — a `migrations/` folder of numbered `.sql` files with a small Python runner — was considered. It's defensible for a 3-table schema, but the moment the prototype acquires a fourth migration the homegrown runner has to track state, idempotency, and concurrency. Alembic already solves that. Cost: one additional dependency (`alembic`) and one transitive (`sqlalchemy`).

If you'd rather have raw SQL files and a hand-rolled runner, I'll switch — flag the preference at approval time.

## Audit chain implementation

**Formula.** `chain_hash = sha256(row_hash || prev_chain_hash)` where `row_hash = sha256(canonical_row_content)` and `canonical_row_content` is the deterministic UTF-8 JSON encoding of the typed `AuditEvent`. Both hashes are 64-char lowercase hex. Genesis `prev_chain_hash` is `"0" * 64`.

This matches `BUILD-PLAN.md`'s wording ("SHA-256 of `(row_content + previous_chain_hash)`") via the small clarification that what's hashed second is the row's hash, not the raw row content. The clarification matters because storing `row_hash` in the table is what makes verification cheap (and what makes the canonicalisation function self-checkable).

**Canonicalisation strategy.** `canonical_row_content` is `json.dumps(event_dict, sort_keys=True, separators=(",", ":"), default=...)`.encode("utf-8") where:

- `event_dict` is built from the `AuditEvent` Pydantic model via `.model_dump(mode="json")` (which already produces JSON-safe types: UUIDs as strings, datetimes as ISO 8601, etc.).
- A custom `default=` handler refuses `Decimal` (caller must convert to string explicitly so rounding is intentional), `set` (order-undefined), and `bytes` (caller must base64-encode explicitly). Forces the caller to make canonicalisation choices visible.
- Datetimes are normalised to UTC before serialisation (rejected if naive).

**Defensive order in `AuditWriter.append`** — sanitise (Pydantic), validate (DB-side checks: claim exists, agent enum, payload JSON-serialisable), abort (raise with diagnostic context), execute (transaction with advisory lock + SELECT FOR UPDATE on the latest row). Every guard clause has a comment explaining *why* it aborts, not just *what* it checks.

## Database schema (locked at end of Phase 1)

### `claims`

| Column | Type | Constraints / notes |
|---|---|---|
| `claim_id` | UUID | PK, default `gen_random_uuid()` |
| `claim_number` | TEXT | UNIQUE NOT NULL — e.g. `CLM-2026-0001` |
| `line_of_business` | TEXT | NOT NULL DEFAULT `'Commercial Property'` |
| `claimant_name` | TEXT | NOT NULL |
| `policy_number` | TEXT | NOT NULL |
| `loss_date` | DATE | NOT NULL |
| `reported_date` | DATE | NOT NULL |
| `jurisdiction` | TEXT | NOT NULL |
| `narrative` | TEXT | NOT NULL |
| `claim_type` | TEXT | NOT NULL — water_damage, fire, theft, etc. |
| `reported_amount` | NUMERIC(14,2) | NOT NULL CHECK > 0 |
| `status` | TEXT | NOT NULL DEFAULT `'received'` CHECK IN (`received`, `extracted`, `coverage_verified`, `estimated`, `guardrail_checked`, `settled`, `awaiting_human`) |
| `scenario_tag` | TEXT | NULL — `auto_approve` / `threshold_escalation` / `guardrail_escalation` / NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` |

Indexes: PK on `claim_id`, UNIQUE on `claim_number`, BTREE on `status`, BTREE on `scenario_tag`.

### `audit_log`

| Column | Type | Constraints / notes |
|---|---|---|
| `audit_id` | BIGSERIAL | PK |
| `correlation_id` | UUID | NOT NULL |
| `claim_id` | UUID | NOT NULL REFERENCES `claims(claim_id)` |
| `agent` | TEXT | NOT NULL CHECK IN (`system`, `doc_parser`, `validator`, `adjuster`, `guardrail`, `orchestrator`) |
| `step` | TEXT | NOT NULL CHECK length > 0 |
| `payload` | JSONB | NOT NULL |
| `row_hash` | CHAR(64) | NOT NULL |
| `prev_chain_hash` | CHAR(64) | NOT NULL |
| `chain_hash` | CHAR(64) | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` |

Indexes: PK on `audit_id`, BTREE on `correlation_id`, BTREE on `claim_id`, BTREE on `created_at`. No UNIQUE on `chain_hash` (collisions infinitesimally unlikely but the contract should still permit them).

### `policy_chunks`

| Column | Type | Constraints / notes |
|---|---|---|
| `chunk_id` | UUID | PK, default `gen_random_uuid()` |
| `source_path` | TEXT | NOT NULL — relative path from repo root |
| `section` | TEXT | NOT NULL |
| `chunk_index` | INT | NOT NULL CHECK >= 0 |
| `content` | TEXT | NOT NULL |
| `token_count` | INT | NOT NULL CHECK > 0 |
| `embedding` | VECTOR(384) | NOT NULL |
| `embedding_model` | TEXT | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` |

Indexes: PK on `chunk_id`, BTREE on `source_path`, HNSW on `embedding` with `vector_cosine_ops` (cosine similarity, since `bge-small-en-v1.5` is normalised). HNSW chosen over IVFFlat — IVFFlat needs `lists` tuned to the data size and a training pass; HNSW works out of the box for the prototype's tens-of-rows scale and gives better recall.

UNIQUE constraint: `(source_path, chunk_index)` — guarantees re-indexing produces a clean, deterministic chunk set.

## Settings sub-models (locked at end of Phase 1)

```
Settings
├── (existing flat fields: app_name, environment, api_host, api_port, log_level, cors_allowed_origins)
├── database: DatabaseSettings
│     url: SecretStr (alias DATABASE_URL, required)
│     min_pool_size: int = 1
│     max_pool_size: int = 5
│     statement_timeout_ms: int = 30_000
│     echo_sql: bool = False
├── llm: LLMSettings
│     anthropic.api_key: SecretStr | None (alias ANTHROPIC_API_KEY)
│     anthropic.orchestrator_model: str
│     anthropic.doc_parser_model: str
│     anthropic.guardrail_model: str
│     mistral.api_key: SecretStr | None (alias MISTRAL_API_KEY)
│     mistral.validator_model: str
│     mistral.adjuster_model: str
├── embedding: EmbeddingSettings
│     model_name: str = "BAAI/bge-small-en-v1.5"
│     dimension: int = 384  (validator: must be 384)
│     normalise_embeddings: bool = True
│     batch_size: int = 32
├── langfuse: LangfuseSettings
│     enabled: bool = False
│     public_key: SecretStr | None
│     secret_key: SecretStr | None
│     host: str = "https://cloud.langfuse.com"
└── escalation: EscalationSettings
      auto_approve_ceiling: Decimal = Decimal("250000")
      validator_confidence_floor: float = 0.65
      adjuster_confidence_floor: float = 0.75
      hard_rules: list[Literal[...]]  (defaults to all four)
      policy_path: Path = Path("backend/app/escalation/policy.yaml")
```

`pydantic-settings`' `env_nested_delimiter="__"` is already configured, so `LLM__ANTHROPIC__API_KEY` works as an env override. The named aliases (`DATABASE_URL`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`) take precedence over the nested form, which keeps the deployment configuration ergonomic.

## Sample policy excerpt — anonymisation note

The text is generic commercial-property wording. No insurer name. No client name. No real-world named insured. No named adjusting firm. Section headings are standard. I'll write it from scratch, run the "no client name" grep before commit, and surface anything in the wording that could read as proprietary.

## Indexing script details

- **Chunker.** Markdown-section-aware. Within a section, build paragraph blocks; pack paragraphs into chunks until the next paragraph would push the chunk above 300 tokens, then start a new chunk. Don't cross section boundaries. Token counting via the embedding model's tokenizer (`AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")`), called once at script start.
- **Batch size.** 32 (`EmbeddingSettings.batch_size`).
- **Normalisation.** `normalize_embeddings=True` on `model.encode(...)`. Required for cosine similarity to work as expected with HNSW.
- **Idempotency.** Single transaction: `DELETE FROM policy_chunks WHERE source_path = $1`, then bulk insert.
- **Output.** Reports rows inserted, total tokens, model name, dimension. Logs to stdout, not the audit log (this is a maintenance script, not a pipeline event).

## Synthetic claim generator details

Generates exactly 9 claims per run. Reproducible: `random.seed(20260508)` so the run is byte-identical session-to-session. Idempotency: `TRUNCATE claims CASCADE` before inserting, gated by an `--allow-truncate` flag so an accidental run doesn't wipe a populated DB.

## Test surface and pass-rate expectations

Aggregate target: **~46–50 tests** across the new files plus the 7 existing backend tests. Pass rate: 100% in CI. The conditional embedding-model test runs only with `RUN_EMBEDDING_TESTS=1` (default off in CI to keep job time short — flagged optional; can be flipped on if you want a full end-to-end indexing assertion in CI).

## CI changes — proposed plus flagged optionals

**Proposed (in Phase 1):**

- Add `services.postgres: pgvector/pgvector:pg16` to the backend job; export `DATABASE_URL`.
- Run `uv run alembic upgrade head` before `uv run pytest`.

**Flagged optional (recommended; cut if you want them deferred):**

- `pip-audit` (or `uv-secure`) on the backend job.
- `npm audit --audit-level=high` on the frontend job.

Recommendation: include both now. They were called out in the Phase 0 report and they're a five-minute add. If they fail on a transitive vuln, we triage in this commit rather than ship a known issue forward.

## Local development changes — proposed

- `.env.example` at repo root with `DATABASE_URL=postgresql://localhost/agentic_claims_dev`, plus `ANTHROPIC_API_KEY=` and `MISTRAL_API_KEY=` as Phase 2 placeholders.
- `README.md`'s Local development section gets three additions: configure `.env`, run migrations, seed + index.
- Documented Neon-from-local override: developer can set `DATABASE_URL` to a Neon dev branch URL and skip `setup-dev-db.sh` entirely. Useful if the developer's machine is the resource-constrained Mac mini referenced in the build plan.

## Render env var — handling

Phase 1 does not commit the Neon URL anywhere. The flow:

1. After this plan is approved, I'll ask explicitly: *"Ready to execute. Please paste the Neon DATABASE_URL into the chat — I will use it to (a) populate a local `.env` file for development (gitignored), (b) run the initial migration locally, and (c) instruct you to set it as an environment variable on Render for the deployed backend. I will not commit it to the repository or log it."*
2. On receipt: write to `.env`, run `alembic upgrade head` against Neon, run the seed + index scripts. Confirm success in the chat.
3. Tell you to set `DATABASE_URL` on Render's Environment tab to the same value. Render will auto-redeploy. The redeploy is your action to take (the Render API isn't accessible to me).

Stress: never echoed in the chat after first receipt; never written to logs; never committed.

## New dependencies — every one flagged

Per the Dependency Discipline standard, every addition gets a justification:

- **`psycopg[binary]>=3.2`** — Postgres driver. `psycopg3` (not psycopg2) for the modern connection model and proper type adapters. Binary build chosen for ease of install on developer machines and CI; flip to source build later if Render's environment objects.
- **`pgvector>=0.3`** — Python adapter so psycopg understands the `vector` column type as a Python list/ndarray without per-call boilerplate. Tiny dependency, the canonical choice for pgvector-on-psycopg.
- **`sqlalchemy>=2.0`** — required by Alembic. Not used by the runtime app (raw SQL via psycopg). Listed explicitly so the dependency tree is honest.
- **`alembic>=1.13`** — migrations. Reasoned above under "Migration tooling choice".
- **`sentence-transformers>=3.0`** — locked architectural decision. No substitute.
- **`pip-audit>=2.7`** *(dev, optional)* — flagged above under CI changes.

No other dependencies are added in Phase 1. `anthropic`, `mistralai`, `langfuse`, `sse-starlette` arrive in Phases 2/4 when they're actually used.

## Risks and downstream impacts

1. **Audit row schema is an interface** — Phases 2–6 will write to `audit_log`. The columns and the `agent` enumeration are locked at end of Phase 1; adding a new agent (none planned) requires a migration + an explicit interface review.
2. **Audit canonicalisation function is an interface** — once data is written, changing the canonical form invalidates every existing chain. Locked at end of Phase 1.
3. **Embedding model is a one-way door** — already locked in `CLAUDE.md`. The settings validator pinning dimension to 384 is the enforcement mechanism.
4. **`claims.status` enum** — Phase 1 declares all states the build plan lists for Phase 5; adding one later requires a migration. If you'd prefer to declare only `received` and `awaiting_human` now and grow it later, flag at approval time.
5. **`scenario_tag` column** — exists for the demo. Production schema would not carry it. I'm comfortable shipping it because the column is null-default and the prototype is the deliverable; flag if you'd rather keep it out of the schema and represent scenarios in the seed metadata only.
6. **Settings field renaming** — once Phase 2's LLM Gateway reads `Settings.llm.anthropic.orchestrator_model`, those names are locked. I've named them per agent rather than per provider so a model-per-agent change is local.
7. **HNSW vs IVFFlat** — chosen HNSW for prototype scale. If we ever index a multi-thousand-chunk corpus, IVFFlat with a tuned `lists` count becomes preferable. Not a Phase 1 concern.
8. **Render Postgres → Neon** — the docs change is purely descriptive; the deployment was already planned to use Neon (per the Phase 0 report's outstanding-items note saying "Render Postgres database (or Neon as an alternative)").

## Optional enhancements (delivered after the spec, never in place of it)

1. **Async `psycopg.AsyncConnection`** — would line the DB up with FastAPI's async event loop. Net win is small (the audit writes aren't a hot path) and the audit chain logic is clearer in synchronous form. Defer to Phase 5+ if the orchestrator needs it.
2. **Pre-commit hooks** — ruff, prettier, and a "no client name" grep. Carried over from the Phase 0 report. Recommend folding into Phase 7 polish.
3. **`uv-secure` instead of `pip-audit`** — newer, uv-native equivalent. Either works; I'll default to `pip-audit` because it's the more battle-tested choice and uv-secure is still relatively new.
4. **A `verify_audit_chain` CLI** (`uv run python -m backend.app.audit.verify`) — would expose the chain check as a one-line command for the demo. Phase 1 ships the function; the CLI wrapper is a 10-line add. Recommend including in Phase 5 or 6 alongside the audit log viewer in the UI.
5. **Tighter version pinning** — Phase 0 report noted carets on most deps. Could pin to tildes here and now. Low priority; not blocking.
6. **`numpy` lower bound** — `sentence-transformers` pulls in numpy transitively. Could pin a lower bound explicitly to match production. Defer unless we hit a numpy 2.x incompatibility.

## What I need from you to start execution

In order:

1. Plan approval (or feedback for revision per `docs/prompts/README.md`'s rejection workflow).
2. After approval, the Neon `DATABASE_URL` — pasted into the chat in response to the explicit ask described in Step 3 of the prompt. I will write it to `.env` only.
3. After execution, your action to set `DATABASE_URL` on Render's Environment tab and confirm the auto-redeploy goes Live. Optionally, a quick verify against the Render service logs that the deployed backend reaches Neon at startup.

That's the full scope of architect involvement. Everything else lives inside the prompt's Step 3 / Step 4 / Step 5 / Step 6 / Step 7 sequence and lands in a single Phase 1 commit.

---

**Plan saved at**: `docs/prompts/02-phase-1-data-layer-plan.md`. Ready for your verdict.

---

## Approval

**Approval message:** "All seven headline decisions accepted as proposed:
1. Alembic with raw SQL — yes.
2. Audit chain formula and canonicalisation as documented — yes.
3. Schema as drawn, including the full status enumeration up front and
   scenario_tag in the schema — yes.
4. Five settings sub-models with Decimal for monetary, dimension pinned
   to 384 — yes.
5. CI changes including the optional pip-audit and npm audit — yes,
   include them in this commit.
6. New deps as flagged — all approved.
7. Docs fix-up (Render Postgres → Neon) — yes.

Proceed to Step 2 (record the approval footer in the plan file with the
verbatim approval message and ISO 8601 UTC timestamp), then ask me for
the Neon DATABASE_URL."

---

**Approved by:** Dermot Copps
**Approved at:** 2026-05-08T15:39:42Z
