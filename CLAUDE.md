# Agentic Claims POC

---
> **Global coding standards apply to this project.**
> Read `~/.claude/CLAUDE.md` before starting any session.
---

## Project Overview

A working prototype demonstrating multi-agent agentic AI for insurance claims processing — retrieval-augmented coverage validation, structured settlement estimation, output guardrails, tamper-evident audit, and human-in-the-loop escalation.

The prototype is the public deliverable. The production architecture is described in `docs/architecture-stack-reference.md` and `diagrams/4-production-architecture.mmd` but is not built — its credibility comes from being internally consistent and clearly mapped to the prototype.

This is a generic prototype for a regulated specialty insurer. The client name does not appear anywhere in the codebase or documentation. If you spot it, remove it.

## Tech Stack

**Backend**
- Python 3.11+
- Package manager: **uv** (single tool replacing pip, pip-tools, virtualenv)
- Web framework: FastAPI with Uvicorn (ASGI)
- Data validation: Pydantic v2
- Testing: pytest
- LLM SDKs: `anthropic`, `mistralai`
- Embeddings: `sentence-transformers` running `BAAI/bge-small-en-v1.5` on CPU
- Observability: Langfuse SDK (self-hosted instance)
- Streaming: Server-Sent Events via `sse-starlette`

**Frontend**
- React 18+ with Vite
- Tailwind CSS
- TypeScript
- TanStack Query for server state
- ESLint + Prettier

**Data**
- PostgreSQL 16+ with the `pgvector` extension
- Single database hosts: claims of record, audit log (with hand-rolled SHA-256 chain hash), policy chunk vector index
- **Local development** runs Postgres natively on macOS via Postgres.app or Homebrew (no Docker, no virtualisation overhead). A setup script enables the pgvector extension and creates the dev database. A developer can also point `DATABASE_URL` at a Neon dev branch and skip local Postgres entirely.
- **Production-deployed prototype** runs Neon (managed Postgres) — `eu-central-1` / Frankfurt, Postgres 17 with pgvector 0.8.0 enabled
- Production target replaces this with Azure SQL Managed Instance + Ledger Tables; documented in `docs/architecture-stack-reference.md` but not implemented in the prototype

**Hosting & CI**
- Backend: Render
- Frontend: Vercel
- Postgres: Neon (managed Postgres) — `eu-central-1` / Frankfurt, Postgres 17, pgvector 0.8.0
- CI: GitHub Actions (Azure DevOps Pipelines is the production target — config in `infra/azure-devops-pipeline.yml` for reference, GitHub Actions actually runs the prototype)

## Project Structure (target — fully populated by end of Phase 0)

```
agentic-claims-poc/
├── README.md
├── CLAUDE.md
├── BUILD-PLAN.md                  # local only — not committed
├── HANDOFF.md                     # local only — not committed
├── pyproject.toml                 # uv project config
├── uv.lock                        # uv lockfile
├── .editorconfig
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml                 # lint, type-check, test
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── src/
├── backend/
│   ├── pyproject.toml             # backend project config (or top-level)
│   ├── settings.py                # Pydantic Settings model
│   ├── settings.yaml.template     # Settings template
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI app
│   │   ├── api/                   # API route handlers
│   │   ├── agents/                # Doc-Parser, Validator, Adjuster, Guardrail
│   │   ├── orchestrator/          # Pipeline coordination
│   │   ├── rag/                   # Embedding, retrieval
│   │   ├── audit/                 # Hash chain logic
│   │   ├── llm/                   # LLM Gateway abstraction
│   │   ├── escalation/            # Escalation policy engine
│   │   ├── models/                # Pydantic data models
│   │   ├── logging/               # API call logger, structured logs
│   │   └── prompts/               # Externalised prompts
│   │       ├── system/            # role/format prompts
│   │       └── user/              # user-message templates
│   ├── data/
│   │   ├── sample_policy.txt      # commercial property policy excerpt
│   │   └── seed_claims.py         # synthetic claim generator
│   └── tests/
│       ├── conftest.py
│       ├── fixtures/
│       └── test_*.py
├── scripts/
│   └── setup-dev-db.sh            # one-time local Postgres + pgvector setup
├── docs/
│   ├── architecture-stack-reference.md
│   ├── change-governance.md       # Phase 7
│   ├── dora-third-party-register.md  # Phase 7
│   ├── design-decisions.md        # Phase 7
│   ├── build-log.md               # appended after every phase
│   └── prompts/                   # every prompt archived in build order
│       ├── README.md
│       └── NN-descriptive-name.md
├── diagrams/
│   ├── 1-headline-agent-flow.mmd
│   ├── 2-rag-zoom.mmd
│   ├── 3-decoupling-event-flow.mmd
│   ├── 4-production-architecture.mmd
│   └── README.md
└── infra/
    └── azure-devops-pipeline.yml  # production CI/CD reference
```

## Build Approach

Phases are defined in `BUILD-PLAN.md` (kept locally; not committed). The build is plan-first — each phase prompt opens by producing a written plan, waits for confirmation, then executes. This follows the global plan-first standard at `~/.claude/CLAUDE.md`.

Every phase ends with two appends:

- A new entry to `docs/build-log.md` describing what was built, test counts, and any issues.
- The phase's prompt saved verbatim to `docs/prompts/NN-descriptive-name.md`.

Together these make the build reproducible end-to-end.

## Current Status

- **Date:** 2026-06-27
- **Phase:** Phase 8.5 complete (test-isolation fix); local test-DB setup + suite run next.
- **What works:** Closed a latent structural hazard exposed during Phase 8.4 verification: `uv run pytest` resolved its database from `.env` (which points at deployed Neon), and the `clean_db` fixture TRUNCATEs `claims`, `audit_log`, and `policy_chunks` — so any laptop pytest run wiped production. (This is what depopulated the deployed DB during Phase 8.4; it was then repopulated via `index_policy` + `seed_claims`.) The fix lives entirely in the test layer: `backend/tests/conftest.py` gains a pure resolver `_resolve_test_database_url(test_url, database_url)` that prefers `TEST_DATABASE_URL` (from `.env.test`), falls back to `DATABASE_URL` only when non-Neon (the CI path), and **categorically raises on any `*.neon.tech` host** — no env-var bypass. The resolved URL is pinned for the session via `os.environ["DATABASE_URL"]` (the highest-precedence path `Settings` honours), so bare `open_connection()` calls are covered too. `clean_db` gains a defence-in-depth Neon guard before its TRUNCATE. New `backend/tests/test_db_isolation.py` adds three discriminator tests against the pure resolver (no DB needed). Verified locally: the three discriminator tests pass, and running a `clean_db`-dependent test with the current Neon `.env` and no `.env.test` now **errors at setup with the guard's `RuntimeError` instead of wiping** — the deployed DB is protected. New `.env.test.example` + a `.gitignore` `!.env.test.example` negation + a README "Local test database setup" section document the convention. No production code touched (`Settings` is read, not modified); no interface change. `/health` reports `version=0.8.5` once redeployed.
- **What's next:** Dermot runs the one-time local test-DB setup (`DEV_DB_NAME=agentic_claims_test ./scripts/setup-dev-db.sh`; `cp .env.test.example .env.test`; set `TEST_DATABASE_URL`), then `uv run pytest` to confirm 338 backend tests pass against the local test DB. Still pending from Phase 8.4: deploy to Render and run the deployed audit-persistence verification (now also surfaces `/health=0.8.5`).

## Standing Instructions

**Plan first, code second.** For any code work, produce a written plan covering files to be created or modified, the approach, key design decisions, risks, dependencies, and any interface impact. Wait for explicit confirmation before writing code.

**Update `docs/build-log.md` after every phase, task, or significant fix** with:
- The prompt that was given (or a reference to `docs/prompts/NN-...md`)
- What was built/changed
- Test count and pass rate
- Any issues discovered

**Update this `CLAUDE.md` before every commit.** Specifically the "Current Status" section: date, phase, what works, what's next. CLAUDE.md is the handoff document — if it's not in here, the next session won't know about it.

**Save every prompt to `docs/prompts/`** in numerical order with descriptive filenames. Each prompt I receive will end with an explicit instruction to save itself; honour that instruction. The archive is part of the public deliverable.

**Anonymisation.** This is a generic prototype. The client name does not appear in code, comments, tests, fixtures, documentation, commit messages, or log output. If you find it, remove it.

**Defensive programming order:** sanitise → validate → abort → execute. No silent fallbacks. No swallowing exceptions. Failures must be visible, traceable, and include diagnostic context.

**Function size:** 30 lines is a prompt to reconsider; 50 lines is a hard limit. Exceptions get a one-line comment explaining why extraction was not done.

**Settings hierarchy:** defaults (in `settings.py`) → `settings.yaml` → CLI flags → environment variables. New settings must appear in both `settings.py` and `settings.yaml.template`. No hardcoded values; no magic numbers without a named constant and a comment.

**Externalised prompts.** All Claude API and Mistral API prompts live in `backend/app/prompts/system/` and `backend/app/prompts/user/`, loaded via a `PromptLoader` class. No inline f-string prompts in source code.

**System / user separation.** All LLM calls use the `system` parameter for role/format instructions and `messages[user]` for dynamic content only. Personas are defined in the system prompt.

**Commit protocol.** Commit frequently with descriptive messages. Push after every logical unit of work. Never leave uncommitted work at the end of a session. CLAUDE.md updated to reflect current state before every commit.

**Security.** Never embed credentials, API keys, connection strings, or secret tokens in code, comments, test fixtures, or log output. These come from environment variables only. Add `.env` and `.env.*` to `.gitignore`.

**Interface stability.** Any change to a JSON output schema, an HTTP response shape, a database column, or any contract that crosses a boundary requires explicit acknowledgement in the plan before proceeding.

**Dependency discipline.** Do not add new dependencies without flagging them in the plan, stating why the existing stack cannot cover the need, and waiting for confirmation.

## Architectural Decisions (Locked)

- **Models.** Claude Sonnet (Orchestrator), Claude Haiku (Doc-Parser, Guardrail), Mistral Large (Validator, Adjuster). Adjuster gets a LoRA adapter in production; not in the prototype.
- **Database.** PostgreSQL with pgvector for the prototype. Single database hosts claims, audit log, vector index. Local dev uses native Postgres (Postgres.app or Homebrew) or, optionally, a Neon dev branch via `DATABASE_URL`; deployed dev/prod uses Neon (managed Postgres) in `eu-central-1` (Frankfurt). Production target: Azure SQL Managed Instance with Ledger Tables for audit.
- **Embedding model.** `BAAI/bge-small-en-v1.5` via `sentence-transformers`, runs on CPU inside the FastAPI process. Same model used for indexing the policy and for encoding query narratives — embedding model is a one-way door, never silently swap.
- **Streaming transport.** Server-Sent Events. The FastAPI endpoint pushes pipeline progress to the React frontend as agents complete.
- **Hosting.** Render (backend), Neon (Postgres), Vercel (frontend). Free tiers sufficient for the demo.
- **Decoupled architecture.** Claims are persisted to a claims-of-record table before any agent fires. The pipeline is triggered by a button click in the prototype (simulating the production Azure Service Bus event).
- **Demo content.** Commercial Property line. Three scripted scenarios: auto-approve $85,000 commercial water damage; threshold escalation $850,000 fire loss; guardrail escalation $1.4M with hallucinated endorsement.
- **Escalation policy.** OR semantics. Hard rules (always escalate): guardrail_failed, claim_type_watchlist, claimant_watchlist, cross_jurisdictional. Threshold rules: settlement > $250,000, validator confidence < 0.65, adjuster confidence < 0.75. Policy lives in `backend/app/escalation/policy.yaml`. Every decision logs which rules fired.
- **Local dev environment.** Native Postgres (Postgres.app or Homebrew), no Docker. Chosen to keep the local footprint small and avoid virtualisation overhead. **Two databases:** `agentic_claims_dev` runs the app (via `DATABASE_URL`); `agentic_claims_test` runs pytest (via `TEST_DATABASE_URL` in `.env.test`). The two are kept separate because the test suite's fixtures TRUNCATE tables — the test fixtures resolve `TEST_DATABASE_URL` in preference to `DATABASE_URL` and **categorically refuse to run against any `*.neon.tech` host** (Phase 8.5, after a Phase 8.4 incident where a pytest run against a Neon-pointing `.env` wiped the deployed database). CI needs no `TEST_DATABASE_URL`: its `DATABASE_URL` is a localhost service container, which the non-Neon fallback accepts.

### Locked interface extensions since Phase 4

These additive extensions to the Phase 4 contracts are locked. All are additive
(existing keys unchanged), so they preserve the audit-log-as-trusted-record
property — the audit log alone is sufficient to reconstruct and explain any past
decision. Any change to these is an interface-stability event.

- **Adjuster `settlement_estimate` audit `output`** gains a full `reasoning` field (untruncated, alongside `reasoning_excerpt`) — Phase 5.
- **Validator `coverage_check` audit `llm_call.provider` / `model`** report the *actual* provider (`self._provider.vendor`) and model in use, not a hardcoded vendor — so a provider-substitution variant is recorded truthfully — Phase 5.
- **`pipeline_started` audit payload + SSE event** gain a `variant` field (default `"default"`) — Phase 5.
- **`audit_log.agent` CHECK** extended to include `'human'`; audit steps `human_approval` / `human_rejection` — Phase 6 (migration 0002).
- **`claims.status` CHECK** extended to include `'aborted'` (terminal state for a human-rejected claim) — Phase 6 (migration 0002).
- **Adjuster `settlement_estimate` audit** gains a top-level `demo_fixture: bool`; when `true` the `llm_call` block records no model call — Phase 7. The deterministic demo affordance is auditable, not hidden.
- **Doc-Parser `doc_extract` audit** gains a top-level `"fields_source": "claim_record"` — Phase 8.2. Records that the structured fields were sourced from the claim record, not from LLM extraction (the LLM now produces only `narrative_summary`). Additive; the `output` block shape is unchanged.
- **All four agents' audit payloads** (`doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`) gain `llm_call.prompt: { system: str, user: str }` — Phase 8.3. The literal, fully-substituted system + user prompt the model received (not the raw template), so the audit captures exactly what each agent sent. Additive; nested under the existing `llm_call` block, all existing keys unchanged. Present only when an LLM call actually happened: the Adjuster demo-fixture path (Phase 7) emits no `prompt` key because it sends no prompt.

## Repository Name

`agentic-claims-poc`. Do not rename. Do not introduce client-specific naming.

## What goes in the repo vs what stays out

In the repo (publicly committable):

- `README.md`, `CLAUDE.md`
- `frontend/`, `backend/`, `infra/`, `scripts/`
- `docs/architecture-stack-reference.md`, `docs/change-governance.md`, `docs/dora-third-party-register.md`, `docs/design-decisions.md`, `docs/build-log.md`, `docs/prompts/`
- `diagrams/*.mmd`
- `.github/workflows/`, config files
- Sample policy excerpt in `backend/data/sample_policy.txt`
- Synthetic seed claims in `backend/data/seed_claims.py`

Stays out of the repo (in `.gitignore`):

- `BUILD-PLAN.md` (treated as local prep, not part of the public deliverable)
- `HANDOFF.md` (one-time kickoff notes)
- `.env`, `.env.*`, API keys, secrets
- `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`
- `node_modules/`, `dist/`, `build/`
- Local database dumps, model caches, output artefacts under `output/` if any
