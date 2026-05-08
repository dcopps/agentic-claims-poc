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
