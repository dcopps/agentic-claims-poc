# Phase 9.2 — Frontend on Azure Static Web Apps, GitHub Actions deploy with OIDC, Application Insights, second verification pass

## Where this phase starts

Phase 9.1 is complete (commits `967a348`, `4a37861`; version `0.9.0`). The backend runs on Azure Container Apps at `https://ca-claimsai-dev-backend.victorioushill-60f56bb8.northeurope.azurecontainerapps.io`, the database is Azure Database for PostgreSQL Flexible Server `psql-claimsai-dev-ojemo`, secrets are in Key Vault, and the whole resource group `rg-claimsai-dev` is provisioned by `infra/bicep/`. The three scripted scenarios passed against Azure **once**, driven by `scripts/verify-demo-scenarios.py`. The frontend is still on Vercel and still points at Render, so CORS and the SSE stream have not been exercised on Azure. Read `docs/prompts/19-phase-9.1-azure-foundation-bicep-container-apps-report.md` before planning; the resource inventory, the RBAC table and the what-if noise categories there are the ground truth.

Phase 9.2 is the second of the three Phase 9 sub-phases scoped in prompt 19. Its purpose is to make the Azure deployment **complete and self-deploying**: the frontend on Azure, the whole thing deployed by a push to `main` with no stored cloud credentials, telemetry on the backend, and the second three-scenario verification pass — run through the UI this time, so that the pass that unlocks the Render / Neon decision also proves CORS and SSE.

**Deadline.** The Azure credit on the subscription expires on 30 October 2026. Phase 9.2 is to be planned, built, deployed and verified before then. Scope that does not fit is deferred to the backlog, not squeezed in.

## What 9.2 delivers

| Item | Delivers | Demonstrable outcome |
|---|---|---|
| **Frontend on Azure** | Azure Static Web App (Free tier) provisioned by Bicep, serving the Vite build, with `staticwebapp.config.json` providing `navigationFallback` to `index.html`. `VITE_API_BASE_URL` set to the Azure backend at build time. | Full demo on Azure URLs. A hard load of `/audit?correlation_id=<id>` returns the app, not a 404. |
| **CORS** | `corsAllowedOrigins` gains the Static Web App origin (Vercel origin retained). | Browser calls from the Azure frontend to the Azure backend succeed, including the SSE stream. |
| **Deploy on push** | Two GitHub Actions workflows: backend (`az acr build` → update the Container App image) and frontend (build → Static Web Apps deploy). Backend workflow authenticates to Azure by **OIDC federated credential** on a managed identity; no Azure secret in GitHub. | A push to `main` deploys both tiers. `gh run list` shows green. No long-lived Azure credential exists anywhere. |
| **Application Insights** | Workspace-based Application Insights component (linked to `log-claimsai-dev`), connection string supplied to the Container App. | Requests and exceptions from the backend visible in the portal. |
| **Second verification pass** | All three scenarios run through the Azure frontend against the Azure backend. | Expected terminal states, seven audit entries each, chain verified; CORS and SSE proven. |
| **Vercel deep-link fix** | `frontend/vercel.json` with the SPA rewrite (one file; backlog item since Phase 6). | Vercel remains a working demo surface while it exists. |

Version `0.9.0 → 0.9.1`.

**Still out of scope** (unchanged from prompt 19): VNet and private endpoints, API Management, Service Bus, Durable Functions, SQL Managed Instance and Ledger Tables, Azure AI Search, Entra ID human sign-in, Langfuse, Document Intelligence, the LoRA adapter, Azure DevOps Pipelines. Azure AI Foundry is 9.3.

## Decisions already made — Dermot, 26 October 2026

1. **No Azure-written workflow files.** Creating a Static Web App in the portal offers to connect to GitHub and commits a generated workflow into the repository. We do not use that. The Static Web App is created by Bicep with no repository link, and **both workflows are written by us** and reviewed under this plan, so that every file in the repository was reviewed before it was committed. The only manual step the Static Web App needs is its deployment token, pasted once into GitHub repository secrets by Dermot. The plan states exactly how the token is retrieved (`az staticwebapp secrets list`) and the secret's name.
2. **The backend workflow does not run the Bicep deployment.** Infrastructure changes stay an operational act run from Dermot's machine with `scripts/azure-deploy.sh`, because the parameter file reads the `@secure()` values from the deploying shell's environment. The workflow's job is narrower: build the image in ACR tagged with the short SHA, then point the existing Container App at the new image (`az containerapp update --image …` or the equivalent). The plan states which role assignments that needs (expected: `AcrPush` on the registry, and a role scoped to the Container App that permits updating it — the narrowest that works) and adds them to the RBAC table.
3. **OIDC via a user-assigned managed identity with a federated credential**, created in Bicep, trusted for `repo:<owner>/agentic-claims-poc:ref:refs/heads/main`. No app registration, no client secret. `azure/login@v2` with `client-id`, `tenant-id`, `subscription-id` as plain repository variables (none of these is a secret). The plan confirms that a user-assigned managed identity can carry a federated identity credential in Bicep (`Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials`) and that the identity's two ids are safe to appear in a committed workflow (they are identifiers, not credentials).
4. **Static Web Apps region.** Static Web Apps is not offered in North Europe; the plan picks the nearest available region (expected: West Europe) and records it as the one resource outside North Europe, with the reason. The content is served from a global edge regardless.

## Plan-first

Produce `docs/prompts/20-phase-9.2-static-web-apps-oidc-deploy-app-insights-plan.md` covering:

1. **Bicep changes.** New modules (suggest `staticwebapp.bicep`, `appinsights.bicep`, and the federated credential on the identity — either in `identity.bicep` or a new `deployer-identity.bicep` for a **second** identity, separate from the backend's runtime identity; the plan says which and why. Recommendation to consider: a separate identity, so the thing GitHub can act as is not the thing that can read Key Vault). `main.bicep` wiring; `main.bicepparam` gains the GitHub `owner/repo` and the Static Web App parameters. State what `az deployment group what-if` is expected to show for this delta (creates only, plus the known noise), and that the idempotence check afterwards is judged by the Phase 9.1 criterion: no real changes, verified against live state.
2. **Static Web App.** SKU Free; `staticwebapp.config.json` at the frontend root with `navigationFallback` (`rewrite: /index.html`, excluding `/assets/*` and file extensions as the docs recommend); how the build injects `VITE_API_BASE_URL` (workflow env, from a repository variable holding the backend URL); what the resulting hostname looks like and how it gets into `corsAllowedOrigins` (the Static Web App's default hostname is known only after creation — plan the two-pass order, or a parameter set after pass 1, as 9.1 did for the container image).
3. **Workflows.** `.github/workflows/deploy-backend.yml` and `deploy-frontend.yml`, triggered on push to `main` filtered by path (`backend/**`, `pyproject.toml`, `uv.lock`, `Dockerfile` for the backend; `frontend/**` for the frontend), plus `workflow_dispatch`. Both **depend on CI passing** — the plan says how (a `workflow_run` trigger on `CI`, or a job dependency within one workflow; pick one and say why). Concurrency group so two pushes do not race. `permissions: id-token: write, contents: read` and nothing more. The backend workflow verifies `/health` reports the new version after the update, with the same polling the start script uses, and fails the run if it does not.
4. **Application Insights.** Workspace-based component in Bicep; connection string into the Container App as `APPLICATIONINSIGHTS_CONNECTION_STRING` (via the existing secret-reference pattern or as a plain env var — the connection string is not a secret in Microsoft's model, but the plan states the choice). **Instrumentation is a dependency decision:** Container Apps does not auto-instrument Python. The plan states whether 9.2 adds `azure-monitor-opentelemetry` (or the narrower `opentelemetry-instrumentation-fastapi` + the Azure exporter) to the backend, what it would capture (requests, exceptions, dependencies — including the outbound Anthropic and Postgres calls), its import-time cost at cold start, and how it is made a no-op when the connection string is absent (local dev, Render, tests). Per the standing rule, no dependency is added until confirmed; if the dependency is declined, 9.2 still provisions the component and wires the connection string, and the SDK goes to the backlog.
5. **CORS.** `corsAllowedOrigins` becomes a two-element list: Vercel origin and Static Web App origin. `cors_allowed_origins` in `backend/settings.py` is unchanged; confirm pydantic-settings parses the JSON list from the env var exactly as 9.1 relies on.
6. **Second verification pass — through the UI.** With the Azure frontend live: run Harborline, Northwood and Coral Bay from the browser; capture correlation ids, terminal states, fired rules, audit counts, chain verification (`rows_checked` should be 42 if nothing is reseeded — the plan decides whether to reseed first and says why); confirm the SSE events arrive in the Run Detail view in the browser; confirm a hard reload of a deep link works on both Azure and Vercel. Also confirm the Application Insights portal shows the requests from the run. Record the result in the build log as **pass two of two**, which satisfies the condition in `CLAUDE.md` for the Render / Neon retirement decision — **the retirement itself is not done in 9.2**; it is a separate decision for Dermot, recorded in the backlog with the saving (Render Standard, $25/month).
7. **Small items carried from the 9.1 report**, each a line in the plan with an estimate, included only if cheap: reorder the probes in `containerapps.bicep` to Liveness, Readiness, Startup (removes the one what-if noise category that is ours); `azure-stop.sh` waits for zero replicas before stopping Postgres (backlog item from 9.1). Anything not cheap stays in the backlog.
8. **Cost.** Static Web App Free: €0. Application Insights: first 5 GB/month free; state the expected ingestion for the demo. Nothing else changes. Restate the parked monthly cost, since from 31 October it is real money: the plan gives one number.
9. **Docs.** `README.md` *Azure deployment* section gains deploy-on-push, the repository variables and the one secret, Static Web App URL, and the verification procedure through the UI. `infra/bicep/README.md` updated. `docs/architecture-stack-reference.md`: the prototype's Azure column now includes the frontend and telemetry; the remaining-gaps list unchanged. `docs/BACKLOG.md`: deep-link items closed; verification pass two recorded; Render / Neon retirement added as a decision item; anything deferred from 9.2 added. `docs/build-log.md` Phase 9.2 entry. `CLAUDE.md`: Hosting & CI, Current Status, and an *Architectural Decisions* bullet recording the four decisions above.
10. **Version** `0.9.1`. **Dependencies:** only the telemetry SDK, and only if confirmed (item 4). **Interface stability:** none expected — no schema, HTTP shape or audit payload changes. If `APPLICATIONINSIGHTS_CONNECTION_STRING` becomes a setting in `settings.py`, it is added to `settings.yaml.template` too, per the standing rule, and stated in the plan.

Wait for explicit confirmation before writing code or creating any Azure resource.

## Deliverables (after the plan is approved)

- `infra/bicep/` — new modules, `main.bicep` and `main.bicepparam` changes, `README.md`.
- `frontend/staticwebapp.config.json`, `frontend/vercel.json`.
- `.github/workflows/deploy-backend.yml`, `deploy-frontend.yml`.
- Backend telemetry wiring, if confirmed, plus tests for the no-op path.
- `scripts/azure-*.sh` changes from item 7, if taken.
- `pyproject.toml` → `0.9.1`.
- Docs as item 9. `docs/prompts/20-…-plan.md`, `20-…-report.md`.
- Commit and push. **The Azure deployment is an operational act, done with Dermot present**, in this order: Bicep pass (new resources) → Dermot pastes the Static Web App token and sets the repository variables → push to `main` triggers both workflows → verification through the UI → `what-if` idempotence → report → `scripts/azure-stop.sh` as the last act of the session.

## Constraints

- **Nothing on Render, Vercel or Neon is torn down in 9.2.** The `vercel.json` fix is the only change to the Vercel deployment.
- **No secret in any committed file.** The Static Web App token lives only in GitHub secrets. The identity's client id, the tenant id and the subscription id are not secrets and may appear in workflow files as repository variables, but still prefer `vars.` over literals so the workflow is portable.
- **No portal-created resources.** Static Web App, Application Insights and the federated credential are Bicep. The portal is used only to read the token and to look at telemetry.
- **The Azure Postgres is a deployed database.** Same rules as 9.1: hostname-only echoes, deliberate `--allow-truncate`, pytest refuses it.
- **Halt if a scenario lands in the wrong terminal state** or if the SSE stream does not reach the browser. Diagnose, do not retry.
- **Halt if the OIDC login fails in the workflow** rather than falling back to a stored credential. A stored Azure credential is a design violation, not a workaround.
- Standing conventions per `CLAUDE.md`: plan-first, the 50-line function limit, mutation-proof discipline for any new test, shell scripts pass `bash -n`.

## Archive

Pre-saved at `docs/prompts/20-phase-9.2-static-web-apps-oidc-deploy-app-insights.md`; plan and report alongside with `-plan.md` / `-report.md`. Phase 9.3 will be prompt 21.
