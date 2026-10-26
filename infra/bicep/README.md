# Azure deployment — Bicep (Phase 9.1, extended in 9.2)

Everything inside the resource group is created by `main.bicep`. Nothing is created in the portal, so `what-if` is a truthful preview and the deployment is reproducible. The only resources outside Bicep are the prerequisites: the subscription, its budget alert, and the resource group itself (one CLI command).

## Layout

| File | Purpose |
|---|---|
| `main.bicep` | Resource-group scope. Names, wiring, outputs. |
| `main.bicepparam` | Committed values. Secrets and machine-specific values come from the environment via `readEnvironmentVariable()`. |
| `modules/identity.bicep` | User-assigned managed identity for the backend (runtime). |
| `modules/deployer-identity.bicep` | Second user-assigned identity for GitHub Actions, with a federated credential trusting `repo:<owner>/<repo>:ref:refs/heads/main` (Phase 9.2). |
| `modules/monitoring.bicep` | Log Analytics workspace (Container Apps needs a log destination). |
| `modules/appinsights.bicep` | Workspace-based Application Insights component; its connection string goes to the Container App as a plain env var (Phase 9.2). |
| `modules/staticwebapp.bicep` | Static Web App (Free) for the React frontend, no repository link; deployed by `.github/workflows/deploy-frontend.yml` with its token (Phase 9.2). |
| `modules/postgres.bicep` | Azure Database for PostgreSQL Flexible Server 17, `vector` allow-listed, database, firewall. |
| `modules/acr.bicep` | Basic container registry; `AcrPull` for the backend identity; `AcrPush` + *Container Registry Tasks Contributor* for the deployer; admin user disabled. |
| `modules/keyvault.bicep` | RBAC-mode vault; the four secrets; the two data-plane role grants. |
| `modules/containerapps.bicep` | Consumption environment + backend Container App with Key Vault secret references, `/health` probes, the Application Insights connection string and the OpenTelemetry knobs; *Container Apps Contributor* for the deployer, scoped to the app. |

`main.bicep` composes the backend's CORS list from the committed origins plus the Static Web App's server-generated hostname, so the frontend origin is never copied from the portal into a file.

The scripts in `scripts/azure-*.sh` are the supported way to run this. They resolve resource names from the group at run time, so no generated name is hardcoded anywhere.

## Prerequisites (once)

```bash
az login                                   # subscription Owner
az bicep install                           # Bicep CLI (bundled with az)
az extension add --name containerapp       # az containerapp commands
for ns in Microsoft.App Microsoft.DBforPostgreSQL Microsoft.ContainerRegistry \
          Microsoft.KeyVault Microsoft.OperationalInsights Microsoft.ManagedIdentity \
          Microsoft.Web Microsoft.Insights; do          # the last two: Static Web Apps, Application Insights (9.2)
  az provider register --namespace "$ns"; done
az postgres flexible-server list-skus -l northeurope | grep -c Standard_B1ms   # must be > 0
```

Set a budget alert on the subscription before deploying (Cost Management → Budgets).

## Deploy

**First deployment — two passes.** The registry must exist before an image can be built, and the Container App needs an image to start, so the first deployment creates everything except the app.

```bash
scripts/azure-deploy.sh deploy                     # pass 1: everything except the Container App
scripts/azure-deploy.sh build                      # az acr build → prints <acr>.azurecr.io/claims-backend:<short-sha>
scripts/azure-deploy.sh what-if  <image>           # preview: only the Container App should be added
scripts/azure-deploy.sh deploy   <image>           # pass 2: Container App
scripts/azure-deploy.sh what-if  <image>           # idempotence: no real changes (verified against live state)
```

**Every later infrastructure change — one pass.** Once a Container App exists, `what-if` and `deploy` default to the image it is running, so a Bicep run never regresses the image the deploy workflow put there (the workflow owns the image since Phase 9.2). Pass an image only to change it deliberately.

```bash
scripts/azure-deploy.sh what-if                    # delta against live state, live image
scripts/azure-deploy.sh deploy
scripts/azure-deploy.sh what-if                    # idempotence
```

`what-if` always precedes `deploy` on an existing group. The script reads `ANTHROPIC_API_KEY` / `MISTRAL_API_KEY` from the shell or the local `.env`, reuses the Postgres admin password already in Key Vault (or generates one on first deploy), discovers the public IP and the signed-in user's object id, and echoes names only — never values.

Parameters you may override in `main.bicepparam`: `minReplicas` (0 = scale to zero, 1 = one warm replica), `containerCpu` / `containerMemory`, `corsAllowedOrigins` (the Static Web App origin is appended automatically), `githubRepository`, `staticWebAppLocation`, Postgres SKU and storage. Changing the prefix or environment name changes every resource name: do it only on a fresh group.

## Deploy on push (Phase 9.2)

A push to `main` deploys both tiers once CI is green: `.github/workflows/deploy-backend.yml` (build in ACR, update the Container App, verify `/health` reports the new version and the ready revision runs the new image) and `deploy-frontend.yml` (build, upload to the Static Web App). Both trigger on `workflow_run` of `CI`, so a red CI deploys nothing. The backend workflow diffs the commit against the deployed image's tag and exits early when nothing under `backend/`, `pyproject.toml`, `uv.lock` or `Dockerfile` changed; the frontend redeploys on every green run.

The backend workflow authenticates with **OIDC** on `id-<prefix>-<env>-deployer` — no Azure credential is stored anywhere. After the Bicep pass, set these **repository variables** (identifiers, not secrets) and the **one secret**:

```bash
OUT="$(az deployment group show -g rg-claimsai-dev -n <deployment-name> --query properties.outputs -o json)"
gh variable set AZURE_CLIENT_ID          --body "$(jq -r .deployerClientId.value <<<"$OUT")"
gh variable set AZURE_TENANT_ID          --body "$(az account show --query tenantId -o tsv)"
gh variable set AZURE_SUBSCRIPTION_ID    --body "$(az account show --query id -o tsv)"
gh variable set AZURE_RESOURCE_GROUP     --body rg-claimsai-dev
gh variable set AZURE_ACR_NAME           --body "$(jq -r .registryName.value <<<"$OUT")"
gh variable set AZURE_CONTAINER_APP_NAME --body "$(jq -r .containerAppName.value <<<"$OUT")"
gh variable set AZURE_BACKEND_URL        --body "https://$(jq -r .containerAppFqdn.value <<<"$OUT")"
# The Static Web App deployment token — read once, piped straight into GitHub, never displayed:
az staticwebapp secrets list --name "$(jq -r .staticWebAppName.value <<<"$OUT")" --resource-group rg-claimsai-dev \
    --query properties.apiKey -o tsv | gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN
```

Names are passed as variables rather than discovered because the deployer identity deliberately has no resource-group-scope read. Rotate the token with `az staticwebapp secrets reset-api-key` and repeat the last line. If a workflow job is ever given a GitHub *environment*, the OIDC token's subject changes and the login fails: that is a halt, not a prompt to add a credential.

## Bootstrap the database (from your machine)

```bash
KV="$(az resource list -g rg-claimsai-dev --resource-type Microsoft.KeyVault/vaults --query '[0].name' -o tsv)"
export DATABASE_URL="$(az keyvault secret show --vault-name "$KV" --name database-url --query value -o tsv)"
python3 -c 'import os,urllib.parse as u; print("host:", u.urlparse(os.environ["DATABASE_URL"]).hostname)'
uv run alembic --config backend/alembic.ini upgrade head
uv run python -m backend.data.index_policy                  # expect: Indexed 12 chunks
uv run python -m backend.data.seed_claims --allow-truncate  # expect: Inserted 9 claims
unset DATABASE_URL
```

Echo the hostname only. Never write the Azure URL into `.env`: pytest refuses `*.postgres.database.azure.com` hosts exactly as it refuses Neon, because the fixtures TRUNCATE tables.

## Verify

```bash
FQDN="$(az containerapp show -g rg-claimsai-dev -n ca-claimsai-dev-backend --query properties.configuration.ingress.fqdn -o tsv)"
curl -fsS "https://$FQDN/health"                                        # {"status":"ok","version":"0.9.0"}
uv run python scripts/verify-demo-scenarios.py --backend "https://$FQDN"
```

## Stop / start between demo sessions

```bash
scripts/azure-stop.sh    # Container App → 0 replicas, waits for the last replica to drain, then stops Postgres
scripts/azure-start.sh   # Postgres started; Container App → 1 warm replica; waits for /health
```

Azure restarts a stopped Flexible Server after seven days (observed: stopped 1 October 2026, running again by the 26th), so a pause longer than a week needs the stop script re-run.

The scripts change `minReplicas` outside Bicep. A later `what-if` will report that one property as drift unless `minReplicas` in `main.bicepparam` matches the current state.

## Tear down

```bash
az group delete --name rg-claimsai-dev --yes
az keyvault purge --name <kv-claimsai-dev-xxxxx>      # soft-delete would otherwise block the name for 7 days
```

## RBAC

| Principal | Role | Scope | Why |
|---|---|---|---|
| `id-claimsai-dev-backend` | Key Vault Secrets User | the vault | Resolve the three secret references at revision start. |
| `id-claimsai-dev-backend` | AcrPull | the registry | Pull the image without registry credentials. |
| Deploying user | Key Vault Secrets Officer | the vault | Read `database-url` for the bootstrap; Owner alone has no data-plane access in RBAC mode. |
| `id-claimsai-dev-deployer` | AcrPush | the registry | Push the built image's layers (Phase 9.2). |
| `id-claimsai-dev-deployer` | Container Registry Tasks Contributor | the registry | `az acr build` is an ACR Task run: `scheduleRun/action`, `listBuildSourceUploadUrl/action`, `runs/*`. AcrPush alone cannot queue a build (Phase 9.2). |
| `id-claimsai-dev-deployer` | Container Apps Contributor | the Container App | `az containerapp update --image`; scoped to the app, not the environment or group (Phase 9.2). |

No subscription- or resource-group-scope assignment is created; the deploying user is already Owner, and the deployer identity cannot list the group (hence the repository variables above). The two identities have disjoint grants: GitHub's principal cannot read the vault; the runtime principal cannot push images or rewrite the app.

## Why these choices

- **User-assigned identity.** Container Apps validates Key Vault references and the pull identity when the app is created; a system-assigned identity does not exist yet at that point. Creating the identity first makes one deployment sufficient.
- **Password auth only for Postgres.** The app uses a static `DATABASE_URL`. Entra token auth needs a token-refreshing connection path and `azure-identity`, which arrive with the Foundry work.
- **Public endpoints with firewall rules.** Private endpoints need a VNet, which is a documented Phase 9 gap. The consumption environment has no static egress IP, hence the "allow Azure services" rule.
- **Purge protection off.** So the whole thing can be removed and recreated under the same names.
- **A second identity for GitHub (9.2).** The thing GitHub can act as is not the thing that can read Key Vault. OIDC via a federated credential on a user-assigned identity: no app registration, no client secret; the client, tenant and subscription ids in the workflow variables are identifiers.
- **No Azure-written workflow files (9.2).** The Static Web App has no repository link; the portal's GitHub integration would commit a generated workflow. Both workflows are written and reviewed in this repository; the only manual step is the deployment token.
- **The workflow does not run Bicep (9.2).** Infrastructure stays an operational act from a developer shell, because the parameter file reads its `@secure()` values from that shell's environment. The workflow builds the image and points the existing app at it, nothing more.
- **Static Web App in East US 2 (9.2).** Static Web Apps is not offered in North Europe, and West Europe refused the resource on 26 October 2026 (region not accepting new customers). The resource holds the static bundle and deployment metadata only, served from a global edge; no claim data is ever in it.
- **Application Insights connection string as a plain env var (9.2).** Ingestion configuration, not a secret, in Microsoft's model; visible in `az containerapp show` and in `what-if`; Key Vault would add a secret and a reference for nothing.
