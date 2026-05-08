# Prompt 01 — Phase 0: Repository Scaffold

## Read first

Before doing anything else, read these two files in this directory:

- `CLAUDE.md` — global standards reference, project overview, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 0 of that plan.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. The relevant items for this prompt: plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts (no inline f-strings), interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 0 of `BUILD-PLAN.md` — Repository scaffold. The definition of done is in the build plan; meet it.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering:

- Files and directories you will create.
- Tools and libraries you will introduce, with rationale where the choice is not already locked in `CLAUDE.md` or `BUILD-PLAN.md`.
- Any new dependency — flag each one and state why the existing stack cannot cover it; wait for confirmation before adding it.
- Risks and downstream impacts, especially anything that could affect Phase 1 onward.
- Any deployment steps that require my involvement (Render account, Vercel account, GitHub remote, environment variables) — list these explicitly so I can do them in parallel with your work.
- Any optional enhancements you would recommend, clearly labelled as optional. Deliver the spec first; suggestions go in the plan, never silently in the code.

Save the plan **before** asking me to review it, so I can read it in my editor. Write it to:

```
docs/prompts/01-phase-0-repository-scaffold-plan.md
```

The file must be a clean, self-contained Markdown document — no chat artefacts, no "here is my plan" preamble. Top-level heading: `# Plan 01 — Phase 0: Repository Scaffold`. Below that, the body of the plan in the same shape it was produced.

After saving the file, point me at it and ask for my verdict. Do not write any other code or modify any other files yet.

## Step 2 — Approval or rejection

I will respond with one of two outcomes.

**If I approve** (any reply along the lines of "yes", "go ahead", "approved", or similar):

Append a horizontal rule and an `## Approval` section to the plan file with these fields:

- `**Approved by:** Dermot Copps`
- `**Approved at:** <ISO 8601 timestamp in UTC, e.g. 2026-05-07T14:32:18Z>`
- `**Approval message:** "<my exact approval message, quoted>"`

Then proceed to Step 3.

**If I reject** (any reply that is not unambiguous approval — including detailed feedback, a counter-proposal, or a request for changes):

Treat the current plan as rejected. Even if my feedback is small, do not silently amend the canonical plan file. Instead:

1. Append a horizontal rule and a `## Rejection` section to the existing plan file with these fields:
   - `**Rejected at:** <ISO 8601 timestamp in UTC>`
   - `**Rejection reason:** <one to three sentence summary of my feedback, in your own words>`
   - `**Superseded by:** docs/prompts/01-phase-0-repository-scaffold-plan.md (next iteration)`
2. Rename the rejected file from `01-phase-0-repository-scaffold-plan.md` to `01-phase-0-repository-scaffold-plan-rejected-NN.md`, where `NN` is the next available two-digit iteration number — `01` for the first rejection, `02` for the second, and so on.
3. Produce a revised plan and save it freshly as `docs/prompts/01-phase-0-repository-scaffold-plan.md`.
4. Return to Step 2 (await my verdict on the new version).

Iterate as needed. The canonical `01-phase-0-repository-scaffold-plan.md` file is the working plan. Rejected versions accumulate as numbered siblings, each with its own `## Rejection` footer and pointing forward to its successor.

Only after the canonical plan file carries an `## Approval` footer should you proceed to Step 3.

## Step 3 — Execute

After the plan is approved, execute Phase 0 per `BUILD-PLAN.md`. Constraints from `CLAUDE.md` apply throughout:

- `uv` is the Python package manager. Use `uv init` and `uv add` for the backend project.
- React + Vite + TypeScript + Tailwind for the frontend.
- **Local dev database is native Postgres on macOS** — Postgres.app or Homebrew Postgres 16+ with pgvector. No Docker, no docker-compose. The `scripts/setup-dev-db.sh` script (or equivalent) creates the development database, enables the pgvector extension, and prepares it for migrations in Phase 1. The README documents the install steps for the developer (link to Postgres.app, or `brew install postgresql@16` plus pgvector).
- Defensive programming pattern (sanitise → validate → abort → execute) is the default for any function that takes input.
- Function size: 30 lines is a prompt to reconsider; 50 lines is a hard limit.
- No hardcoded values. Settings hierarchy: defaults in `backend/settings.py` and a matching `backend/settings.yaml.template`. The initial `Settings` Pydantic model is fine for Phase 0; sub-models for database, LLM providers, embeddings, observability, and escalation populate in Phase 1.
- Type hints on every function signature.
- Anonymisation: the client name does not appear anywhere in code, comments, tests, fixtures, configuration, or commit messages.
- `.gitignore` must exclude `BUILD-PLAN.md`, `HANDOFF.md`, `.env`, `.env.*`, secrets, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `node_modules/`, `dist/`, `build/`, local database dumps, and any `output/` directory.

## Step 4 — Log

When the code work is complete, append a new entry to `docs/build-log.md`. Follow the entry format documented at the top of that file. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/01-phase-0-repository-scaffold.md`.
- Plan (approved): link to `docs/prompts/01-phase-0-repository-scaffold-plan.md`.
- Plan iterations: count of rejected revisions, if any (e.g. "1 rejected before approval"). List the rejected files inline.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate. Phase 0 establishes the test scaffolding; even if no functional tests exist yet, note the test runner is wired into CI and a single placeholder test passes.
- Issues discovered.
- Next: Phase 1 — Data layer and settings infrastructure.

## Step 5 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 0:

- Date: today's date in ISO format.
- Phase: "Phase 0 complete; Phase 1 next".
- What works: "Hello-world deployed; CI runs on PRs."
- What's next: "Phase 1 — Data layer and settings infrastructure."

## Step 6 — Git

Initialise a git repository in this directory if it is not already one. Make an initial commit covering all the Phase 0 work, with the commit message:

```
Phase 0: repository scaffold

- uv-managed Python backend with FastAPI + /health endpoint
- React + Vite + TypeScript + Tailwind frontend
- Initial Settings model and settings.yaml.template
- Native local Postgres + pgvector setup script (Postgres.app or Homebrew; no Docker)
- GitHub Actions CI for backend (ruff, mypy, pytest) and frontend (eslint, tsc, tests)
- Standard tooling configs (.gitignore, .editorconfig, pyproject.toml, package.json, tsconfig.json)
- Approved plan archived (with any rejected iterations preserved)
- Build log opened with Phase 0 entry; CLAUDE.md status updated
```

Do not push yet. I will create the GitHub remote afterwards and provide the URL.

## Step 7 — Report back

Per the global "After coding" section, report:

- Files created and modified.
- Test count and pass rate.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend for follow-on work.

End the report by listing the deployment steps that require my involvement and that I should do in parallel — typically: creating the GitHub repository, creating the Render service, creating the Vercel project, supplying any environment variables, and confirming Postgres 16+ with pgvector is installed locally on the developer machine.
