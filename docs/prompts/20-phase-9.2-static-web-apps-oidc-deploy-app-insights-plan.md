# Phase 9.2 — Plan: frontend on Static Web Apps, OIDC deploy on push, Application Insights, second verification pass

Prompt: [`20-phase-9.2-static-web-apps-oidc-deploy-app-insights.md`](20-phase-9.2-static-web-apps-oidc-deploy-app-insights.md). Patch version `0.9.0 → 0.9.1`.

Plan written 26 October 2026 against commit `4a37861`. Nothing in Azure has been created, no GitHub variable or secret has been set, and no code has been written. Items marked **⚠ decision needed** deviate from, or add to, the prompt's wording; everything else follows the prompt as written. The deadline is the Azure credit expiry on 30 October 2026.

---

## 0. Findings that shape the plan

Measured on this machine and against the live subscription on 26 October 2026, not assumed.

1. **CI on `main` has been red since 15 June 2026 (Phase 6).** The last green run is Phase 5 (14 June). Every push since fails in the *Frontend* job at `npm ci` with `EUSAGE: package.json and package-lock.json are not in sync` (missing `@emnapi/core`, `@emnapi/runtime`, `@emnapi/wasi-threads` entries under the `wasm32-wasi` optional packages of `@rolldown/binding` and `@tailwindcss/oxide`). `npm ci` fails identically on this Mac (npm 11.6.2). The *Backend* job passes. A deploy workflow that depends on CI passing therefore **cannot fire at all** until the lockfile is regenerated. Previewed in the scratchpad: `npm install --package-lock-only` adds 104 lines (the missing optional entries) and changes no direct dependency. This is a prerequisite, not a nice-to-have — see §1.
2. **Two resource providers are not registered:** `Microsoft.Web` (Static Web Apps) and `Microsoft.Insights` (Application Insights) both report `NotRegistered`. Two `az provider register` commands, added to the README prerequisites.
3. **Static Web Apps regions** offered to this subscription: Central US, East US 2, West US 2, **West Europe**, East Asia. West Europe it is — the one resource outside North Europe.
4. **The Postgres server is `Ready`, not stopped.** The activity log shows the last `stop` succeeded at 18:31 UTC on 1 October and no `start` since; the service's seven-day auto-restart (the caveat in `azure-stop.sh`'s header) brought it back around 8 October, and it has been running since. The Container App is at `minReplicas` 0 on image `967a348`. Operationally: `azure-stop.sh` remains the last act of the session, and the auto-restart goes to the backlog as a limitation the stop script cannot fix.
5. **GitHub:** repository `dcopps/agentic-claims-poc`, Actions enabled (`allowed_actions: all`), **no repository variables or secrets exist yet**.
6. **CORS parsing confirmed:** `CORS_ALLOWED_ORIGINS='["https://agentic-claims-poc.vercel.app","https://example.1.azurestaticapps.net"]'` constructs `Settings()` with a two-element Python `list` — pydantic-settings JSON-decodes complex fields from the environment. No settings change is needed for §6.
7. **Role definitions read from the subscription:** `AcrPush` grants only `pull/read` and `push/write` — it cannot queue an `az acr build`. `Container Registry Tasks Contributor` (`fb382eab-…`) grants `scheduleRun/action`, `listBuildSourceUploadUrl/action`, `runs/*` and `registries/read`, which is exactly what `az acr build` does. `Container Apps Contributor` (`358470bc-…`) grants `containerApps/*/write` plus `managedEnvironments/read`. `Managed Identity Operator` (`f1a07417-…`) grants `userAssignedIdentities/*/assign/action`. See §5.
8. **The app does not touch the database at startup** (`_lifespan` loads the policy and variant registry only; `/health` touches nothing). A deploy therefore passes its probes and the version check even while the deployment is parked.
9. **Frontend facts:** routes are `/`, `/claims/:claimId`, `/claims/:claimId/runs/:correlationId`, `/claims/:claimId/compare/:a/:b`, `/audit`, `/agents`; the API base is `VITE_API_BASE_URL`; the run stream is a plain `EventSource` (no credentials); `frontend/public/` does not exist yet; the lockfile's `engines` require Node `^20.19 || ^22.12 || >=24` and CI uses `setup-node@v4` with `20`.
10. **List prices (EUR, fetched today from the Azure retail prices API):** Container Registry Basic €0.1466/day, registry storage €0.088/GB-month, Postgres backup storage €0.0836/GB-month, Static Web Apps Free €0 (Standard would be €7.92/month). The API query did not return the B1ms compute or Flexible Server storage meters; §10 uses the published list (≈ $0.017/h and ≈ $0.115/GiB-month) and says so.

---

## 1. Prerequisites — before any Azure resource is created

**1a. Regenerate `frontend/package-lock.json` — ⚠ decision needed (a one-file change the prompt did not list).** `cd frontend && npm install` (Node 20, matching CI), then `npm ci && npm run build && npm test -- --run` locally to prove the result. No `package.json` change; no new direct dependency; the diff is the 104 missing optional-package entries. Without this, deliverable 3 ("both depend on CI passing") is unreachable and `gh run list` can never show green. It goes in as the first commit of 9.2 so the push that carries the workflows is also the push that turns CI green.

**1b. Register providers:** `az provider register --namespace Microsoft.Web` and `… Microsoft.Insights`, then wait for `Registered` (usually under two minutes). Added to the README and `infra/bicep/README.md` prerequisites loop.

**1c. The 30 October credit expiry is not a billing cliff.** The subscription was upgraded to Pay-As-You-Go on 1 October 2026 during Phase 9.1 (corrected at the approval gate; the plan as first written assumed a free trial). Expiry of the credit therefore disables nothing; from 31 October the parked cost in §10 is simply billed.

---

## 2. Bicep changes

### 2a. Modules

| File | Change |
|---|---|
| `modules/deployer-identity.bicep` | **New.** A **second** user-assigned identity, `id-claimsai-dev-deployer`, with one child resource `Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31` named `github-main`: issuer `https://token.actions.githubusercontent.com`, subject `repo:${githubRepository}:ref:refs/heads/main`, audiences `['api://AzureADTokenExchange']`. Outputs `clientId`, `principalId`. |
| `modules/staticwebapp.bicep` | **New.** `Microsoft.Web/staticSites` (latest stable API the local Bicep type index accepts; `2024-04-01` at the time of writing), SKU `Free`/`Free`, its own `location` parameter, **no** `repositoryUrl`, `branch` or `buildProperties` (decision 1: nothing links it to GitHub), `allowConfigFileUpdates: true`, `stagingEnvironmentPolicy: 'Disabled'` (the token deploys only to production; no preview environments to secure or pay attention to). Outputs `name`, `defaultHostname`. |
| `modules/appinsights.bicep` | **New.** `Microsoft.Insights/components@2020-02-02`, `kind: 'web'`, `Application_Type: 'web'`, `WorkspaceResourceId` = the existing Log Analytics workspace, `IngestionMode: 'LogAnalytics'`. Output `connectionString`. |
| `modules/acr.bicep` | New param `pushPrincipalId`; two deterministic role assignments for the deployer scoped to the registry: `AcrPush` and `Container Registry Tasks Contributor` (why both: §5). |
| `modules/containerapps.bicep` | New params `deployerPrincipalId`, `appInsightsConnectionString`. The container's `env` gains `APPLICATIONINSIGHTS_CONNECTION_STRING` as a plain value (§4). One role assignment, `Container Apps Contributor`, scoped to the Container App resource, conditional on `deployApp`. Probes reordered to Liveness, Readiness, Startup (§9) — values unchanged. |
| `modules/identity.bicep` | **Only if the first workflow run proves it necessary** (§5): `Managed Identity Operator` for the deployer, scoped to the backend identity. Not deployed speculatively. |
| `main.bicep` | Wires the three new modules. New params `githubRepository` (string, `owner/repo`), `staticWebAppLocation` (default `westeurope`). **`corsAllowedOrigins` changes type from JSON string to `array`** and `main.bicep` composes the final value: `string(concat(corsAllowedOrigins, ['https://${staticWebApp.outputs.defaultHostname}']))`. New names: `swa-${base}`, `appi-${base}`, `id-${base}-deployer`. New outputs: `staticWebAppName`, `staticWebAppDefaultHostname`, `deployerClientId`, `deployerPrincipalId`, `appInsightsName`. |
| `main.bicepparam` | `githubRepository = 'dcopps/agentic-claims-poc'`, `staticWebAppLocation = 'westeurope'`, `corsAllowedOrigins = ['https://agentic-claims-poc.vercel.app']`. Nothing secret; nothing machine-specific. |

**Why a separate deployer identity (the prompt's recommendation, adopted).** The principal GitHub can act as should not be the principal that can read Key Vault, and the runtime principal should not be able to push images or rewrite the app. Two identities, disjoint grants: the backend identity keeps *Key Vault Secrets User* + *AcrPull*; the deployer gets *AcrPush* + *Tasks Contributor* + *Container Apps Contributor* and nothing on the vault. A compromise of the GitHub side yields the ability to deploy an image, not to read a secret.

**Confirmations the prompt asked for (decision 3).** A user-assigned managed identity carries federated identity credentials as a child resource type in Bicep (`…/userAssignedIdentities/federatedIdentityCredentials`), no app registration involved. The identity's `clientId` and the tenant and subscription ids are identifiers: the OIDC exchange succeeds only when GitHub's token carries the matching issuer *and* subject, i.e. a workflow actually running on `refs/heads/main` of `dcopps/agentic-claims-poc`. Possessing the ids grants nothing. One operational consequence: if a job is ever given a GitHub *environment*, the token's subject changes to `…:environment:<name>` and the login fails — documented in the workflow header, and the failure is a halt, not a prompt to add a credential.

### 2b. One Bicep pass, not two — ⚠ decision needed

The Static Web App's hostname is server-generated and known only after creation, but it is an **output of a resource in the same deployment**, so `main.bicep` can compose the CORS list from it and the Container App receives the two-element value in the same pass. The 9.1 two-pass pattern existed because an image had to be *built* between passes; nothing here has that shape. Recommended: one pass. Alternative (not recommended): two passes with the hostname pasted as a literal into `main.bicepparam` after pass 1 — one more committed value to keep in step with Azure.

The pass must be run with the **currently deployed image** (`…/claims-backend:967a348`) so the Container App is in scope and receives its env changes; see §9 for the script change that makes this the default.

### 2c. Expected `what-if`

Preview (before deploy), with the current image:

- **Create 4:** deployer identity, its federated credential, the Static Web App, the Application Insights component.
- **Modify 1 (real):** the Container App — two env entries (`CORS_ALLOWED_ORIGINS` value, `APPLICATIONINSIGHTS_CONNECTION_STRING` new) and the probe order.
- **Unsupported 5** (was 2): the three new role assignments join the two existing ones; their names depend on `principalId`s unknown until deployment.
- **Noise** in the 9.1 categories 2 (`reference()` expressions — the App Insights connection string now joins them) and 3 (server-defaulted properties). Category 1 (probe order) appears for the last time, as the real change that removes it.

Idempotence (after deploy): 0 create, 0 real modify; noise in categories 2 and 3 only, probably with new category-3 lines for the Static Web App and Application Insights server defaults. Judged by the Phase 9.1 criterion: **no real changes, verified against live state**, line by line in the build log.

---

## 3. Static Web App

- **SKU Free, West Europe** (§0.3). Content is served from the global edge regardless of the resource's region; the region holds only the resource and its deployment metadata.
- **`staticwebapp.config.json` — ⚠ decision needed on its location.** The prompt says "at the frontend root". Recommended: **`frontend/public/staticwebapp.config.json`**. Reason: the workflow builds the app itself (§3, next bullet) and deploys `frontend/dist`; the Static Web Apps action reads the config from the folder it deploys, and Vite copies `public/` into `dist/` verbatim, so this is the one placement where the file ships without a copy step. Content: `navigationFallback` with `rewrite: "/index.html"` and `exclude: ["/assets/*", "/*.{css,js,map,ico,png,svg,json,txt,woff,woff2}"]`, as the docs recommend, so a missing asset is a real 404 and only navigations fall back. Nothing else (no routes, no headers) — the spec.
- **Build in the workflow, not Oryx.** The alternative is to let the action's Oryx build run `npm run build`. Rejected: Oryx chooses its own Node version (the lockfile requires `^20.19 || ^22.12 || >=24`), and a build we run is the same `npm ci && npm run build` CI runs, on `setup-node` 20, with `VITE_API_BASE_URL` set explicitly from the repository variable `AZURE_BACKEND_URL` for that one step. The action is then invoked with `skip_app_build: true`, `skip_api_build: true`, `app_location: frontend/dist`, `production_branch: main`.
- **Hostname** is of the form `<word>-<word>-<hex>.<n>.azurestaticapps.net`, captured as the Bicep output `staticWebAppDefaultHostname`, flows into CORS in the same deployment (§2b), and is recorded in README / CLAUDE.md after the pass.
- **Deployment token — the one manual step.** Retrieved and stored without ever being displayed:

  ```bash
  az staticwebapp secrets list --name swa-claimsai-dev --resource-group rg-claimsai-dev \
      --query properties.apiKey -o tsv \
    | gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN --repo dcopps/agentic-claims-poc
  ```

  Secret name: **`AZURE_STATIC_WEB_APPS_API_TOKEN`**. Rotation, if ever needed: `az staticwebapp secrets reset-api-key`, then repeat the line.

---

## 4. Workflows

### 4a. How "depends on CI passing" is implemented — ⚠ decision needed

**Chosen: `workflow_run` on `CI`** (`types: [completed]`, `branches: [main]`), plus `workflow_dispatch`, with the job guarded by `if: github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success'` and checkout at `github.event.workflow_run.head_sha`.

Why not a job dependency inside one workflow: it would mean either duplicating CI's jobs in each deploy workflow, folding the deploy jobs into `ci.yml` (the prompt asks for two workflows, and `ci.yml` should stay the thing a pull request runs), or turning `ci.yml` into a reusable workflow called from both — which runs CI twice per push. `workflow_run` leaves `ci.yml` untouched and makes "CI is green on this commit" a literal precondition rather than a convention.

**The cost of `workflow_run` is that GitHub does not apply `paths:` filters to it.** The path filter is therefore implemented inside the workflows, differently per tier:

- **Backend: diff against what is deployed.** After login the workflow reads the running image tag (a short SHA) from the Container App, then `git diff --quiet <deployed-sha> <head-sha> -- backend pyproject.toml uv.lock Dockerfile`. No change → the job logs *"backend unchanged since <sha>; nothing to deploy"* and exits 0. This is strictly stronger than a path filter: it is correct across multi-commit pushes, and it self-heals — if a deploy fails, the next push redeploys even if it touched only docs, because the deployed image still differs from `main`. If the deployed tag is not in history the job fails loudly (someone deployed something not on `main`). Needs `fetch-depth: 0`.
- **Frontend: no filter — every green CI run on `main` redeploys the frontend.** A Static Web App exposes no "deployed commit" to diff against, and the `workflow_run` payload carries no push range. The honest alternatives each cost something the prompt forbids or discourages: `actions: read` (to find the previous deploy run's SHA), `checks: read` (for a `push` + `paths` + poll-the-check-runs design), or a third-party change-detection action. A frontend deploy is `npm ci`, a build and an upload: about ninety seconds, free, and idempotent in effect. **Alternative, if strict path filtering is wanted:** both workflows on `push` with native `paths:`, gated by a ~15-line step that polls the commit's check runs until both CI jobs report success, costing `checks: read` as a third permission.

### 4b. `deploy-backend.yml`

`permissions: { id-token: write, contents: read }`; `concurrency: { group: deploy-backend, cancel-in-progress: false }` (pushes queue, never race, and a running deploy is never cancelled mid-update); `timeout-minutes` set.

1. `actions/checkout@v4` at `head_sha`, `fetch-depth: 0`.
2. `azure/login@v2` with `client-id: ${{ vars.AZURE_CLIENT_ID }}`, `tenant-id: ${{ vars.AZURE_TENANT_ID }}`, `subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}` — OIDC, no secret. Failure here is a halt.
3. `az extension add --name containerapp`.
4. Read the deployed image; change detection (§4a).
5. `az acr build --registry $AZURE_ACR_NAME --platform linux/amd64 --file Dockerfile --image claims-backend:<short-sha> .` — the SHA tag only (no mutable `latest` from the workflow; the local script keeps its behaviour).
6. `az containerapp update -g $AZURE_RESOURCE_GROUP -n $AZURE_CONTAINER_APP_NAME --image <acr>.azurecr.io/claims-backend:<short-sha>`.
7. **Verify:** source `scripts/azure-common.sh` and call a new `wait_for_health_version "$AZURE_BACKEND_URL/health" "<version from pyproject.toml at head_sha>"` — the same `HEALTH_RETRIES × HEALTH_INTERVAL_S` budget the start script uses (36 × 5 s), failing the run if `/health` does not answer 200 **with that version** in time. *Optional, recommended:* also assert that the active revision's image equals the reference just deployed, because `/health` cannot distinguish two builds of the same version number — a bug-fix deploy that keeps `0.9.1` would otherwise pass the version check against the old revision.

Resource names arrive as **repository variables**, not discovery: the deployer identity deliberately has no resource-group-scope read, so the `az resource list -g` lookups the local scripts use would be denied. Variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_ACR_NAME`, `AZURE_CONTAINER_APP_NAME`, `AZURE_BACKEND_URL`. All are identifiers; all set with `gh variable set`.

### 4c. `deploy-frontend.yml`

`permissions: { contents: read }` only — it never logs in to Azure, so `id-token: write` is not needed (narrower than the prompt's line, which was written for the backend). `concurrency: { group: deploy-frontend, cancel-in-progress: false }`.

1. Checkout at `head_sha`.
2. `actions/setup-node@v4`, Node 20, npm cache keyed on `frontend/package-lock.json` (as CI).
3. `npm ci`; `npm run build` with `VITE_API_BASE_URL: ${{ vars.AZURE_BACKEND_URL }}` on that step.
4. `Azure/static-web-apps-deploy@v1` with `azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}`, `action: upload`, `app_location: frontend/dist`, `skip_app_build: true`, `skip_api_build: true`, `production_branch: main`.
5. *Optional, recommended:* a deep-link smoke check — `curl -fsS "$AZURE_FRONTEND_URL/audit?correlation_id=smoke"` must return 200 containing `<div id="root">`, automating the demonstrable outcome in the prompt's table. Adds one variable, `AZURE_FRONTEND_URL`.

### 4d. Shared script change

`scripts/azure-common.sh` gains `wait_for_health_version URL VERSION` (polls like `wait_for_health`, additionally parses `.version` with `jq`, which is present on this Mac and on `ubuntu-latest`). `wait_for_health` stays for `azure-start.sh`.

---

## 5. RBAC — additions to the table

| Principal | Role | Scope | Why |
|---|---|---|---|
| `id-claimsai-dev-deployer` | AcrPush | the registry | Push the built image's layers. |
| `id-claimsai-dev-deployer` | Container Registry Tasks Contributor | the registry | `az acr build` queues an ACR Task run: `scheduleRun/action`, `listBuildSourceUploadUrl/action`, `runs/read`, `runs/listLogSasUrl/action`. AcrPush alone cannot queue a build — verified against the role definition today (§0.7). |
| `id-claimsai-dev-deployer` | Container Apps Contributor | the Container App | `containerApps/*/write` for `az containerapp update --image`. Scoped to the app resource, not the environment or the group; the role's environment-level actions are inert at that scope. |
| *(conditional)* `id-claimsai-dev-deployer` | Managed Identity Operator | `id-claimsai-dev-backend` | Only if ARM rejects the update PATCH because it carries the app's identity block and demands `…/assign/action` on the backend identity. Decided by the first real run; added in Bicep and redeployed; never a wider role. |

No subscription- or resource-group-scope assignment; the deployer cannot list the group (hence variables, §4b). The `what-if` "unsupported" count becomes 5. The narrowest Container Apps role that works is settled empirically — the fallback is bounded and named above.

---

## 6. Application Insights

**Component:** workspace-based (§2a), linked to `log-claimsai-dev`, North Europe. **Connection string → the Container App as a plain env var `APPLICATIONINSIGHTS_CONNECTION_STRING`.** The choice, stated: Microsoft's model treats the connection string as ingestion configuration, not a secret (the instrumentation key permits sending telemetry, nothing else, and the component can later be switched to Entra-only ingestion); a Key Vault round trip would add a secret, a reference and nothing in protection; and as a plain value it is visible in `az containerapp show` and in `what-if`, where it will appear as a category-2 `reference()` line.

**Instrumentation — ⚠ dependency decision needed (no dependency is added until confirmed).**

*Option A (recommended): add the SDK.* Three packages:

| Package | Why the existing stack cannot cover it |
|---|---|
| `azure-monitor-opentelemetry` | Microsoft's distro: OpenTelemetry SDK + the Azure Monitor exporter + auto-instrumentation for FastAPI, `requests`, `urllib`, `urllib3`, `psycopg2`, Django, Flask, and a logging handler. Nothing in the current stack can emit to Application Insights. |
| `opentelemetry-instrumentation-httpx` | The `anthropic` and `mistralai` SDKs make their calls over `httpx`, which the distro does **not** bundle. Without it the outbound LLM calls are invisible as dependencies — and those are the calls worth seeing. |
| `opentelemetry-instrumentation-psycopg` | The backend uses psycopg 3 (`psycopg[binary]`); the distro bundles only the psycopg2 instrumentation. Gives the Postgres dependency calls. |

What it captures: every `/api/*` request with status and duration; unhandled exceptions with stack traces; dependencies — Anthropic/Mistral HTTPS calls and Postgres statements — correlated to the request; the app's Python logs into the workspace `traces` table. `/health` is excluded from request telemetry (`OTEL_PYTHON_EXCLUDED_URLS=health`), because three probes at 5–30 s intervals would otherwise be the bulk of ingestion and all of the noise. Import-time cost: the distro and exporter import in the order of a few hundred milliseconds on one vCPU, under 3 % of the measured 28 s cold start; the before/after cold start is measured and recorded in the report. Image growth: roughly a dozen pure-Python packages, ~10–15 MB.

How it is a no-op when absent: a new `TelemetrySettings` sub-model (`telemetry.connection_string: SecretStr | None = None`) with `APPLICATIONINSIGHTS_CONNECTION_STRING` as the **fourth named env alias** (alongside `DATABASE_URL`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`), added to `settings.yaml.template` as `telemetry: { connection_string: null }`. A new `backend/app/telemetry.py` exposes `configure_telemetry(app, settings) -> bool`: sanitise (strip) → validate (empty → return `False` **before any `azure.*` or `opentelemetry.*` import**, so local dev, Render, CI and pytest never load the SDK; a non-empty string without `InstrumentationKey=` → `ValueError` naming what was expected and the truncated value) → execute (`configure_azure_monitor(connection_string=…)`, `FastAPIInstrumentor.instrument_app(app)`, `HTTPXClientInstrumentor().instrument()`, `PsycopgInstrumentor().instrument()`, return `True`). Called once from `create_app()`. Tests: unset → `False` and `azure.monitor` absent from `sys.modules`; set → the three configure calls happen exactly once with the given string (monkeypatched); malformed → the `ValueError` text; each test checked for discrimination by reverting the guard it covers. The kill switch, if telemetry ever misbehaves in the demo (for instance the ASGI middleware interfering with the SSE stream — not expected, verified in §8): unset the env var; no code change.

*Option B: provision only.* The component exists and the connection string reaches the container; the SDK goes to the backlog; the portal shows nothing from the app until it lands, so the table's "requests and exceptions visible" outcome is not met in 9.2.

---

## 7. CORS

`corsAllowedOrigins` becomes the two-element list (Vercel origin retained, Static Web App origin appended by Bicep — §2b). `cors_allowed_origins` in `backend/settings.py` is unchanged; parsing of a two-element JSON list from the env var was exercised today (§0.6). The frontend's `EventSource` sends no credentials, so the existing `allow_credentials=True` with an explicit origin list is exactly what the SSE stream needs; the browser's `access-control-allow-origin` header on the `text/event-stream` response is the proof captured in §8. `localhost` stays out of the Azure list, as in 9.1.

---

## 8. Second verification pass — through the UI

**Preconditions:** both workflows green on the 9.2 push; `/health` on Azure reports `0.9.1`; the Static Web App serves the new build; `azure-start.sh` has set one warm replica (Postgres is already `Ready`, §0.4).

**Do not reseed — ⚠ confirm.** Reasons: (1) `rows_checked` continuing from 21 to **42** proves one ledger survived the 9.1 stop/start, the 9.2 Bicep pass (new revision) and the workflow-driven image swap — a continuity property a reseed would erase; (2) reseeding means `--allow-truncate` against a deployed database, exactly the class of action the project's guards exist to make rare; (3) nothing in 9.2 changes schema or seed content. Expected after the pass: 15 claims, 42 audit rows.

**Procedure (browser, Azure frontend URL), for Harborline Logistics ($85k water), Northwood Manufacturing ($850k fire) and Coral Bay Holdings ($1.4M, hallucinated endorsement):** *Load demo claim* → *Submit* → *Process* → in Run Detail, watch the seven SSE events arrive in order; record correlation id, terminal state and fired rules; Audit page shows seven entries; *Verify chain* → `ok`. In the browser's Network panel, the stream request must be `text/event-stream`, status 200, with `access-control-allow-origin` equal to the Static Web App origin — that is the CORS + SSE proof. Expected: `settled` / `awaiting_human` (`settlement_over_ceiling`) / `awaiting_human` (`guardrail_failed`, `settlement_over_ceiling`); providers and models as in 9.1 (`claude-haiku-4-5-20251001`; the Coral Bay Adjuster is the demo fixture). After the third run: chain `ok`, `rows_checked` 42. **Deep links:** hard-reload `/audit?correlation_id=<id>` on Azure and on Vercel — the app renders both times. **Application Insights:** Transaction search shows the three `/api/pipeline/run/…` requests with their Anthropic and Postgres dependencies (Option A) or, under Option B, the component exists and shows no data yet, recorded as such.

**Halt** if any scenario lands in the wrong terminal state or the SSE stream does not reach the browser: diagnose, do not retry. **Record as pass two of two** in the build log, which satisfies the `CLAUDE.md` condition for the Render / Neon decision. **Retirement is not done in 9.2** — it becomes a decision item in the backlog with the saving (Render Standard, $25/month) and what retiring would remove (the canonical demo URL on Vercel, the Neon database, `render.yaml`).

---

## 9. Small items from the 9.1 report

| Item | Taken? | Estimate | Note |
|---|---|---|---|
| Reorder probes to Liveness, Readiness, Startup | **Yes** | 5 min | Zero behaviour change; removes the one what-if noise category that is ours. Lands in the same Container App modify as the env vars — no extra revision. |
| `azure-stop.sh` waits for zero replicas before stopping Postgres | **Yes** | 30 min | New `wait_for_zero_replicas` in `azure-common.sh`: poll `az containerapp replica list … --query 'length(@)'` every `REPLICA_POLL_INTERVAL_S=15` up to `REPLICA_DRAIN_TIMEOUT_S=420` (the 300 s cooldown plus margin), `die` with the remaining count if not drained. Chosen over deactivating the revision, which `azure-start.sh` would have to reverse. |
| `azure-deploy.sh` defaults to the **live** image when none is given and a Container App exists — **⚠ behaviour change, confirm** | **Yes** | 20 min | After 9.2 the image is owned by the workflow. Today an image-less `deploy` or `what-if` means "infrastructure only"; against a group that already has an app that would show (and on `deploy`, *apply*) a regression to whatever image the shell happened to pass. New rule: no argument + app present → read and echo the deployed image and use it; no argument + no app → pass 1 as today. |
| Bootstrap guards into the README / a `scripts/azure-bootstrap.sh` | No | — | Not cheap enough to do well before the deadline; stays in the backlog. |
| Install `shellcheck` | No (suggestion) | — | `brew install shellcheck`; would be run over the scripts if present. |

---

## 10. Cost

New in 9.2: **Static Web App Free: €0. Application Insights: €0** — one verification pass is on the order of thirty requests, a dozen dependency calls and a few hundred log lines, well under a megabyte; probe traffic is excluded; the 5 GB/month free allowance is not approached. The deployer identity, the federated credential and three role assignments are free. Nothing else changes.

**Parked monthly cost, restated as one number: about €8 a month at list price**, made up of the Container Registry Basic unit (€0.1466/day ≈ €4.5), registry storage (~0.5 GB, ≈ €0.05), Postgres storage at 32 GiB (≈ €3.5 — published list ≈ $0.115/GiB-month; not returned by the price API today), backup storage within the equal-to-provisioned allowance (€0), Key Vault (< €0.05), Log Analytics and Application Insights within the free tier, Container Apps at zero replicas (€0), Static Web App Free (€0). If the account's 12-month free allowance (750 h/month of B1ms and 32 GiB) applies, Postgres costs nothing and the figure is about €4.5. **If Postgres is left running** — as it has been since the auto-restart around 8 October — add ≈ €11.5 a month of B1ms compute at list (≈ $0.017/h), or nothing under the allowance. A demo hour with one warm replica is ≈ €0.10 at list, and the Container Apps monthly free grant (180 000 vCPU-s, 360 000 GiB-s ≈ 50 replica-hours) covers demo use entirely. Figures to be confirmed in the Cost analysis blade (the subscription has been Pay-As-You-Go since 1 October, §1c).

---

## 11. Docs

- `README.md` *Azure deployment*: the comparison table gains Frontend and Observability rows; a *Deploy on push* subsection with the seven variables and the one secret, the token line from §3, the Static Web App URL, the two providers in the prerequisites, and the verification procedure through the UI.
- `infra/bicep/README.md`: layout (three new modules), the one-pass CORS composition, the RBAC table (§5), prerequisites, the "run `deploy`/`what-if` with the live image" rule.
- `docs/architecture-stack-reference.md`: the *Prototype on Azure* table gains the frontend (Static Web Apps, West Europe) and telemetry (Application Insights) rows and CI/CD (OIDC deploy on push); the remaining-gaps list unchanged except "Application Insights in 9.2" becomes present.
- `docs/BACKLOG.md`: deep-link items closed (Vercel and Azure); pass two recorded; **Render / Neon retirement added as a decision item**; `azure-stop.sh` item closed; new items: Postgres seven-day auto-restart defeats parking (a scheduled re-stop would need a stop-capable identity — not done), the SDK (if Option B), the frontend path filter (if the always-deploy choice stands), `Managed Identity Operator` outcome (whichever way it went).
- `docs/build-log.md`: Phase 9.2 entry — files, tests, deployment sequence, what-if line list, RBAC, the three-scenario table, the CORS/SSE evidence, App Insights observation, cold start before/after (Option A), cost.
- `CLAUDE.md`: *Hosting & CI*, *Current Status*, and an *Architectural Decisions* bullet recording the four decisions of 26 October (no Azure-written workflows; the workflow does not run Bicep; OIDC via a separate user-assigned identity with a federated credential; Static Web Apps in West Europe), plus the lockfile finding.
- `docs/prompts/20-…-report.md` after the deployment.

---

## 12. Version, dependencies, interface stability

- **Version** `0.9.1` in `pyproject.toml`; `/health` reports it; the workflow's verification asserts it.
- **Dependencies:** the three telemetry packages, only under Option A and only once confirmed. The lockfile regeneration (§1a) adds no direct dependency — it records optional transitive entries already implied by `package.json` — and is flagged here because `package-lock.json` changes.
- **Interface stability:** no JSON schema, HTTP shape, audit payload or database change. New setting `telemetry.connection_string` (+ env alias) in both `settings.py` and `settings.yaml.template`. `main.bicep`'s `corsAllowedOrigins` parameter changes type (string → array); it is consumed only by `main.bicepparam` in this repository. The Container App gains one env var.

---

## 13. Execution order (deployment steps with Dermot present)

1. Approval of this plan and the decisions below.
2. **Code**, committed locally in two commits — (a) the lockfile regeneration; (b) everything else: Bicep, `frontend/public/staticwebapp.config.json`, `frontend/vercel.json`, the two workflows, telemetry (Option A) with tests, script changes, version, docs. Local checks: `az bicep build` + lint (zero warnings), `bash -n` on the scripts, `npm ci && npm run build && npm test -- --run`, `uv run pytest`, `ruff`, `mypy`. **Not pushed yet** — the push that adds the workflows would fire them before the identity, the Static Web App and the variables exist, producing a red first run by construction.
3. Register the two providers (§1b).
4. `scripts/azure-deploy.sh what-if` (live image, §9) → compare with §2c → `deploy`. Outputs give the Static Web App hostname and the deployer `clientId`.
5. Dermot sets the seven (eight with the smoke check) variables with `gh variable set` and the token secret with the piped line in §3.
6. `git push` → CI (now green) → `workflow_run` fires both deploys → `gh run list` shows three green runs. The backend run builds `claims-backend:<sha>`, updates the app, and `/health` reports `0.9.1`; the frontend run publishes to the Static Web App.
7. `azure-start.sh`; the UI verification pass (§8); the Application Insights check.
8. `scripts/azure-deploy.sh what-if` idempotence (live image by default now).
9. Report, build-log entry, `CLAUDE.md`; commit and push. This second push exercises the backend's change detection (docs only → *"nothing to deploy"*) and redeploys the frontend's identical build — both recorded.
10. `scripts/azure-stop.sh` — now waiting for zero replicas — as the last act.

Effort: about half a day for step 2, two to three hours for steps 3–10. Fits before 30 October provided the decisions are made at the gate.

---

## 14. Risks

- **RBAC narrowness is empirical.** Container Apps Contributor at app scope is expected to suffice; if ARM demands `assign/action` on the backend identity, the bounded fallback in §5 applies. Any other authorization failure is diagnosed, not worked around with a wider role.
- **OIDC subject mismatch** (repository renamed, a GitHub environment added to the job, a workflow run from a branch) makes `azure/login` fail. That is the system working; per the constraints it is a halt, never a stored credential.
- **Static Web Apps action semantics with `skip_app_build`** — the config file must be in the deployed folder; covered by `frontend/public/`. The hard reload of a deep link is the acceptance test.
- **`az acr build` from a GitHub runner** uploads the allow-listed context and downloads the embedding model anonymously inside the build, the same as from this Mac; the Hugging Face rate-limit risk from the 9.1 backlog is unchanged.
- **OpenTelemetry's ASGI middleware and the SSE response** (Option A): supported upstream; verified by the UI pass; kill switch is unsetting the env var.
- **what-if noise grows** with two new resource types; the criterion does not change and the list is written down.
- **Two Container App revisions in one session** (Bicep env change, then the workflow's image). Single-revision mode promotes each when healthy; the old one serves until then.
- **`VITE_API_BASE_URL` is baked at build time.** A backend hostname change needs a frontend redeploy (a `workflow_dispatch` suffices). Documented.
- **Vercel project root is assumed to be `frontend/`** (where the backlog places `vercel.json`). If Vercel's root is the repository root the file must sit there instead; the Vercel hard reload in §8 settles it.
- **Postgres auto-restarts seven days after a stop** (observed, §0.4). Parking is therefore good for a week at a time; longer pauses need a re-run of `azure-stop.sh` or an upgrade/teardown decision. Backlog.
- **From 31 October the parked cost is billed** (§1c, §10); the subscription itself is unaffected by the credit expiry.

---

## 15. Optional enhancements (clearly labelled; not in scope unless approved)

- Revision-image assertion in the backend workflow (§4b step 7) — recommended.
- Deep-link smoke check in the frontend workflow (§4c step 5) — recommended; one extra variable.
- `OTEL_PYTHON_EXCLUDED_URLS=health` is part of Option A as designed, not an extra; listed here only so its presence in Bicep is not a surprise.
- A scheduled `azure-stop` (GitHub Actions cron with OIDC) to defeat the seven-day auto-restart — needs a stop-capable role for the deployer identity, a widening; backlog only.
- `shellcheck` over `scripts/azure-*.sh`.

---

## Decisions requested at the approval gate

1. **Lockfile regeneration as the first commit of 9.2** (§1a) — the prerequisite for a CI-gated deploy. Confirm.
2. **Telemetry SDK:** Option A (three packages, recommended) or Option B (provision only).
3. **CI gate and path filter:** `workflow_run` + diff-against-deployed for the backend + always-deploy for the frontend (recommended), or `push` + native `paths:` + a check-runs poll costing `checks: read`.
4. **`staticwebapp.config.json` in `frontend/public/`** (recommended) rather than `frontend/`.
5. **One Bicep pass** with CORS composed from the Static Web App output (recommended) rather than two passes with a pasted hostname.
6. **`azure-deploy.sh` defaults to the live image** when an app exists (§9). Confirm.
7. **No reseed** before the verification pass (§8). Confirm.
8. **Optional items** 15.1 and 15.2: in or out.
9. *(Operational, outside the plan)* Re-stop Postgres now rather than at the end of the session?

## Approval

Approved by Dermot on 26 October 2026 with these decisions:

1. Lockfile regeneration is the first commit of 9.2.
2. **Option A** — the three telemetry packages are added.
3. `workflow_run` gate; diff-against-deployed for the backend; always-deploy for the frontend.
4. `staticwebapp.config.json` lives in `frontend/public/`.
5. One Bicep pass, CORS composed from the Static Web App output.
6. `azure-deploy.sh` defaults to the live image when a Container App exists.
7. No reseed before the verification pass.
8. Revision-image assertion: **taken.** Deep-link smoke check: **skipped.**
9. The subscription has been Pay-As-You-Go since 1 October 2026; §1c corrected. Postgres stays running for the duration of 9.2; `azure-stop.sh` is the last act of the session.
