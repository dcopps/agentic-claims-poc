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
- **Local development** runs Postgres natively on macOS via Postgres.app or Homebrew (no Docker, no virtualisation overhead). A setup script enables the pgvector extension and creates the dev database.
- **Production** runs Render's managed Postgres with pgvector enabled
- Production target replaces this with Azure SQL Managed Instance + Ledger Tables; documented in `docs/architecture-stack-reference.md` but not implemented in the prototype

**Hosting & CI**
- Backend: Render
- Frontend: Vercel
- Postgres: Render-managed
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

- **Date:** 2026-05-08
- **Phase:** Phase 0 complete; Phase 1 next.
- **What works:** Hello-world deployed; CI runs on PRs.
- **What's next:** Phase 1 — Data layer and settings infrastructure.

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
- **Database.** PostgreSQL with pgvector for the prototype. Single database hosts claims, audit log, vector index. Local dev uses native Postgres (Postgres.app or Homebrew); deployed dev/prod uses Render's managed Postgres. Production target: Azure SQL Managed Instance with Ledger Tables for audit.
- **Embedding model.** `BAAI/bge-small-en-v1.5` via `sentence-transformers`, runs on CPU inside the FastAPI process. Same model used for indexing the policy and for encoding query narratives — embedding model is a one-way door, never silently swap.
- **Streaming transport.** Server-Sent Events. The FastAPI endpoint pushes pipeline progress to the React frontend as agents complete.
- **Hosting.** Render (backend, Postgres), Vercel (frontend). Free tiers sufficient for the demo.
- **Decoupled architecture.** Claims are persisted to a claims-of-record table before any agent fires. The pipeline is triggered by a button click in the prototype (simulating the production Azure Service Bus event).
- **Demo content.** Commercial Property line. Three scripted scenarios: auto-approve $85,000 commercial water damage; threshold escalation $850,000 fire loss; guardrail escalation $1.4M with hallucinated endorsement.
- **Escalation policy.** OR semantics. Hard rules (always escalate): guardrail_failed, claim_type_watchlist, claimant_watchlist, cross_jurisdictional. Threshold rules: settlement > $250,000, validator confidence < 0.65, adjuster confidence < 0.75. Policy lives in `backend/app/escalation/policy.yaml`. Every decision logs which rules fired.
- **Local dev environment.** Native Postgres (Postgres.app or Homebrew), no Docker. Chosen to keep the local footprint small and avoid virtualisation overhead.

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
