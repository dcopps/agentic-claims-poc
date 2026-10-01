# Azure deployment — Bicep (Phase 9.1)

Everything inside the resource group is created by `main.bicep`. Nothing is created in the portal, so `what-if` is a truthful preview and the deployment is reproducible. The only resources outside Bicep are the prerequisites: the subscription, its budget alert, and the resource group itself (one CLI command).

## Layout

| File | Purpose |
|---|---|
| `main.bicep` | Resource-group scope. Names, wiring, outputs. |
| `main.bicepparam` | Committed values. Secrets and machine-specific values come from the environment via `readEnvironmentVariable()`. |
| `modules/identity.bicep` | User-assigned managed identity for the backend. |
| `modules/monitoring.bicep` | Log Analytics workspace (Container Apps needs a log destination). |
| `modules/postgres.bicep` | Azure Database for PostgreSQL Flexible Server 17, `vector` allow-listed, database, firewall. |
| `modules/acr.bicep` | Basic container registry; `AcrPull` for the identity; admin user disabled. |
| `modules/keyvault.bicep` | RBAC-mode vault; the four secrets; the two data-plane role grants. |
| `modules/containerapps.bicep` | Consumption environment + backend Container App with Key Vault secret references and `/health` probes. |

The scripts in `scripts/azure-*.sh` are the supported way to run this. They resolve resource names from the group at run time, so no generated name is hardcoded anywhere.

## Prerequisites (once)

```bash
az login                                   # subscription Owner
az bicep install                           # Bicep CLI (bundled with az)
az extension add --name containerapp       # az containerapp commands
for ns in Microsoft.App Microsoft.DBforPostgreSQL Microsoft.ContainerRegistry \
          Microsoft.KeyVault Microsoft.OperationalInsights Microsoft.ManagedIdentity; do
  az provider register --namespace "$ns"; done
az postgres flexible-server list-skus -l northeurope | grep -c Standard_B1ms   # must be > 0
```

Set a budget alert on the subscription before deploying (Cost Management → Budgets).

## Deploy (two passes)

The registry must exist before an image can be built, and the Container App needs an image to start, so the first deployment creates everything except the app.

```bash
scripts/azure-deploy.sh deploy                     # pass 1: group + identity, logs, Postgres, ACR, Key Vault, environment
scripts/azure-deploy.sh build                      # az acr build → prints <acr>.azurecr.io/claims-backend:<short-sha>
scripts/azure-deploy.sh what-if  <image>           # preview: only the Container App should be added
scripts/azure-deploy.sh deploy   <image>           # pass 2: Container App
scripts/azure-deploy.sh what-if  <image>           # idempotence: no real changes (verified against live state)
```

`what-if` always precedes `deploy` on an existing group. The script reads `ANTHROPIC_API_KEY` / `MISTRAL_API_KEY` from the shell or the local `.env`, reuses the Postgres admin password already in Key Vault (or generates one on first deploy), discovers the public IP and the signed-in user's object id, and echoes names only — never values.

Parameters you may override in `main.bicepparam`: `minReplicas` (0 = scale to zero, 1 = one warm replica), `containerCpu` / `containerMemory`, `corsAllowedOrigins`, Postgres SKU and storage. Changing the prefix or environment name changes every resource name: do it only on a fresh group.

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
scripts/azure-stop.sh    # Container App → 0 replicas; Postgres stopped (Azure auto-restarts it after 7 days)
scripts/azure-start.sh   # Postgres started; Container App → 1 warm replica; waits for /health
```

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

No subscription-scope assignment is created; the deploying user is already Owner.

## Why these choices

- **User-assigned identity.** Container Apps validates Key Vault references and the pull identity when the app is created; a system-assigned identity does not exist yet at that point. Creating the identity first makes one deployment sufficient.
- **Password auth only for Postgres.** The app uses a static `DATABASE_URL`. Entra token auth needs a token-refreshing connection path and `azure-identity`, which arrive with the Foundry work.
- **Public endpoints with firewall rules.** Private endpoints need a VNet, which is a documented Phase 9 gap. The consumption environment has no static egress IP, hence the "allow Azure services" rule.
- **Purge protection off.** So the whole thing can be removed and recreated under the same names.
