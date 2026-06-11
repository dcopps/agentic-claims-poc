# Agentic Claims POC

A working prototype demonstrating multi-agent agentic AI for insurance claims processing — retrieval-augmented coverage validation, structured settlement estimation, output guardrails, tamper-evident audit, and human-in-the-loop escalation.

> **Status: Build in progress.** This README will be expanded as the build progresses. The full demo, live URL, setup instructions, and design discussion arrive at the end of Phase 7. The architectural design is locked and visible in `docs/` and `diagrams/`.

## What this is

A multi-agent claims processing pipeline built on:

- **A tiered model strategy** — Claude Sonnet for orchestration reasoning, Claude Haiku for fast extraction and output guardrails, Mistral Large for open-weight reasoning that handles PII-sensitive decisions and is fine-tunable.
- **A RAG pipeline** — claim narratives embedded and matched against an indexed policy corpus, with retrieved chunks cited in every coverage decision.
- **A tamper-evident audit vault** — every agent action logged to a SHA-256 hash chain in PostgreSQL (with SQL Server Ledger Tables described as the production target).
- **A decoupled architecture** — claims persisted to a system of record before any agent fires, with the AI pipeline triggered by an event. Replay against historical claims is a first-class capability.
- **A regulator-ready posture** — DORA-compliant provider substitutability, GDPR-compliant data residency, an explicit escalation policy with named rules, and an LLM Gateway that mediates every model call.

## Reproducible build

Every prompt used to build this prototype is archived in [`docs/prompts/`](docs/prompts/), numbered in build order. Re-running the prompts in sequence against a fresh Claude Code session, in an empty directory, reproduces the entire repository.

The outcome of each phase — what was built, test counts, issues discovered — is recorded in [`docs/build-log.md`](docs/build-log.md). Together the prompts archive and the build log make the build process inspectable end-to-end: prompts capture intent, the build log captures outcome.

## Documentation

- [`docs/architecture-stack-reference.md`](docs/architecture-stack-reference.md) — full development vs production stack reference
- [`docs/build-log.md`](docs/build-log.md) — chronological record of every phase, task, and significant fix
- [`docs/prompts/`](docs/prompts/) — every prompt used in build order
- [`diagrams/`](diagrams/) — four Mermaid diagrams covering the agent flow, the RAG mechanics, the claim lifecycle, and the production Azure topology

## Local development

Supported developer platform: macOS. Linux is workable but the install commands below assume Homebrew.

### Prerequisites

- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/).
- **Node 20+** with `npm`.
- **PostgreSQL 17 with pgvector**, installed natively (no Docker). Postgres 17 is pinned because the Homebrew `pgvector` bottle currently ships builds only for `postgresql@17` and `postgresql@18`. The project's stack reference accepts "Postgres 16+", but the local install commands target 17 specifically.

### Install Postgres + pgvector

```bash
brew install postgresql@17 pgvector
brew services start postgresql@17

# postgresql@17 is keg-only — add it to PATH so psql and friends are visible.
echo 'export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"' >> ~/.zshrc
exec zsh
```

### Create the dev database

```bash
bash scripts/setup-dev-db.sh
```

The script verifies your Postgres install (psql on PATH, server reachable, version >= 16, pgvector available), creates the `agentic_claims_dev` database, and enables the extension. Idempotent — safe to re-run.

### Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set `DATABASE_URL`. Two patterns are supported:

- **Local Postgres** (the default): `DATABASE_URL=postgresql://localhost/agentic_claims_dev`
  after running `setup-dev-db.sh`.
- **Neon dev branch**: paste the Neon connection string directly into `DATABASE_URL`
  and skip `setup-dev-db.sh` entirely. Useful on resource-constrained machines or
  when you want to share state with the deployed backend.

`.env` is gitignored; never commit a populated copy. `ANTHROPIC_API_KEY` and
`MISTRAL_API_KEY` are optional in Phase 1 — they are required in Phase 2 when
the LLM Gateway lands.

### Run database migrations

```bash
uv run alembic --config backend/alembic.ini upgrade head
```

Applies the schema (`claims`, `audit_log`, `policy_chunks`) against
whichever database `DATABASE_URL` points to. Re-runnable; the migration
runner tracks state in the `alembic_version` table.

### Seed and index

```bash
uv run python -m backend.data.seed_claims --allow-truncate
uv run python -m backend.data.index_policy
```

The first command inserts the nine synthetic demo claims (three scripted
scenarios plus six background); the second chunks `backend/data/sample_policy.txt`
and writes embeddings into `policy_chunks`. Re-running the indexer
replaces prior rows for the same source path; the seeder requires
`--allow-truncate` to overwrite a populated `claims` table.

### Run the backend

```bash
uv sync
uv run uvicorn backend.app.main:app --reload
```

`/health` will respond at `http://127.0.0.1:8000/health` with `{"status":"ok","version":"0.0.1"}`.

### Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173/` — the page should display "backend: ok". The Vite dev server proxies `/health` and `/api/*` to the local FastAPI server, so no environment variables are required in dev.

### Test, lint, type-check

```bash
# Backend
uv run pytest
uv run ruff check .
uv run mypy backend

# Frontend
cd frontend
npm test
npm run lint
npm run typecheck
```

## Getting started

Phase 0 ships the runnable scaffold (this README's "Local development" section). Subsequent phases layer on the data model, the LLM Gateway, the agents, the orchestrator, and the demo UI. See [`docs/build-log.md`](docs/build-log.md) for what's currently in place.
