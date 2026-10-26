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
- Two deployment targets from one repository (since Phase 9.1, 1 October 2026):
  - **Render / Vercel / Neon (canonical for demos):** Backend on Render; frontend on Vercel; Postgres on Neon (managed Postgres) — `eu-central-1` / Frankfurt, Postgres 17, pgvector 0.8.0.
  - **Azure (Phase 9):** backend on Azure Container Apps (consumption, 1 vCPU / 2 GiB) from an image built with `az acr build` into Azure Container Registry; Azure Database for PostgreSQL Flexible Server 17 (Burstable B1ms, pgvector 0.8) in North Europe; secrets in Key Vault read by a user-assigned managed identity; frontend on Azure Static Web Apps (Free; the resource is in East US 2 because the service is not offered in North Europe and West Europe refused new customers — it holds only the static bundle); Application Insights (workspace-based) fed by the Azure Monitor OpenTelemetry distro; everything provisioned by Bicep in `infra/bicep/`. Operated by `scripts/azure-deploy.sh`, `azure-start.sh`, `azure-stop.sh`.
- CI: GitHub Actions (Azure DevOps Pipelines is the production target — config in `infra/azure-devops-pipeline.yml` for reference, GitHub Actions actually runs the prototype). CI's Postgres service image is `pgvector/pgvector:pg17`, matching both deployed databases. **Deploy on push (Phase 9.2):** `deploy-backend.yml` and `deploy-frontend.yml` trigger on `workflow_run` of `CI` on `main`; the backend authenticates by OIDC on a dedicated managed identity (no stored Azure credential), builds in ACR and updates the Container App only when the backend paths differ from the deployed image's commit; the frontend builds with `VITE_API_BASE_URL` from a repository variable and uploads with the Static Web App's token (the one GitHub secret). Infrastructure is still deployed from a developer shell with Bicep.

## Project Structure (target — fully populated by end of Phase 0)

```
agentic-claims-poc/
├── README.md
├── CLAUDE.md
├── BUILD-PLAN.md                  # local only — not committed
├── HANDOFF.md                     # local only — not committed
├── pyproject.toml                 # uv project config (torch pinned to the CPU index on Linux)
├── uv.lock                        # uv lockfile
├── Dockerfile                     # backend image for Azure Container Apps (model baked in)
├── .dockerignore                  # allow-list build context
├── .editorconfig
├── .gitignore
├── .github/
│   └── workflows/
│       ├── ci.yml                 # lint, type-check, test
│       ├── deploy-backend.yml     # Phase 9.2: OIDC → az acr build → az containerapp update, on green CI
│       └── deploy-frontend.yml    # Phase 9.2: build → Static Web Apps upload, on green CI
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── public/
│   │   └── staticwebapp.config.json   # Phase 9.2: SPA navigationFallback for Static Web Apps
│   ├── vercel.json                # Phase 9.2: SPA rewrite for Vercel
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
│   │   ├── telemetry.py           # Phase 9.2: Application Insights export, no-op without a connection string
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
│   ├── setup-dev-db.sh            # one-time local Postgres + pgvector setup
│   ├── verify-demo-scenarios.py   # three-scenario check against a deployed backend
│   ├── azure-common.sh            # shared helpers (sourced)
│   ├── azure-deploy.sh            # what-if | deploy [image] | build
│   ├── azure-start.sh             # Postgres start + 1 warm replica
│   └── azure-stop.sh              # minReplicas 0 + Postgres stop
├── docs/
│   ├── architecture-stack-reference.md
│   ├── BACKLOG.md                 # pending + future work; completed work goes to build-log.md
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
    ├── azure-devops-pipeline.yml  # production CI/CD reference
    └── bicep/                     # Phase 9.1 + 9.2: main.bicep, main.bicepparam, modules/ (nine), README.md
```

## Build Approach

Phases are defined in `BUILD-PLAN.md` (kept locally; not committed). The build is plan-first — each phase prompt opens by producing a written plan, waits for confirmation, then executes. This follows the global plan-first standard at `~/.claude/CLAUDE.md`.

Every phase ends with two appends:

- A new entry to `docs/build-log.md` describing what was built, test counts, and any issues.
- The phase's prompt saved verbatim to `docs/prompts/NN-descriptive-name.md`.

Together these make the build reproducible end-to-end.

## Current Status

- **Date:** 2026-10-26
- **Phase:** Phase 9.2 — **complete (26 October 2026).** Deployed, self-deploying on push, telemetry verified, second verification pass **passed for the deployment with one recorded exception** (Harborline auto-approve ends `awaiting_human` — a Guardrail model-behaviour change, see *Demo status*). Report `docs/prompts/20-…-report.md`; build-log entry *Phase 9.2*. Live: image `claims-backend:2b662da` on revision `--0000006`. Plan `docs/prompts/20-…-plan.md` approved 26 October 2026 (decisions recorded in its *Approval* section). Version `0.9.1` in `pyproject.toml`. Built: three new Bicep modules (`deployer-identity`, `staticwebapp`, `appinsights`) plus edits to `acr`, `containerapps`, `main`, `main.bicepparam`; `frontend/public/staticwebapp.config.json`, `frontend/vercel.json`; `.github/workflows/deploy-backend.yml`, `deploy-frontend.yml`; `backend/app/telemetry.py` + `TelemetrySettings` + the `APPLICATIONINSIGHTS_CONNECTION_STRING` alias; `azure-common.sh` gains `wait_for_health_version`, `require_active_image`, `wait_for_zero_replicas`; `azure-stop.sh` waits for the replica to drain; `azure-deploy.sh` defaults to the live image. Suite **381 passed, 0 failed, 7 skipped** (+6); `ruff`, `mypy`, Bicep build + lint, `bash -n`, frontend lint / typecheck / build / 36 tests all clean. **Done 26 October 2026:** `Microsoft.Web` + `Microsoft.Insights` registered; what-if matched plan §2c (4 create, 1 real modify, 5 unsupported; two extra env entries `OTEL_SERVICE_NAME` / `OTEL_PYTHON_EXCLUDED_URLS` are the approved §6 design; no probe-order line because the Bicep already matches the live order); deploy `claimsai-dev-b820d96-20261026T162838Z` succeeded — Static Web App `delightful-beach-009db650f.5.azurestaticapps.net`, deployer client id in the `AZURE_CLIENT_ID` repository variable, revision `--0000003` still on image `967a348`; the seven repository variables and `AZURE_STATIC_WEB_APPS_API_TOKEN` set; `b820d96` pushed — CI red (see *CI on `main`*), both deploys skipped by the gate. `3abad04` (npm 10 lockfile) pushed: CI **green**; frontend deploy green (Static Web App serves 200 on `/` and on a deep link; bundle bakes the Azure backend URL); backend deploy **red at *Verify the rollout* although the rollout succeeded** — revision `--0000004` healthy, 100 % traffic, image `claims-backend:3abad04`, `/health` `0.9.1` (13 s from container start), `wait_for_health_version` passed after 3 attempts. Cause: `require_active_image` read `[latestRevisionName, latestReadyRevisionName]` with `-o tsv`, which prints one element per line, so `read` saw `ready` as empty and the check could never pass. Fixed with a `join(' ', …)` query; verified from the shell against the live app (exit 0 for `3abad04`, exit 1 with the expected message for `967a348`). The workflow path is not re-exercised by this push (`scripts/` is outside `BACKEND_PATHS`, so the run reports nothing to deploy); the first real backend change proves it end to end. **FastAPI request telemetry fix:** App Insights received no requests because `main.py` bound `FastAPI` with `from fastapi import FastAPI` at import, before the distro rebinds `fastapi.FastAPI` to its instrumented subclass, so `create_app` built the uninstrumented class. `create_app` now constructs `fastapi.FastAPI(...)` looked up at call time; regression test `test_create_app_builds_the_class_the_distro_installs` (verified to fail on the old binding); `main.py` and `telemetry.py` comments corrected. Suite **382 passed, 0 failed, 7 skipped** (+1). This push is the first backend change through the corrected *Verify the rollout* step. **Closed out 26 October 2026:** backend deploy of `2b662da` green end to end (first real run of the corrected verify step); App Insights shows requests with Postgres and `api.anthropic.com` dependencies as children, `/health` excluded; idempotence what-if 0 creates, no real changes (`6 modify / 14 no change / 5 unsupported / 1 ignore`, all known categories plus new server-populated lines on App Insights and the Static Web App); pass two through the UI recorded (chain `ok` over 49 rows, 16 claims); cold start **not measured** (backlog); `Managed Identity Operator` not needed; `azure-stop.sh` run as the last act after the docs commit — **check its state first next session**.
- **Found during 9.2 planning (26 October 2026):** CI on `main` had been red since 15 June (frontend lockfile; `dcc52bd` did not fix it — see *CI on `main`*). `Microsoft.Web` and `Microsoft.Insights` were unregistered. Static Web Apps is not offered in North Europe and **West Europe refused the resource** ("region is currently not accepting new customers"); `staticWebAppLocation` is `eastus2`, which a read-only what-if accepted. Postgres was `Ready`, not stopped: Azure restarts a stopped Flexible Server after seven days. The subscription has been Pay-As-You-Go since 1 October, so the 30 October credit expiry disables nothing.
- **Read-only what-if of the 9.2 delta (26 October 2026, `eastus2`):** 4 creates (deployer identity, its federated credential, the Static Web App, Application Insights); 1 real modify (the Container App: env + probe order); the 9.1 noise categories 2 and 3 on Postgres, the environment and the registry; 5 unsupported role assignments (was 2). Matches the plan's §2c.
- **Dependency note (9.2):** `uv add` moved `mistralai` 2.4.5 → 2.10.1 (2.4.5 capped `opentelemetry-semantic-conventions` below what the distro needs); the first resolution jumped to 3.5.0 and was rejected with `mistralai>=1.5,<3`. The distro bundles the `httpx` instrumentation, so only two packages were added, not the plan's three.
- **Phase 9.1 (1 October 2026) — complete.** Plan `docs/prompts/19-…-plan.md`; report `docs/prompts/19-…-report.md`; build-log entry *Phase 9.1*.
- **Azure deployment (1 October 2026):** `https://ca-claimsai-dev-backend.victorioushill-60f56bb8.northeurope.azurecontainerapps.io`, resource group `rg-claimsai-dev`, image `claims-backend:967a348`. Resources: `id-claimsai-dev-backend`, `log-claimsai-dev`, `psql-claimsai-dev-ojemo` (Postgres 17.11, pgvector 0.8.2), `acrclaimsaidevojemo`, `kv-claimsai-dev-ojemo`, `cae-claimsai-dev`, `ca-claimsai-dev-backend`; 9.2 adds `id-claimsai-dev-deployer`, `appi-claimsai-dev`, `swa-claimsai-dev`. **It is parked between sessions: `scripts/azure-stop.sh` is the last act of every Azure session, so run `scripts/azure-start.sh` first** (about 3 minutes; it leaves `minReplicas` at 1, which a later what-if reports as drift from the parameter file's 0). Azure restarts a stopped Postgres after seven days, so check its state. The Azure database holds 16 claims (9 seeded + 3 from pass one + 4 from pass two) and 49 audit rows. Frontend: `https://delightful-beach-009db650f.5.azurestaticapps.net`.
- **Azure verification — first pass of two (1 October), passed:** `settled` / `awaiting_human` (`settlement_over_ceiling`) / `awaiting_human` (`guardrail_failed`, `settlement_over_ceiling`); seven audit entries per run; chain `ok` over 21 rows; every LLM call `provider = "anthropic"` with `requested_model` = `model` = `claude-haiku-4-5-20251001`; the guardrail scenario's Adjuster is the demo fixture, as designed. Cold start 28.0 s from zero replicas. Run via `scripts/verify-demo-scenarios.py`, not the UI. **Pass two (26 October), through the Azure frontend:** passed for the deployment with the Harborline exception; CORS and the SSE stream proven from the Static Web App origin; details in the build log.
- **what-if never prints "No changes" for this template** — expect about four "modify" entries of noise in three categories (probe array order, unresolved `reference()` expressions, server-defaulted properties shown as deletions) plus 2 "unsupported" role assignments. The criterion is "no real changes, verified against live state"; the line-by-line list is in the build log. Anything outside those categories is a real change.
- **Step 0 facts (1 October 2026):** subscription `Azure subscription 1` (free trial, spending limit on, user is Owner); Bicep CLI 0.47.16 and the `containerapp` extension installed; providers `Microsoft.App`, `DBforPostgreSQL`, `ContainerRegistry`, `KeyVault`, `OperationalInsights`, `ManagedIdentity` registered; `Standard_B1ms` is offered in `northeurope` for Postgres 11–18, so no region fallback was needed.
- **What works (9.1, code and infra):** `infra/bicep/main.bicep` + six modules compile and lint with zero warnings; `main.bicepparam` reads every secret with `readEnvironmentVariable()`. The Container App is conditional on `containerImage` (pass 1 deploys everything but the app; no placeholder image). `Dockerfile` is two-stage, `uv`-based, non-root, bakes `bge-small-en-v1.5` under `HF_HOME=/opt/hf` with `HF_HUB_OFFLINE=1` at runtime, port fixed at 8000; `.dockerignore` is an allow-list. `torch==2.11.0` is now a direct dependency resolved from the PyTorch CPU index on Linux only (`uv.lock` lost all 36 `nvidia-*` and 6 `cuda-*` entries; macOS resolution proven unchanged by `uv export` diff). pytest guard extended: `_DEPLOYED_HOST_SUFFIXES = (".neon.tech", ".postgres.database.azure.com")`, two new discriminator tests. CI Postgres image pinned to `pg17`. Scripts pass `bash -n`; no function over 30 lines; `shellcheck` is not installed on this machine, so it was not run. Suite **375 passed, 0 failed, 7 skipped** (+2); `ruff` and `uv run mypy backend` clean.
- **Demo status: Render / Vercel / Neon, the three scripted scenarios only — but the $85k Harborline auto-approve currently does not settle, on either deployment.** Since at least 26 October the Guardrail's LLM check flags it (`guardrail_failed`); replaying pass one's byte-identical 1 October prompt to `claude-haiku-4-5-20251001` at temperature 0 now fails too, so the model's behaviour changed under an unchanged id. Fix before the next demo: `docs/BACKLOG.md` → *Findings from the 26 October 2026 verification* (Guardrail prompt + replay regression fixture; Adjuster temperature 0 for the scripted scenarios). Stay off the background claims (*Findings from the 21 September 2026 verification*).
- **CI on `main` (26 October 2026):** `frontend/package-lock.json` regenerated as the first commit of Phase 9.2. It had been out of sync with `package.json` since Phase 6 (15 June 2026), so every CI run since then failed at `npm ci` in the Frontend job; the Backend job was passing throughout. Phase 9.2's deploy workflows gate on CI, so this had to come first. **Correction:** `dcc52bd` was generated with npm 11 (Node 24), which omits the `@emnapi/core` / `@emnapi/runtime` entries that CI's npm 10 (Node 20) requires, so CI stayed red on that push and on `b820d96`. Regenerated with `npx npm@10 install --package-lock-only` (no version changes; adds the `@emnapi/*` entries and the `@tailwindcss/oxide-wasm32-wasi` nested deps, drops npm-11-only `"peer": true` markers) and verified under Node 20.20.2 / npm 10.9.9: `npm ci`, lint, typecheck, 36 tests, build. **Regenerate the lockfile with npm 10 (`npx npm@10 …`) until CI's Node version changes.**
- **Known debt:** three `_build_audit_payload` builders over the 50-line limit (backlog: *Split the oversized audit-payload builders*); `docs/prompts/README.md` index not maintained past prompt 04.
- **What's next:** the Harborline Guardrail fix (backlog, demo-visible, before any demo); then 9.3 (`0.9.2`) — Azure AI Foundry as a third LLM provider (prompt 21). Pass two met the condition for *considering* the Render / Neon retirement — an open decision in `docs/BACKLOG.md`. Phase 8.7 UI polish is queued after Phase 9.

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

- **Models.** Two layers, distinguished deliberately since Phase 8.6:
  - **Production target (unchanged):** Claude Sonnet (Orchestrator), Claude Haiku (Doc-Parser, Guardrail), Mistral Large (Validator, Adjuster). Adjuster gets a LoRA adapter in production; not in the prototype. `docs/architecture-stack-reference.md` and `diagrams/*.mmd` describe this target.
  - **Prototype default (from 15 September 2026, Phase 8.6):** all four agents on Anthropic — Claude Haiku for the Doc-Parser, Validator, Adjuster and Guardrail. Reason: Mistral withdrew Mistral Large from its Free tier (`403 tier_not_allowed` on both `mistral-large-latest` and the pinned `mistral-large-2512`); Dermot chose the Claude default over adding a Mistral payment method (14 September 2026).
  - **Mechanism:** each agent has a provider selector — `llm.doc_parser_provider`, `llm.validator_provider`, `llm.adjuster_provider`, `llm.guardrail_provider` (`anthropic` | `mistral`, default `anthropic`) — and resolves its model via `LLMSettings.model_for(agent)` from the selected provider block. The Mistral path is retained: `MistralProvider`, its tests, and the `mistral-large-2512` pin in `llm.mistral.*`. The **`v1_mistral` replay variant** routes the Validator and Adjuster back to Mistral; setting `LLM__VALIDATOR_PROVIDER=mistral` and `LLM__ADJUSTER_PROVIDER=mistral` makes it the default without a code change (see `docs/BACKLOG.md` → *Re-enable Mistral as default*).
  - **Verified combinations: only two** — all-Anthropic (the default) and Validator + Adjuster on Mistral (`v1_mistral`). Doc-Parser or Guardrail on Mistral is structurally possible (it requires `llm.mistral.<agent>_model`, which has no default; startup refuses the selector otherwise) but untested.
- **Database.** PostgreSQL with pgvector for the prototype. Single database hosts claims, audit log, vector index. Local dev uses native Postgres (Postgres.app or Homebrew) or, optionally, a Neon dev branch via `DATABASE_URL`; deployed dev/prod uses Neon (managed Postgres) in `eu-central-1` (Frankfurt). Production target: Azure SQL Managed Instance with Ledger Tables for audit.
- **Embedding model.** `BAAI/bge-small-en-v1.5` via `sentence-transformers`, runs on CPU inside the FastAPI process. Same model used for indexing the policy and for encoding query narratives — embedding model is a one-way door, never silently swap. Since Phase 9.1 `torch` is pinned to `2.11.0` on every platform (PyPI on macOS, the PyTorch CPU index on Linux) so the Mac that indexes the policy and the container that embeds queries run the same numerics; the Azure image bakes the model and runs with Hugging Face access off.
- **Streaming transport.** Server-Sent Events. The FastAPI endpoint pushes pipeline progress to the React frontend as agents complete.
- **Hosting.** Render (backend), Neon (Postgres), Vercel (frontend). Free tiers sufficient for the demo.
- **Phase 9.2 decisions (Dermot, 26 October 2026).** (1) **No Azure-written workflow files:** the Static Web App is created by Bicep with no repository link, and both deploy workflows are written and reviewed in this repository; the only manual step is pasting the app's deployment token into GitHub secrets. (2) **The backend workflow does not run Bicep:** infrastructure stays an operational act from a developer shell (`scripts/azure-deploy.sh`), because the parameter file reads its `@secure()` values from that shell; the workflow builds the image in ACR and points the existing Container App at it, under *AcrPush* + *Container Registry Tasks Contributor* on the registry and *Container Apps Contributor* on the app. (3) **OIDC via a second user-assigned managed identity** (`id-claimsai-dev-deployer`) with a federated credential for `repo:dcopps/agentic-claims-poc:ref:refs/heads/main`; no app registration, no client secret; the client, tenant and subscription ids live in repository variables as identifiers. The deployer and runtime identities have disjoint grants. (4) **Static Web App region:** not offered in North Europe; West Europe refused the resource on 26 October (not accepting new customers); `eastus2` is the one resource outside North Europe, holding only the static bundle. Also decided: telemetry via `azure-monitor-opentelemetry` + `opentelemetry-instrumentation-psycopg`, a no-op without `APPLICATIONINSIGHTS_CONNECTION_STRING`; `workflow_run` as the CI gate with diff-against-deployed for the backend and always-deploy for the frontend; `staticwebapp.config.json` in `frontend/public/`; one Bicep pass with CORS composed from the Static Web App output; `azure-deploy.sh` defaults to the live image; no reseed before the verification pass.
- **Two deployment targets (Phase 9.1, 1 October 2026).** The same repository, migrations and settings contract deploy to Render / Vercel / Neon **and** to Azure (Container Apps + Flexible Server + Key Vault + ACR, Bicep-provisioned, North Europe). **Render / Vercel / Neon is canonical for demos** until the Azure deployment has passed the full three-scenario verification twice; only then is retiring Render / Neon considered. Nothing on Render, Vercel or Neon is changed by Phase 9. The Azure specifics that are decisions, not defaults: user-assigned managed identity (a system-assigned identity cannot be referenced by the Key Vault secret refs in the same deployment pass); password auth for Postgres with the connection string in Key Vault (Entra auth deferred); public endpoints behind firewall rules (private endpoints are a documented gap); `minReplicas` 0 between demos, 1 during; the backend image is built with `az acr build`, never local Docker, and bakes the embedding model.
- **Decoupled architecture.** Claims are persisted to a claims-of-record table before any agent fires. The pipeline is triggered by a button click in the prototype (simulating the production Azure Service Bus event).
- **Demo content.** Commercial Property line. Three scripted scenarios: auto-approve $85,000 commercial water damage; threshold escalation $850,000 fire loss; guardrail escalation $1.4M with hallucinated endorsement.
- **Escalation policy.** OR semantics. Hard rules (always escalate): guardrail_failed, claim_type_watchlist, claimant_watchlist, cross_jurisdictional. Threshold rules: settlement > $250,000, validator confidence < 0.65, adjuster confidence < 0.75. Policy lives in `backend/app/escalation/policy.yaml`. Every decision logs which rules fired.
- **Local dev environment.** Native Postgres (Postgres.app or Homebrew), no Docker. Chosen to keep the local footprint small and avoid virtualisation overhead. **Two databases:** `agentic_claims_dev` runs the app (via `DATABASE_URL`); `agentic_claims_test` runs pytest (via `TEST_DATABASE_URL` in `.env.test`). The two are kept separate because the test suite's fixtures TRUNCATE tables — the test fixtures resolve `TEST_DATABASE_URL` in preference to `DATABASE_URL` and **categorically refuse to run against any deployed-database host — `*.neon.tech` (Phase 8.5, after a Phase 8.4 incident where a pytest run against a Neon-pointing `.env` wiped the deployed database) and `*.postgres.database.azure.com` (Phase 9.1)**. CI needs no `TEST_DATABASE_URL`: its `DATABASE_URL` is a localhost service container, which the non-deployed fallback accepts.

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
- **All four agents' audit payloads** (`doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`) gain `llm_call.requested_model: str` — Phase 8.5.3. The model identifier the agent passed to `provider.complete(model=…)` (the resolved settings value at call time, including any variant override — a `v2_haiku_validator` run records the Haiku id), recorded on success, parse-failure and provider-exception paths alike, so a failed call still records what was asked for. `model` remains the *responding* model from the response; a mismatch between the two is diagnostic. Additive; nested under the existing `llm_call` block, all existing keys unchanged. Absent when no call was attempted: the Adjuster demo-fixture path emits no `requested_model`, the same rule as `prompt`. Implemented via `_shared.CapturedRequest` / `attach_request`, so the recorded value is the sent value by construction.
- **All four agents' audit `llm_call.provider`** reports the *actual* provider the agent holds (`self._provider.vendor`), not a hardcoded vendor — Phase 8.6. Extends the Phase 5 Validator-only rule to `doc_extract`, `settlement_estimate` and `output_check`, because every agent's provider is now a settings choice. Value change only, no shape change: before this, the Adjuster hardcoded `"mistral"`, which would have mislabelled every Haiku-backed settlement; on the default wiring `doc_extract` / `output_check` values are unchanged (`anthropic`). The Adjuster demo-fixture path still records `"demo_fixture"`.

## Repository Name

`agentic-claims-poc`. Do not rename. Do not introduce client-specific naming.

## What goes in the repo vs what stays out

In the repo (publicly committable):

- `README.md`, `CLAUDE.md`
- `frontend/`, `backend/`, `infra/`, `scripts/`
- `docs/architecture-stack-reference.md`, `docs/BACKLOG.md`, `docs/change-governance.md`, `docs/dora-third-party-register.md`, `docs/design-decisions.md`, `docs/build-log.md`, `docs/prompts/`
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
