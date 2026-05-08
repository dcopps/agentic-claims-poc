# Report 01 — Phase 0: Repository Scaffold

## Summary

- **Recap:** Phase 0 of the agentic-claims-poc build is complete and pushed to `dcopps/agentic-claims-poc` with CI green. Next: provision the Render Web Service (via the committed `render.yaml` blueprint) and the Vercel project so deployments go live.
- **Completed at:** ~2026-05-08T12:30:00Z (approximate — the report file was added retrospectively after the four-artefact convention was introduced; the precise completion timestamp was not captured at the time. Future phase reports record `Completed at` as a precise ISO 8601 UTC timestamp at the moment of report-writing.)
- **Phase:** 0 — Repository scaffold
- **Status:** Complete (local + CI). Live deployments to Render and Vercel are in the architect's hands and not yet stood up.
- **Prompt:** [`01-phase-0-repository-scaffold.md`](01-phase-0-repository-scaffold.md)
- **Plan (approved):** [`01-phase-0-repository-scaffold-plan.md`](01-phase-0-repository-scaffold-plan.md) — approved 2026-05-08T11:50:06Z, no rejected iterations.
- **Repository:** [https://github.com/dcopps/agentic-claims-poc](https://github.com/dcopps/agentic-claims-poc) — public, `main` set up to track `origin/main`.
- **CI:** Both jobs green (run 25554956879 on the first push to main).

## Files created and modified

### Backend (top-level uv project)

- `pyproject.toml`, `uv.lock` — Python 3.11+. Runtime deps: FastAPI, Uvicorn, Pydantic, Pydantic-Settings, PyYAML. Dev deps: pytest, httpx, ruff, mypy, types-pyyaml. Ruff + mypy + pytest config inline.
- `backend/__init__.py`, `backend/app/__init__.py`, `backend/app/api/__init__.py`, `backend/tests/__init__.py`, `backend/data/.gitkeep`.
- `backend/settings.py` — Pydantic Settings model with defensive YAML overlay loader.
- `backend/settings.yaml.template` — matching template.
- `backend/app/main.py` — `create_app()` factory plus CORS middleware.
- `backend/app/api/health.py` — `/health` route mounted at root; version field read via `importlib.metadata.version("agentic-claims-poc")`.
- `backend/tests/conftest.py`, `backend/tests/test_health.py`, `backend/tests/test_settings.py` — defaults + 5 YAML-loader guard tests.

### Frontend (Vite + React 19 + TypeScript)

- `frontend/package.json`, `frontend/package-lock.json` — regenerated post-CI to fix a Linux-x64 platform-gap on the macOS-generated lockfile.
- `frontend/vite.config.ts` — Vite + Tailwind plugin + dev proxy + Vitest config.
- `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/App.test.tsx`, `frontend/src/index.css` (`@import "tailwindcss"`), `frontend/src/setupTests.ts`.
- `frontend/index.html` — title set, default favicon link removed.
- `frontend/.prettierrc`, `frontend/.env.example`.
- Removed Vite default cruft: `App.css`, `src/assets/`, `public/`.

### Tooling and infrastructure

- `.gitignore`, `.editorconfig`.
- `render.yaml` — Render Blueprint declaring a free-tier Web Service. Build command `uv sync`; start command `uv run uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`; health-check path `/health`; auto-deploy on push to `main`. Postgres database declaration deferred to Phase 1.
- `infra/.gitkeep`, `scripts/setup-dev-db.sh` (executable, follows the sanitise → validate → abort → execute pattern).
- `.github/workflows/ci.yml` — two jobs: backend (ruff + mypy + pytest), frontend (eslint + tsc + vitest).

### Documentation

- `README.md` — added "Local development" section with Postgres 17 install instructions, dev-db script invocation, run/test commands.
- `CLAUDE.md` — "Current Status" updated to "Phase 0 complete; Phase 1 next".
- `docs/build-log.md` — Phase 0 entry appended.
- `docs/prompts/01-phase-0-repository-scaffold-plan.md` — Approval footer appended at end of file.

## Tests

- **Backend: 7 passing, 0 failing.**
  - `test_health.py` — 1 test (GET /health returns 200 with the expected JSON shape).
  - `test_settings.py` — 6 tests: defaults, missing file, empty file, malformed YAML, non-mapping YAML, directory-not-file.
- **Frontend: 2 passing, 0 failing.**
  - `App.test.tsx` — App renders heading; backend status reads "ok" on a 200 response.
- **CI on `main`:** both jobs green (run 25554956879).

## Deviations from spec

Four deviations during execution. Each is recorded so the audit trail explains why what shipped differs from what the plan stated.

### 1. `postgresql@16` → `postgresql@17`

Amendment A in the approval message specified `postgresql@16`. Homebrew's `pgvector` bottle currently ships extension files only for `postgresql@17` and `postgresql@18` — there is no pre-built bottle for `@16`, so `CREATE EXTENSION vector` against `@16` would fail.

Stopped per the amendment ("if Homebrew install or pgvector setup fails, stop and report"), surfaced the issue, and switched to `postgresql@17` after architect confirmation. `CLAUDE.md` and `BUILD-PLAN.md` retain the "Postgres 16+" wording (still accurate; 17 satisfies the minimum). The `README.md` Local development section pins to 17 explicitly with a brief note about the bottle limitation.

### 2. `gh repo create … --push` failed initially

The user's `gh` token had `repo` scope but not `workflow`. GitHub blocks creating workflow files (`.github/workflows/ci.yml`) without the `workflow` scope. Asked the architect to run `gh auth refresh -s workflow` and retried; push succeeded on the second attempt.

### 3. Frontend lockfile platform-gap on first CI

The first generated `package-lock.json` came from macOS arm64 and was missing the `emnapi` and related entries needed for Linux x64 (the CI runner platform). First CI run failed with `npm ci` errors. Resolved by removing `node_modules/` and `package-lock.json`, re-running `npm install`, committing the regenerated lockfile. CI green on the second run.

### 4. Tailwind v3 layout → Tailwind v4 layout

The plan listed `tailwind.config.js` and `postcss.config.js`. Tailwind v4 (current as of early 2025) does not require either of these — it uses the `@tailwindcss/vite` plugin and a single `@import "tailwindcss"` line in the entry CSS. The plan reflected an older mental model.

Used the v4 path (modern default). The architect confirmed this was the right call after the report was reviewed.

## Guard clauses added

All from the plan; no surprises. Triggering tests for each guard live in `backend/tests/test_settings.py`.

- `_load_yaml_overrides` aborts on: missing file (returns empty dict; documented as "no overlay"), file is a directory, oversize file (>256KB), malformed YAML, non-mapping YAML.
- `scripts/setup-dev-db.sh` aborts on: `psql` not on PATH, server unreachable, version below 16, pgvector unavailable, malformed `DEV_DB_NAME` shape.
- `/health` version field returns the sentinel `"unknown"` (not silent fallback) when the package isn't installed, surfacing the misconfiguration.

## Optional enhancements recommended for Phase 1+

1. **Tighter version pinning.** The scaffold currently allows caret ranges (e.g. `vite ^8.0.10`). A small fix-up commit could replace carets with tildes or exact versions for more deterministic CI. Low priority.
2. **`npm audit` and `pip-audit` (or `uv-secure`) in CI.** Cheap insurance for the regulator-ready posture story; useful before more dependencies arrive in Phase 2. Recommended to fold into Phase 1 alongside the Postgres service container.
3. **Pre-commit hooks** (still optional from the plan) — ruff, prettier, and a "no client name" grep would catch issues before CI churns minutes. Defer to Phase 7 polish or skip.

## Outstanding items requiring architect involvement

The repository is on GitHub and CI is green. The remaining items are deployment-side actions in third-party consoles only the architect can drive.

1. **Render Web Service.** Visit `https://dashboard.render.com/blueprints`, click "New Blueprint Instance", point at `dcopps/agentic-claims-poc`. The committed `render.yaml` will auto-provision a free-tier `agentic-claims-poc-backend` with autodeploy on `main`. Once it's up, send the URL to confirm `/health` returns `{"status":"ok","version":"0.0.1"}` from production.
2. **Render Postgres database** (or Neon as an alternative). Provision separately on the free tier; capture the `DATABASE_URL`. Phase 1 wires it in.
3. **Vercel project.** Import `dcopps/agentic-claims-poc`, root directory `frontend`, Vite preset (build command `npm run build`, output `dist`). Add `VITE_API_BASE_URL` env var pointing at the Render service URL once Render is up.
4. **CORS update.** Add the Vercel URL to the backend's `cors_allowed_origins` once Vercel is up. Either via env var override (`CORS_ALLOWED_ORIGINS`) or by updating `settings.yaml.template`'s default. Small fix-up commit before Phase 1 starts.

The "deployed live" leg of Phase 0's definition of done lands when (1)–(3) are up. Phase 1 is ready to start once the deployments are confirmed and CORS is updated.
