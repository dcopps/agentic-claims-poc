# Phase 9.2 — Report: frontend on Static Web Apps, deploy on push, Application Insights, second verification pass

Prompt: [`20-phase-9.2-static-web-apps-oidc-deploy-app-insights.md`](20-phase-9.2-static-web-apps-oidc-deploy-app-insights.md) · Plan: [`20-…-plan.md`](20-phase-9.2-static-web-apps-oidc-deploy-app-insights-plan.md) · 26 October 2026 · `0.9.0 → 0.9.1`

## Summary

The Azure deployment is complete and deploys itself. The frontend runs on Azure Static Web Apps. A push to `main` that passes CI deploys both tiers: the backend by OIDC on a dedicated managed identity with no stored Azure credential, the frontend by the Static Web App's token. Application Insights records requests with their Postgres and Anthropic dependencies attached. The **second three-scenario verification pass**, run through the Azure frontend, **passed for the deployment**, which proves CORS and the SSE stream from the Static Web App origin. Its one deviation is recorded as an exception: the $85k Harborline auto-approve scenario ended `awaiting_human` on `guardrail_failed`, because the Guardrail model's verdict on byte-identical input changed between 1 and 26 October under an unchanged model id. The images are not the cause. The condition for *considering* the Render / Neon retirement is met; the decision is open.

Three defects surfaced during the deployment, and all three are fixed: the npm 11 lockfile kept CI red, the rollout check could never pass, and FastAPI requests never reached Application Insights.

## Resources added (Bicep, one pass)

| Resource | Name | Notes |
|---|---|---|
| User-assigned managed identity + federated credential | `id-claimsai-dev-deployer`, `github-main` | Subject `repo:dcopps/agentic-claims-poc:ref:refs/heads/main`; no app registration, no secret |
| Static Web App (Free) | `swa-claimsai-dev` → `delightful-beach-009db650f.5.azurestaticapps.net` | East US 2: not offered in North Europe, and West Europe refused new customers |
| Application Insights (workspace-based) | `appi-claimsai-dev` | On `log-claimsai-dev` |

RBAC added: the deployer holds *AcrPush* and *Container Registry Tasks Contributor* on the registry and *Container Apps Contributor* on the app. **`Managed Identity Operator` was not needed.** The deployer and runtime identities hold disjoint grants.

## Files

| Commit | Files | Change |
|---|---|---|
| `b820d96` | `infra/bicep/` (3 new modules, 4 edited, README), `.github/workflows/deploy-{backend,frontend}.yml`, `frontend/public/staticwebapp.config.json`, `frontend/vercel.json`, `backend/app/telemetry.py`, `backend/app/main.py`, `backend/settings.py`, `settings.yaml.template`, tests, `scripts/azure-{common,deploy,stop}.sh`, `pyproject.toml`, `uv.lock`, docs | The phase's code (detailed in the build log) |
| `dcc52bd`, `3abad04` | `frontend/package-lock.json` | CI red since 15 June; second regeneration with npm 10 to match CI |
| `8d211ad` | `scripts/azure-common.sh` | `require_active_image` reads both revision names on one line |
| `2b662da` | `backend/app/main.py`, `backend/app/telemetry.py`, `backend/tests/test_telemetry.py` | App built from `fastapi.FastAPI` looked up at call time; regression test |
| this commit | `docs/build-log.md`, `docs/BACKLOG.md`, `docs/change-governance.md`, `docs/dora-third-party-register.md`, `README.md`, `CLAUDE.md`, this report | Deployment, verification and exception recorded |

**Interface changes:** none beyond the plan. **Dependencies:** `azure-monitor-opentelemetry` and `opentelemetry-instrumentation-psycopg`, as approved. `mistralai` moved 2.4.5 → 2.10.1, held below 3.

## Tests

**382 passed, 0 failed, 7 skipped** (375 at the end of 9.1 → 381 at `b820d96` → 382 at `2b662da`). `ruff check .` and `uv run mypy backend` are clean. Frontend: lint, typecheck, build and 36 tests pass under Node 20 / npm 10. Discriminator proof for the new telemetry test: with `from fastapi import FastAPI` reintroduced in `create_app`, `test_create_app_builds_the_class_the_distro_installs` fails, and it passes with the fix.

## Workflow runs

| Push | CI | Backend deploy | Frontend deploy |
|---|---|---|---|
| `b820d96` | red (lockfile) | skipped by the gate | skipped by the gate |
| `3abad04` | green | **red at *Verify the rollout*** although the rollout succeeded (`--0000004`, `3abad04`, `0.9.1`) | green |
| `8d211ad` | green | green: *"backend unchanged since 3abad04; nothing to deploy"* | green |
| `2b662da` | green | **green end to end**: ACR build 3 min 39 s, `--0000006` healthy on `claims-backend:2b662da`, `/health` `0.9.1` on the first poll | green |

## Application Insights

After `2b662da`, a test-bench `POST /api/agents/test/validator` (which writes no audit entry and creates no claim) appears as a 200 request. Its direct children are Postgres `SET` + `SELECT` (the pgvector retrieval) and `api.anthropic.com POST /v1/messages` (200, 2.6 s). `GET /api/claims*` requests carry their Postgres dependencies. Route templates and the cloud role are set. `/health` is excluded: 0 of 7 requests.

## Second verification pass (through the Azure frontend, image `3abad04`)

| | Auto-approve ($85k) ×2 | Threshold ($850k) | Guardrail ($1.4M) |
|---|---|---|---|
| Correlation id | `8590b47e-…`, `f02fb888-…` | `45692633-…` | `b35b146b-…` |
| Terminal status | `awaiting_human` — **recorded exception** | `awaiting_human` ✓ | `awaiting_human` ✓ |
| Fired rules | `guardrail_failed` (LLM check only) | `settlement_over_ceiling` ✓ | `guardrail_failed`, `settlement_over_ceiling` ✓ |
| Audit entries | 7 / 7 | 7 | 7 |

Chain `ok` over 49 rows. Every LLM call was on `anthropic`, with `requested_model` = `model` = `claude-haiku-4-5-20251001`; the guardrail scenario's Adjuster is the demo fixture. All four runs streamed their agent cards live into Run Detail from the Static Web App origin. The stream endpoint answered the Static Web App `Origin` with 200 `text/event-stream`. A deep link hard-reloaded on Azure returned the app. The Vercel deep link is verified by the deploy check only.

**The exception.** The flag came from the Guardrail's LLM check; the rule checks found nothing. Today's recorded Guardrail prompt, replayed at temperature 0 from the Mac without the telemetry packages, reproduced the flag 5 / 5. Pass one's 1 October prompt (`08d514f2-…`, which passed then) fails today 3 / 3, with a different flag. The verdict on byte-identical input changed under an unchanged model id. This affects the Render demo too. Dermot's verdict: pass two is passed for the deployment, with this exception recorded.

## Idempotence what-if (read-only, after `2b662da`)

0 creates and no real changes: `6 to modify, 14 no change, 5 unsupported, 1 to ignore`. All modify lines fall into known categories:
- Unresolved `reference()` expressions.
- Server-filled properties shown as deletions.
- The `minReplicas` 1 → 0 drift from `azure-start.sh`.
- New server-filled lines on App Insights and the Static Web App: the upload action's repository metadata, not a repository link.

The probe-order noise category is gone. The full list is in the build log.

## Deviations from the plan

1. **Static Web App region:** East US 2, not West Europe, which refused the resource. Decided at the approval gate.
2. **Dependencies:** two packages added, not three. The distro bundles the httpx instrumentation.
3. **Frontend in the request telemetry:** the plan assumed that calling `configure_telemetry` before constructing the app was enough. It was not, and was fixed in `2b662da`.
4. **Cold start before/after telemetry:** not measured. Moved to the backlog.
5. **Vercel deep link:** not tested by hand; verified by the deploy check only.
6. **Pass two's auto-approve scenario** did not reach `settled`. It is recorded as an exception and followed up in the backlog.

## Guard clauses added beyond the spec

None.

## Suggestions

- **Guardrail false positives on Harborline:** tighten the Guardrail prompt to judge only claims about what the policy covers, and keep the replayed prompts as a pre-demo regression fixture. Do this before the next demo, on either deployment.
- **Adjuster at temperature 0 for the scripted scenarios**, so the Guardrail sees stable input.
- **A scheduled eval against the live model** (production target, [`change-governance.md`](../change-governance.md)): behavioural drift under a pinned model id is now an observed vendor risk.
- **Measure cold start** with and without telemetry.
- **Decide the Render / Neon retirement**, now that the condition is met.
