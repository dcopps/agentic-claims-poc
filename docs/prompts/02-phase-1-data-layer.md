# Prompt 02 — Phase 1: Data Layer and Settings Infrastructure

## Read first

Before doing anything else, read these three files in this directory:

- `CLAUDE.md` — global standards reference, project overview, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 1.
- `docs/prompts/01-phase-0-repository-scaffold-report.md` — what Phase 0 actually delivered, what's still outstanding, what to build on.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. The relevant items for this prompt: plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts (no inline f-strings), interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 1 of `BUILD-PLAN.md` — Data layer and settings infrastructure. The definition of done is in the build plan; meet it.

By the end of Phase 1 the system has:

- A persistent database schema for claims, audit log, and policy chunks.
- A settings architecture extended with named sub-models for the database, LLM providers, embeddings, observability, and escalation.
- A cryptographically chained audit vault with the defensive programming pattern applied throughout.
- A small but realistic commercial-property policy excerpt indexed into the vector store via the embedding model.
- A synthetic claim generator producing fixtures that span the three locked demo scenarios.
- Comprehensive tests covering every guard clause and every contract.

No agents, no LLM calls, no orchestrator, no UI changes. Those are Phases 2–6. Phase 1 is purely the data foundation.

## Current state of the project (for orientation)

Phase 0 delivered (see `docs/prompts/01-phase-0-repository-scaffold-report.md` for the full record):

- Top-level uv project with FastAPI backend, React/Vite/Tailwind frontend, GitHub Actions CI for both stacks.
- A minimal `Settings` Pydantic model and matching `settings.yaml.template`.
- An idempotent `scripts/setup-dev-db.sh` that creates a local `agentic_claims_dev` database on Postgres 17 and enables the `vector` extension.
- A `/health` endpoint and a placeholder `/api` router (still empty).
- A defensive YAML overlay loader on `Settings`.
- `render.yaml` blueprint deploying the backend to Render free tier.

Phase 0 deployment work, completed manually after the report was written:

- **Render Web Service:** live at `https://agentic-claims-poc-backend.onrender.com` (Blueprint provisioned from `render.yaml`).
- **Vercel frontend:** live at `https://agentic-claims-poc.vercel.app` with `VITE_API_BASE_URL` configured against the Render URL and CORS allowlisted on the backend.
- **Neon Postgres:** project `agentic-claims-poc` in AWS Frankfurt (`eu-central-1`), Postgres 17, pgvector 0.8.0 confirmed enabled. Connection string is in the architect's password manager and will be supplied as the value of `DATABASE_URL` when this prompt asks for it. **The `DATABASE_URL` is NOT yet set on Render** — Phase 1 wires it in.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering:

- Files and directories you will create or modify.
- Database schema design — tables, columns, types, constraints, indexes.
- Migration tooling choice — Alembic versus a simple `migrations/` folder with hand-written SQL files. Both are acceptable; recommend the one you'd ship and explain why. The criterion: it must be re-runnable, version-controlled, and execute identically against local Postgres and Neon.
- Settings sub-models — exact field set per sub-model (DatabaseSettings, LLMSettings, EmbeddingSettings, LangfuseSettings, EscalationSettings). For sub-models whose consumers don't exist until Phase 2 (LLM, Embedding, Langfuse) include only the fields needed to declare the connection / model identifier; defer per-call parameters until they're consumed. EscalationSettings should match the locked rule structure in `CLAUDE.md`'s Architectural Decisions section.
- Audit chain implementation — exact SHA-256 chain hash formula, the row content canonicalisation strategy (because the same logical content must always hash identically), and the order in which the defensive pattern (sanitise → validate → abort → execute) applies.
- Sample commercial property policy excerpt — outline of the sections you'll include (named perils, exclusions, sub-limits, business interruption, general conditions, definitions). Phase 1's scope says 2–3 pages of realistic wording. Confirm you'll keep it generic — no client name, no real insurer wording.
- Indexing script — chunking strategy, batch size, where the vectors are written. Use `bge-small-en-v1.5` via the `sentence-transformers` library. Same model used at indexing time and at retrieval time (one-way door).
- Synthetic claim generator — exact shape of the generated claims, ensuring at least one claim that demonstrably matches each of the three locked demo scenarios (auto-approve $85k water damage, threshold escalation $850k fire, guardrail escalation $1.4M with hallucinated endorsement). The "guardrail" claim is generated as a normal claim in Phase 1; the hallucination is injected by the Adjuster's output in later phases.
- Tests — for every guard clause (what triggers it, what the expected error message contains), for the seed generator (right scenario coverage), for the indexing script (right number of chunks, right embedding dimension).
- CI changes — adding a Postgres + pgvector service container to the backend job so tests can run against a real database. Optionally adding `npm audit` and `pip-audit` (recommended in Phase 0's report; if you include them, flag explicitly).
- Local development changes — the README's "Local development" section needs updating to mention `.env` for `DATABASE_URL`, and to acknowledge the optional Neon-from-local pattern (developer can override `DATABASE_URL` to point at a Neon dev branch if they prefer).
- Documentation fix-up — `docs/architecture-stack-reference.md` currently says "PostgreSQL on Render" for the prototype's data layer. It should say Neon. Multiple references; fix all of them. This is a preamble step for Phase 1, not a separate concern.
- Render env var — `DATABASE_URL` set to the Neon connection string. The architect supplies the value when execution starts (do not expect it in this prompt; ask explicitly via the chat once the plan is approved). Stress: do not commit the connection string to the repository, and do not echo it in logs.
- Any new dependency — flag each one. Likely additions: `psycopg[binary]` (or `asyncpg`), `sqlalchemy`, `alembic` if chosen, `sentence-transformers`. State why the existing stack cannot cover it; wait for confirmation before adding.
- Risks and downstream impacts, especially anything that affects the LLM Gateway or the agents in Phase 2.
- Any deployment steps that require my involvement (typically: setting `DATABASE_URL` on Render once you ask for the value).
- Optional enhancements you would recommend, clearly labelled as optional. Deliver the spec first; suggestions go in the plan, never silently in the code.

Save the plan **before** asking me to review it, so I can read it in my editor. Write it to:

```
docs/prompts/02-phase-1-data-layer-plan.md
```

Top-level heading: `# Plan 02 — Phase 1: Data Layer and Settings Infrastructure`. Below that, the body of the plan in the same shape it was produced.

After saving the file, point me at it and ask for my verdict. Do not write any other code or modify any other files yet.

## Step 2 — Approval or rejection

Same workflow as Phase 0.

**If I approve** (any reply along the lines of "yes", "go ahead", "approved", or similar):

Append a horizontal rule and an `## Approval` section to the plan file. Order the section so the timestamp closes the file (per the convention documented in `docs/prompts/README.md`):

```
## Approval

**Approval message:** "<my exact approval message, quoted>"

---

**Approved by:** Dermot Copps
**Approved at:** <ISO 8601 timestamp in UTC, e.g. 2026-05-09T14:32:18Z>
```

Then proceed to Step 3.

**If I reject** (any reply that is not unambiguous approval — including detailed feedback, a counter-proposal, or a request for changes):

Treat the current plan as rejected. Do not silently amend the canonical plan file. Instead:

1. Append a `## Rejection` footer to the existing plan file with timestamp, summary of feedback, and a pointer to the next iteration.
2. Rename the rejected file to `02-phase-1-data-layer-plan-rejected-NN.md` (where `NN` is the next available two-digit iteration number).
3. Produce a revised plan and save it freshly as `docs/prompts/02-phase-1-data-layer-plan.md`.
4. Return to Step 2 (await my verdict on the new version).

Iterate as needed. Only after the canonical plan file carries an `## Approval` footer should you proceed to Step 3.

## Step 3 — Execute

After the plan is approved, execute Phase 1 per `BUILD-PLAN.md`. Constraints from `CLAUDE.md` apply throughout:

- **Defensive programming** (sanitise → validate → abort → execute) for every function that takes input. Audit chain logic in particular must follow this pattern strictly.
- **Function size:** 30 lines is a prompt to reconsider; 50 lines is a hard limit.
- **Settings hierarchy:** new fields appear in both `backend/settings.py` and `backend/settings.yaml.template`. No hardcoded values. No magic numbers without a named constant and a comment explaining why.
- **Type hints** on every function signature.
- **Tests:** every new function gets tests; every guard clause gets a triggering test; tests verify error message content, not just that an exception was raised.
- **Anonymisation:** the client name does not appear anywhere in code, comments, tests, fixtures, configuration, commit messages, or the policy excerpt.
- **Security:** never embed credentials, API keys, or connection strings in code, comments, tests, or log output. The `DATABASE_URL` is loaded from environment variables only. `.env` and `.env.*` are already in `.gitignore`.
- **Externalised prompts:** Phase 1 doesn't introduce LLM prompts (no LLM calls happen yet), but the directory structure (`backend/app/prompts/system/`, `backend/app/prompts/user/`) should be in place ready for Phase 2 if it isn't already.
- **Interface stability:** the audit vault row contract, the chain hash formula, and the policy chunk schema are interfaces that downstream phases depend on. Once landed, they are stable. Flag if any later realisation forces a change.

### Preamble fix-up — before any other Phase 1 work

Update `docs/architecture-stack-reference.md` to reflect the actual prototype data layer. The doc currently has multiple references to "PostgreSQL on Render" or "Render-managed Postgres" for the prototype side; replace with "Neon (managed Postgres) — `eu-central-1` / Frankfurt; pgvector 0.8.0 enabled". The production-side wording (Azure SQL Managed Instance) is unchanged. Make the change, but do not commit it as a standalone step — it lands in the same Phase 1 commit as the rest of the work.

### Database connection — when to ask for the URL

The Neon `DATABASE_URL` is in my password manager. After I approve the plan, ask me explicitly:

> "Ready to execute. Please paste the Neon DATABASE_URL into the chat — I will use it to (a) populate a local `.env` file for development (gitignored), (b) run the initial migration locally, and (c) instruct you to set it as an environment variable on Render for the deployed backend. I will not commit it to the repository or log it."

Wait for the URL before proceeding. Once you have it, write it to a local `.env` file (which `.gitignore` excludes), use it to run migrations against Neon, and tell me to add it as `DATABASE_URL` on Render's Environment tab.

## Step 4 — Log

When the code work is complete, append a new entry to `docs/build-log.md` following the entry format documented at the top of that file. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/02-phase-1-data-layer.md`.
- Plan (approved): link to `docs/prompts/02-phase-1-data-layer-plan.md`.
- Plan iterations: count of rejected revisions, if any. List the rejected files inline.
- Report: link to `docs/prompts/02-phase-1-data-layer-report.md`.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate. Include the breakdown (audit chain tests, settings tests, schema tests, indexing tests, seed-generator tests).
- Issues discovered.
- Next: Phase 2 — LLM Gateway and Validator agent.

## Step 5 — Write the report

Save the report to `docs/prompts/02-phase-1-data-layer-report.md`. The report opens with a `## Summary` block containing, in this order:

- **Recap** — one sentence stating what's done plus one sentence stating what comes next. The five-second elevator pitch.
- **Completed at** — ISO 8601 UTC timestamp at the moment of report-writing.
- **Phase** — `1 — Data layer and settings infrastructure`.
- **Status** — Complete / Complete with deferrals.
- Links to the prompt, the approved plan, and the repository.
- CI status if relevant.

Body sections cover files created and modified by tier, test counts and pass rates, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement (typically: setting `DATABASE_URL` on Render).

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 1:

- Date: today's date in ISO format.
- Phase: "Phase 1 complete; Phase 2 next".
- What works: a one-line summary of the data layer (e.g. "Database schema, settings infrastructure, audit chain with defensive guards, indexed policy excerpt, synthetic claim seeds. All persistent state in place; no agents yet.").
- What's next: "Phase 2 — LLM Gateway and Validator agent."

## Step 7 — Git

Make a single commit covering all the Phase 1 work, with the commit message:

```
Phase 1: data layer and settings infrastructure

- Database schema (claims, audit_log, policy_chunks) with migrations
- Settings sub-models (Database, LLM, Embedding, Langfuse, Escalation)
- Audit chain with SHA-256 row + chain hashes; defensive guards throughout
- Sample commercial property policy excerpt indexed via bge-small-en-v1.5
- Synthetic claim generator covering the three demo scenarios
- Postgres+pgvector service container in CI
- README, architecture-stack-reference updated for Neon
- Approved plan archived; build log entry appended; report written
- CLAUDE.md Current Status updated
```

Push to `main` so Render auto-deploys the new code.

## Step 8 — Report back

Per the global "After coding" section, report:

- Files created and modified.
- Test count and pass rate, with breakdown.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend for follow-on work.

End the report with the action items I still need to handle:

- Set `DATABASE_URL` on Render's Environment tab to the Neon connection string (the value I supplied to you in chat). Render will auto-redeploy after the env var change. Confirm the deploy goes Live without errors.
- Verify the deployed backend can reach Neon (a small test endpoint or just the Render service logs showing successful database connection at startup).
