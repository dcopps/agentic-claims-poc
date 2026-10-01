# Phase 9.1 — Plan: Azure foundation (Bicep, Postgres Flexible Server, Container Apps, Key Vault, managed identity)

Prompt: [`19-phase-9.1-azure-foundation-bicep-container-apps.md`](19-phase-9.1-azure-foundation-bicep-container-apps.md). Minor version `0.8.6.1 → 0.9.0`.

Plan written 1 October 2026 against commit `a2c2c16`. Nothing in Azure has been created and no code has been written. Three items below are **deviations or additions to the prompt's wording** and are marked **⚠ decision needed**; everything else follows the prompt as written.

---

## 0. Findings that shape the plan

Measured on this machine on 1 October 2026, not assumed.

| Finding | Evidence | Consequence |
|---|---|---|
| **The lockfile pulls CUDA on Linux.** `torch 2.11.0` resolves from PyPI; the Linux entry depends on `cuda-toolkit[...]` and 36 `nvidia-*` packages. The x86_64 wheel alone is 530 MB. | `uv.lock` lines 2387–2393; `grep -c 'name = "nvidia-' uv.lock` = 36 | `uv sync --frozen` in a Linux image would produce a 4–6 GB container. §3 pins `torch` to the PyTorch CPU index **for Linux only**. The CPU index carries `torch-2.11.0+cpu` for cp311 `manylinux_2_28_x86_64` (checked). |
| **Container Apps does not inject `$PORT`.** Render does; the Container App's ingress `targetPort` is configured, not discovered. | `render.yaml` start command uses `$PORT` | The `Dockerfile` fixes the port (8000, the `api_port` default) and Bicep sets `targetPort: 8000`. No app change. |
| **The embedding loader needs no code change to read a baked model.** `SentenceTransformer(model_name)` with no `cache_folder`; the library honours `HF_HOME`. | `backend/app/agents/validator.py:581`, `backend/data/index_policy.py:205` | Bake via `ENV HF_HOME=/opt/hf` in the image. `backend/settings.py` is untouched. |
| **A Key Vault secret reference cannot be created in the same pass as a system-assigned identity.** The identity does not exist when ARM validates the reference (and the same applies to `AcrPull` for the image pull). Documented in Azure/bicep discussion #12056 and azure-container-apps issue #722. | Web check, 1 Oct 2026 | §5 **⚠ decision**: recommend a **user-assigned** managed identity so one `az deployment group create` is idempotent and what-if is truthful. |
| **Fresh subscription.** Offer `FreeTrial_2014-09-01`, spending limit **on**, user is Owner. Bicep CLI not installed; `containerapp` CLI extension not installed; `Microsoft.App`, `Microsoft.DBforPostgreSQL`, `Microsoft.ContainerRegistry`, `Microsoft.KeyVault`, `Microsoft.OperationalInsights` all `NotRegistered`. | `az account show`, `az bicep version`, `az extension list`, `az provider show` | §11 execution step 0 installs/registers these (local tooling and provider registration, not resources). The spending limit means the free credit cannot be overrun into a bill; the budget alert stands as the early warning. |
| **Free-trial service limits.** Container Apps: one environment per subscription, ten cores. Flexible Server: B1ms + 32 GiB storage + 32 GiB backup free for 750 h/month for 12 months on a free account. | Microsoft Learn (links in §13) | One environment is all 9.1 needs. The prompt's largest cost line (~€12–15/month) is covered by the free allowance for the first year. |
| **Postgres 17 and pgvector 0.8.0 are GA on Flexible Server**; `vector` must be allow-listed via the `azure.extensions` server parameter before `CREATE EXTENSION`. | Flexible Server release notes; provider API `2025-08-01` is GA | §2 requests major version `17` to match Neon exactly (same engine, same pgvector). |
| **Both regions are available.** North Europe and West Europe are listed for `flexibleServers` and `managedEnvironments`. | `az provider show … locations` | Region `northeurope`. If B1ms quota is refused for the free trial in North Europe at execution time, the fallback is `westeurope` — to be confirmed with `az postgres flexible-server list-skus -l northeurope` in step 0, before anything is created. |
| **Hugging Face anonymous downloads** are rate-limited to 3,000 file requests per 5-minute window per IP; `huggingface_hub ≥ 1.2` sleeps and retries on a 429. The model is ~10 files. | HF Hub rate-limit docs | No HF token. The build is expected to succeed anonymously; §3 states the fallback and that adding a token would be a flagged change. |
| **Deployed CORS origin today** is `https://agentic-claims-poc.vercel.app`; Render holds exactly four env vars (`ANTHROPIC_API_KEY`, `CORS_ALLOWED_ORIGINS`, `DATABASE_URL`, `MISTRAL_API_KEY`). | `docs/build-log.md:802` | The Container App gets the same four, three from Key Vault and `CORS_ALLOWED_ORIGINS` as a plain value. |
| **This machine's public IP** was recorded (supplied at deploy time via `DEPLOYER_CLIENT_IP`; redacted here, never committed). | `curl api.ipify.org` | §2 firewall rule parameter. |

---

## 1. Bicep module layout

```
infra/bicep/
├── README.md                 # deploy / what-if / bootstrap / stop-start / teardown
├── main.bicep                # resource-group scope; wires the modules; outputs
├── main.bicepparam           # non-secret values; secrets via readEnvironmentVariable()
└── modules/
    ├── identity.bicep        # user-assigned managed identity (see §5 ⚠)
    ├── monitoring.bicep      # Log Analytics workspace (Container Apps environment requires one)
    ├── keyvault.bicep        # vault (RBAC model) + the four secrets + deployer role
    ├── acr.bicep             # Basic registry + AcrPull for the identity
    ├── postgres.bicep        # Flexible Server, database, azure.extensions, firewall
    └── containerapps.bicep   # managed environment + backend Container App
```

**Scope and resource group.** `az deployment group` needs an existing group, so the group is created with one CLI command (`az group create -n rg-claimsai-dev -l northeurope`), documented in the README. Everything inside the group is Bicep. (A subscription-scope deployment could create the group too; not worth the extra scope indirection for one resource.)

**Parameters (`main.bicepparam`).** Non-secret: `namePrefix = 'claimsai'`, `environmentName = 'dev'`, `location = 'northeurope'`, `postgresSkuName = 'Standard_B1ms'`, `postgresTier = 'Burstable'`, `postgresVersion = '17'`, `postgresStorageGiB = 32`, `postgresAdminLogin = 'claimsadmin'`, `containerCpu = '1.0'`, `containerMemory = '2Gi'`, `minReplicas = 0`, `maxReplicas = 1`, `corsAllowedOrigins = '["https://agentic-claims-poc.vercel.app"]'`, `containerImage` (see deploy sequence). Secrets are `@secure()` parameters read with `readEnvironmentVariable()` in the `.bicepparam` file: `postgresAdminPassword`, `anthropicApiKey`, `mistralApiKey`, plus `deployerClientIp` and `deployerPrincipalId` (not secrets, but machine-specific, so also from the environment rather than committed). Values therefore never appear on the command line or in shell history, and the committed file holds only names.

**Naming.** `uniqueString(resourceGroup().id)` (first five characters) is appended where Azure requires global uniqueness; it is deterministic, so redeploys are idempotent.

| Resource | Name |
|---|---|
| Resource group | `rg-claimsai-dev` |
| User-assigned identity | `id-claimsai-backend-dev` |
| Log Analytics workspace | `log-claimsai-dev` |
| Key Vault | `kv-claimsai-dev-<u>` |
| Container Registry | `acrclaimsaidev<u>` |
| Postgres Flexible Server | `psql-claimsai-dev-<u>` → `psql-claimsai-dev-<u>.postgres.database.azure.com` |
| Database | `agentic_claims` |
| Container Apps environment | `cae-claimsai-dev` |
| Container App | `ca-claimsai-backend-dev` |

**Invocation** (from the repo root, after `az login`):

```bash
export POSTGRES_ADMIN_PASSWORD="$(openssl rand -hex 24)"     # URL-safe alphabet: no percent-encoding needed in DATABASE_URL
export ANTHROPIC_API_KEY=… MISTRAL_API_KEY=…                  # from the existing local .env, not retyped
export DEPLOYER_CLIENT_IP="$(curl -s https://api.ipify.org)"
export DEPLOYER_PRINCIPAL_ID="$(az ad signed-in-user show --query id -o tsv)"

az deployment group what-if --resource-group rg-claimsai-dev --parameters infra/bicep/main.bicepparam
az deployment group create  --resource-group rg-claimsai-dev --parameters infra/bicep/main.bicepparam --name claimsai-dev-$(git rev-parse --short HEAD)
```

What-if always runs first; the README says so and the build-log records both outputs. Outputs of `main.bicep`: Container App FQDN, Postgres FQDN, Key Vault name and URI, ACR login server, identity principal id.

**Deploy sequence (two passes, by necessity).** The registry must exist before `az acr build`, and the Container App must have an image to start. Pass 1 deploys with `containerImage` at its default, the public `mcr.microsoft.com/k8se/quickstart:latest`. Then `az acr build`. Pass 2 sets `containerImage=<acr>.azurecr.io/claims-backend:<sha>` in `main.bicepparam` (a committed, non-secret value) and redeploys; only the Container App changes. A third what-if after pass 2 is the idempotence check (§7).

---

## 2. Postgres Flexible Server

| Setting | Value | Why |
|---|---|---|
| API version | `Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01` | Latest GA (preview versions exist; not used). |
| Major version | `17` | Matches Neon (17 + pgvector 0.8.0): same engine, same migrations, same extension version. 18 is not requested; nothing in the stack needs it and parity with the other deployment is worth more. |
| SKU | `Standard_B1ms`, tier `Burstable` | Prompt's choice; free-account allowance covers 750 h/month. |
| Storage | 32 GiB, auto-grow disabled | Minimum; the dataset is kilobytes. |
| Backup | 7 days, locally redundant | Minimum retention; geo-redundancy is a production concern. |
| High availability | Disabled | B1ms does not support it; not needed. |
| `azure.extensions` | `VECTOR` | Allow-lists `CREATE EXTENSION vector`, which migration 0001 runs. Dynamic parameter; no restart. Set as a `configurations` child resource. |
| Firewall | Rule `AllowAzureServices` (`0.0.0.0`–`0.0.0.0`) + rule `DeployerClient` (`deployerClientIp`) | The consumption environment has no static egress IP without a VNet, so the Azure-services rule is the only way the Container App reaches the server. The client rule is for migrations and seeding from this machine. Public access is a documented Phase 9 gap (private endpoint). |
| Authentication | Password auth **enabled**, Entra auth **disabled** | **Decision: defer Entra auth for Postgres.** The app connects with a static `DATABASE_URL` through `psycopg`. Entra tokens expire hourly; honouring them means a token-refreshing connection path in `backend/db/connection.py` and `azure-identity` as a dependency. That is a code and dependency change, which the prompt forbids for 9.1 beyond the test guard, and `azure-identity` is explicitly scheduled for 9.3. Recorded as a remaining gap. |
| Admin credential | Login `claimsadmin`; password generated at deploy (`openssl rand -hex 24`) and written to Key Vault as `postgres-admin-password` by Bicep | Hex alphabet avoids percent-encoding in the connection string. The password is also composed by Bicep into the `database-url` secret: `postgresql://claimsadmin:<pw>@<fqdn>:5432/agentic_claims?sslmode=require`. Azure enforces TLS; `sslmode=require` makes the client refuse plaintext. |

The `agentic_claims` database is a `databases` child resource so the whole data tier is in Bicep. Note for the stop/start scripts (§8): Azure **automatically restarts** a stopped Flexible Server after seven days; the README says so.

---

## 3. Container image

### 3a. `torch` CPU pin — a dependency-resolution change, flagged

Not a new dependency. `pyproject.toml` gains:

```toml
[tool.uv.sources]
torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]

[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true
```

then `uv lock`. The marker confines the change to Linux: macOS development keeps resolving from PyPI exactly as today. `uv.lock` changes for the Linux branch only (the `nvidia-*` and `cuda-*` entries disappear). Side effect worth having: GitHub Actions on `ubuntu-latest` stops downloading CUDA libraries, so CI gets faster. Verification: `grep -c 'name = "nvidia-' uv.lock` is `0` after relock; the local suite still passes.

### 3b. `Dockerfile` (repo root) and `.dockerignore`

Repo root rather than `backend/`, because `pyproject.toml`, `uv.lock` and the `backend/` package all live at the root and the app's data paths (`backend/data/sample_policy.txt`, `backend/app/escalation/policy.yaml`) are repo-relative. `WORKDIR /app` reproduces the repo-root layout.

```
Stage 1 "builder"  python:3.11-slim-bookworm
  COPY --from=ghcr.io/astral-sh/uv:0.9.11 /uv /usr/local/bin/uv        # pinned to the local uv version
  ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
  COPY pyproject.toml uv.lock README.md ./                              # README.md: hatchling reads it for package metadata
  RUN uv sync --frozen --no-dev --no-install-project                    # dependency layer, cached independently of source
  COPY backend/ backend/
  RUN uv sync --frozen --no-dev --no-editable                           # installs the project → importlib.metadata reports 0.9.0 for /health
  ENV HF_HOME=/opt/hf
  RUN .venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

Stage 2 "runtime"  python:3.11-slim-bookworm
  RUN useradd --system --uid 10001 --no-create-home app
  WORKDIR /app
  COPY --from=builder --chown=app:app /app /app                         # .venv + backend/ + pyproject
  COPY --from=builder --chown=app:app /opt/hf /opt/hf                   # baked model, readable by the non-root user
  ENV HF_HOME=/opt/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
  USER app
  EXPOSE 8000
  CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Design decisions:

- **`HF_HUB_OFFLINE=1` at runtime** makes "no network access to Hugging Face" enforced rather than incidental: if the baked model were ever missing, the process fails loudly at first use instead of silently fetching. This is the defensive-programming rule applied to the image.
- **Model name is literal in the `RUN` line**, matching `EmbeddingSettings.model_name`'s default. The two are interlocked exactly as the model name and dimension already are; a comment in the `Dockerfile` names the setting. (Reading it from `settings.py` at build time would require `DATABASE_URL` to instantiate `Settings`, which is the wrong coupling.)
- **Port is fixed at 8000**, the `api_port` default, because Container Apps configures `targetPort` rather than injecting `$PORT`. Stated under §12.
- **No `settings.yaml`** is copied; the image is configured by environment variables only, the same as Render.
- **`uv` pinned to 0.9.11** (the local version) so the lockfile semantics are identical in both places.

`.dockerignore` (allow-list style: deny everything, then re-admit what the image needs):

```
*
!pyproject.toml
!uv.lock
!README.md
!backend/
backend/tests/
backend/**/__pycache__/
backend/settings.yaml
```

That excludes `.git`, `.venv`, `node_modules`, `frontend/`, `docs/`, `diagrams/`, `infra/`, `scripts/`, `.env*`, `BUILD-PLAN.md`, `HANDOFF.md` and every other file by default, so no secret can reach the build context through a forgotten pattern.

### 3c. Build

```bash
TAG="$(git rev-parse --short HEAD)"
az acr build --registry "$ACR_NAME" --image "claims-backend:${TAG}" --image claims-backend:latest --platform linux/amd64 --file Dockerfile .
```

Tag scheme: short git SHA, plus a moving `latest` for convenience only (the Container App always references the SHA tag, so a rollback is a redeploy with the previous SHA). `--platform linux/amd64` matches the Container Apps consumption hosts and the CPU wheel selected in §3a. The ACR build agent has outbound internet (needed for PyPI anyway), so the Hugging Face fetch runs there; if it is rate-limited the agent retries, and if it still fails the report records it and the HF-token option is raised as a separate flagged change.

**Expected image size:** roughly 1.3 GB uncompressed (slim base ~150 MB, CPU torch ~450 MB installed, transformers/numpy/tokenizers ~350 MB, model 133 MB, app and venv remainder). Compressed in ACR, 500–700 MB. The report records the measured figure from `az acr repository show-manifests`. Against the CUDA path this is a four-to-five-fold reduction, and it is why §3a is in scope.

---

## 4. Container App

| Setting | Value |
|---|---|
| API version | `Microsoft.App/containerApps@2026-01-01` (GA) |
| Environment | `cae-claimsai-dev`, consumption-only, logs to `log-claimsai-dev` |
| Identity | `UserAssigned` → `id-claimsai-backend-dev` (§5 ⚠) |
| Registry | `<acr>.azurecr.io`, `identity: <identity resource id>` (no admin credentials; ACR admin user disabled) |
| Ingress | external, `targetPort: 8000`, HTTPS only, `transport: auto` |
| Revision mode | `Single` |
| Secrets | `database-url`, `anthropic-api-key`, `mistral-api-key` — each `keyVaultUrl: <vault>/secrets/<name>` with `identity: <identity resource id>` |
| Env vars | `DATABASE_URL`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY` via `secretRef`; `CORS_ALLOWED_ORIGINS` as a plain value (JSON list, the form pydantic-settings parses for a `list[str]` field, mirroring the Render value); `ENVIRONMENT=prod`; `LOG_LEVEL=INFO` |
| Resources | `cpu: 1.0`, `memory: 2Gi`. Render's 512 MB OOM-killed the in-process embedder; torch plus the model comfortably needs ~1 GiB resident, and 2 GiB leaves headroom for concurrent pipeline runs. |
| Scale | `minReplicas` from parameter (default **0**), `maxReplicas: 1` (a second replica would double LLM concurrency against the same Anthropic key for no demo benefit) |
| Probes | Liveness `GET /health` every 30 s; readiness `GET /health` every 10 s; startup `GET /health`, 5 s period, 24 failures (two minutes), covering image pull plus Python import. `/health` does not touch the database or the model, so it reports process liveness, which is what the probes should measure. |

**`minReplicas` decision.** Default `0`. Cold start with a ~600 MB compressed image is image pull plus interpreter start plus the lazy orchestrator build on first pipeline call; expect 20–40 s before the first request after idle completes. At `1`, a warm replica of 1 vCPU / 2 GiB is about 2,600 vCPU-seconds an hour; the monthly free grant (180,000 vCPU-s) covers roughly 50 warm hours, after which it costs on the order of €30/month continuously. So: `0` by default, `1` while a demo window is open, toggled by the §8 scripts. This matches the prompt's suggested recommendation.

---

## 5. RBAC — ⚠ decision needed on the identity type

**Recommendation: a user-assigned managed identity** (`identity.bicep`), not system-assigned. Reason, from §0: Container Apps validates Key Vault secret references and the ACR pull identity when the app resource is created, and a system-assigned identity does not exist until that same creation completes. The known workarounds are a two-deployment dance (create the app with a placeholder, assign roles, redeploy with the references) or temporarily enabling ACR admin credentials, both of which make what-if lie about the end state. A user-assigned identity is created first, granted its two roles, and the app is created once, with every reference valid. **The security story is identical**: one identity, exactly two data-plane grants, no secret anywhere but the vault, a compromised container can read only what it was granted. It is also the production-realistic pattern (identities outliving the workloads that use them). The prompt says "system-assigned"; this is the one place the plan proposes otherwise.

| # | Principal | Role | Scope | Why |
|---|---|---|---|---|
| 1 | `id-claimsai-backend-dev` | `Key Vault Secrets User` | the vault | Resolve the three `keyVaultUrl` secret references at revision start. Read-only, secrets only. |
| 2 | `id-claimsai-backend-dev` | `AcrPull` | the registry | Pull `claims-backend:<sha>` without admin credentials (ACR admin user stays disabled). |
| 3 | Dermot's user (`deployerPrincipalId`) | `Key Vault Secrets Officer` | the vault | The vault uses the RBAC permission model; subscription Owner does **not** confer data-plane secret access. This grant is what lets `az keyvault secret show --name database-url` work for the §6 bootstrap. Bicep writes the secrets through the control plane, which Owner already covers. |

Nothing at subscription scope is created. Dermot is already Owner of the free-trial subscription, which covers `az group create`, the deployment, `az acr build` (`scheduleRun`) and the stop/start commands. Role assignments are Bicep resources with deterministic `guid()` names, so they are idempotent.

---

## 6. Data bootstrap

Run from this machine after pass 2, with `DATABASE_URL` set for one shell session only (never written to `.env`):

```bash
export DATABASE_URL="$(az keyvault secret show --vault-name "$KV_NAME" --name database-url --query value -o tsv)"
python3 -c 'import os,urllib.parse as u; print("DATABASE_URL host:", u.urlparse(os.environ["DATABASE_URL"]).hostname)'   # hostname-only echo, as with Neon
uv run alembic --config backend/alembic.ini upgrade head
uv run python -m backend.data.index_policy
uv run python -m backend.data.seed_claims --allow-truncate
```

Expected: `Indexed 12 chunks …` and `Inserted 9 claims (3 scripted + 6 background).` Confirmed afterwards with `SELECT count(*)` on `policy_chunks` and `claims` via `psql` over TLS, recorded in the report.

**Test-layer change (the only one).** `backend/tests/conftest.py`: `_NEON_HOST_SUFFIX` becomes `_DEPLOYED_HOST_SUFFIXES = (".neon.tech", ".postgres.database.azure.com")`; `_is_neon_host` becomes `_is_deployed_host`, matching any suffix case-insensitively; the three error messages and `_README_POINTER` say "deployed-database host" and name both patterns; the `clean_db` defence-in-depth check uses the renamed helper; the module comment gains the Azure sentence. `backend/tests/test_db_isolation.py` gains `_AZURE_URL` / `_AZURE_HOST` constants and two tests: the explicit `TEST_DATABASE_URL` path and the `DATABASE_URL` fallback path both refuse the Azure host, asserting the host name and the README pointer appear in the message, and the upper-cased URL is also refused. Existing Neon tests are unchanged. Discriminator: reverting the suffix tuple to Neon-only fails both new tests; this is proven and recorded in the report.

---

## 7. Verification (recorded in the report and the build log)

1. `curl https://<fqdn>/health` → `{"status":"ok","version":"0.9.0"}`.
2. `uv run python scripts/verify-demo-scenarios.py --backend https://<fqdn>` — the script, not the Vercel frontend, as the prompt leans; it needs no frontend change and Vercel stays pointed at Render. Expected: `settled` with no rules; `awaiting_human` with `settlement_over_ceiling`; `awaiting_human` with `guardrail_failed`.
3. Audit depth and chain, which the script does not check: `GET /api/audit?correlation_id=<cid>` for each run → seven entries; the existing chain-verification endpoint reports the chain intact; every `llm_call.provider` is `anthropic` and `requested_model` is the Haiku id.
4. `az deployment group what-if` after pass 2, with `minReplicas` set to the value the scripts last applied → "No changes".
5. `scripts/azure-stop.sh` then `scripts/azure-start.sh`, then `/health` again → `0.9.0`.
6. **Halt rule.** A scenario landing in the wrong terminal state halts verification for diagnosis, per the prompt. Same provider as Render, so a difference is environmental.

---

## 8. Cost, stop/start and teardown

`scripts/azure-stop.sh`: `az postgres flexible-server stop` + `az containerapp update --min-replicas 0`. `scripts/azure-start.sh`: `az postgres flexible-server start` (waits for `Ready`) + `az containerapp update --min-replicas 1`, then polls `/health`. Both read resource names from `az deployment group show … --query properties.outputs`, so no name is hardcoded; both follow sanitise → validate (logged in, group exists) → abort → execute. Requires the `containerapp` CLI extension (step 0). Caveat documented: a stopped Flexible Server auto-starts after seven days; `azure-stop.sh` prints this.

The scripts move `minReplicas` outside Bicep, which what-if will report as drift. Accepted and documented: the idempotence check is run with the `minReplicas` parameter matching the current state. The alternative, redeploying Bicep to toggle one integer, is slower than the thing it replaces.

**Teardown** (README): `az group delete -n rg-claimsai-dev --yes` then `az keyvault purge --name <kv>` (soft-delete is mandatory; without the purge the vault name is blocked for 90 days and a re-deploy fails). Purge protection is deliberately **off** on the vault for this reason.

| Line | Monthly estimate | Note |
|---|---|---|
| Postgres B1ms + 32 GiB | **€0** for 12 months on the free account; otherwise ~€13 | 750 free hours covers 24×31. Stopped servers still bill storage. |
| ACR Basic | ~€4.50 | Flat. 10 GiB included; one ~600 MB image. |
| Container Apps, `minReplicas 0` | ~€0 | Free grant covers demo-hour usage. |
| Container Apps, `minReplicas 1` continuously | ~€30 | Why the default is 0. |
| Log Analytics | €0 | 5 GB/month free; the app logs kilobytes. |
| Key Vault | <€0.10 | Per 10k operations. |

Within the $40/month budget alert in the default posture; the spending limit on the free trial means an overrun suspends rather than bills.

---

## 9. Docs

- **`README.md`**: new *Azure deployment* section after *Live demo*: prerequisites (subscription, `az login`, `az bicep install`, `containerapp` extension, provider registration), deploy (two-pass sequence), bootstrap, verify, stop/start, teardown. The stale *Live demo* line (`0.7.0`, "set after deploy") is corrected while there. The *Production architecture* table's "Development (prototype)" column stays; a one-line note points at the new stack-reference section.
- **`docs/architecture-stack-reference.md`** — **decision: no third column.** The 37-row table is already wide, and most rows are identical between the two prototype deployments. Instead: (a) a dated note under the *Stack at a glance* table, in the style of the Phase 8.6 note, saying the prototype has run on Azure since 1 October 2026; (b) a new section **"Prototype on Azure (Phase 9)"** after *Development stack — detailed*, holding a compact table of only the rows that differ (backend hosting, data tier, secrets, identity, IaC, region, container build) between Render/Neon/Vercel and Azure, plus the Azure resource inventory; (c) a new section **"Remaining gaps to the production target"** listing the prompt's out-of-scope items (VNet/private endpoints, APIM, Service Bus, Durable Functions, SQL MI + Ledger, AI Search, Entra human sign-in, Entra Postgres auth, Langfuse, Document Intelligence, LoRA, Azure DevOps). The *Production (Target)* column and sections are untouched.
- **`infra/azure-devops-pipeline.yml`**: header comment only — `infra/bicep/main.bicep` now exists and is the prototype's real IaC; the pipeline remains a reference. The `0.7.0` version strings in it are left as they are (illustrative pipeline, not run).
- **`docs/BACKLOG.md`**: Phase 8.7 heading annotated "queued after Phase 9"; the deep-link 404 item annotated "resolved by SWA `navigationFallback` in Phase 9.2"; a *Phase 9 follow-ons* note for Entra auth for Postgres and the Hugging Face token question if it arises.
- **`docs/build-log.md`**: Phase 9.1 entry with the resource inventory, the RBAC table, measured image size, bootstrap counts, the three-scenario table, what-if result and stop/start result.
- **`CLAUDE.md`**: Tech Stack *Hosting & CI* gains the Azure deployment; *Current Status* rewritten for 9.1; new *Architectural Decisions* bullet: **two deployment targets; Render/Vercel/Neon remains canonical for demos until Azure has passed the full three-scenario verification twice** (the prompt's retirement rule), after which the bullet is revisited. The *Local dev environment* bullet's pytest-guard sentence gains the Azure host pattern.
- **`docs/prompts/19-…-report.md`** after execution; this plan gets its `## Approval` footer.

---

## 10. Version

`pyproject.toml` `0.8.6.1 → 0.9.0`. `/health` picks it up from package metadata; the Docker image installs the project non-editable, so the container reports it too. 9.2 and 9.3 are `0.9.1` and `0.9.2`.

---

## 11. Execution order

**Step 0 — local tooling and subscription preparation (no resources, no code):** `az bicep install`; `az extension add --name containerapp`; `az provider register` for the five namespaces and wait for `Registered`; `az postgres flexible-server list-skus -l northeurope` to confirm `Standard_B1ms` is offered to this subscription (fallback `westeurope`, which would be raised before continuing).

**Step 1 — code and docs (commit + push before any deployment):** §3a pin + relock; version bump; `Dockerfile` + `.dockerignore`; Bicep files + `infra/bicep/README.md`; `scripts/azure-stop.sh` / `azure-start.sh`; conftest guard + tests; docs per §9 except the parts that need deployed facts. Gates: `uv run pytest` (expect 375 passed, 7 skipped: +2 tests), `ruff`, `mypy`, `az bicep build infra/bicep/main.bicep` (lint), `az bicep lint`. Grep the diff for key- or connection-string-shaped strings before committing.

**Step 2 — operational, with Dermot present:** `az group create`; what-if; pass 1; `az acr build`; pass 2; what-if idempotence; §6 bootstrap; §7 verification; stop/start test. Then the build-log entry, the report, `CLAUDE.md`, the `containerImage` tag in `main.bicepparam`; commit and push.

---

## 12. Dependencies and interface stability

**Dependencies:** none added. One **resolution change** (§3a): `torch` from the PyTorch CPU index on Linux. Flagged here for confirmation; `uv.lock` changes on its Linux branch only.

**Interface stability: none.** Same schema, migrations, audit payloads and HTTP shapes. `backend/settings.py` and `settings.yaml.template` are untouched: the image configures the model cache through `HF_HOME`, which the library reads, not through a setting. Start-up changes from Render's `uv run uvicorn … --port $PORT` to a fixed `--port 8000` inside the image because Container Apps configures `targetPort` rather than injecting `$PORT`; the app's `api_port` default already is 8000, so nothing in the app changes.

---

## 13. Risks

| Risk | Likelihood | Handling |
|---|---|---|
| B1ms not offered to the free trial in North Europe | Low | Step 0 checks before anything is created; fallback West Europe, raised first. |
| Hugging Face 429 during `az acr build` | Low | Library retries; on persistent failure, halt and raise the token option as a flagged change. |
| Key Vault name soft-delete collision on re-deploy after teardown | Certain unless purged | Teardown includes `az keyvault purge`; purge protection off. |
| Postgres auto-restart after 7 days stopped | Certain if left 7 days | Documented; free allowance makes it cost-neutral for 12 months. |
| what-if drift from `minReplicas` toggling | Expected | Documented in §8; idempotence verified with matching parameter. |
| Container Apps revision fails to start because a KV reference is unresolvable | Low with user-assigned identity | Revision provisioning error surfaces in `az containerapp revision list`; the ordering in §5 is what prevents it. |
| Scenario lands in the wrong state on Azure | Low | Halt rule (§7.6). |

---

## 14. Optional enhancements (clearly labelled; not in scope unless approved)

- **`scripts/azure-deploy.sh`** wrapping step 2's command sequence with the same sanitise → validate → abort → execute discipline as the stop/start scripts. The `.bicepparam` + `readEnvironmentVariable()` design already keeps secrets off the command line, so this is convenience, not safety.
- **`render.yaml` `envVars` inventory** (existing backlog item) — Phase 9.1 makes the same four-variable contract explicit on the Azure side; mirroring it in `render.yaml` would document both deployments identically. Not touched in 9.1 because the prompt forbids changes on Render.
- **Pin `pgvector/pgvector:pg17` in CI** to match both deployed databases (CI is on `pg16` today). One-line change; not in 9.1's scope.

---

## Decisions requested at the approval gate

1. **⚠ Identity type (§5):** user-assigned managed identity (recommended) instead of the prompt's system-assigned wording.
2. **⚠ `torch` CPU index pin (§3a):** a `pyproject.toml` / `uv.lock` resolution change, Linux-only, flagged under dependency discipline.
3. **⚠ Entra authentication for Postgres (§2):** deferred, password auth only in 9.1, recorded as a gap.
4. Region `northeurope`, prefix `claimsai`, environment suffix `dev`, `minReplicas` default `0`.
5. Any of the §14 optional items.

---

## Approval

**Approved by:** Dermot Copps

**Verbatim approval message:**

> 9.1 plan approved. Decisions: (1) user-assigned identity, yes; (2) torch CPU pin, yes — confirm macOS resolution unchanged after relock; (3) Entra Postgres auth deferred, yes; (4) northeurope / claimsai / dev / minReplicas 0, yes; (5) take scripts/azure-deploy.sh and the CI pg17 pin; leave render.yaml on the backlog.
>
> One addition: if step 0's list-skus doesn't offer Standard_B1ms in northeurope, stop and report before any fallback — don't switch region on your own.
>
> Proceed with step 0 and step 1 (tooling, code, docs, tests, commit, push). Stop before step 2 and tell me when the code is pushed — I'll be present for the deployment.

**Amendments at the gate:**
- §14 optional items: `scripts/azure-deploy.sh` and the CI `pgvector/pgvector:pg17` pin are **in scope**; the `render.yaml` env inventory stays on the backlog.
- §3a: the relock must be shown to leave the macOS resolution unchanged.
- §11 step 0 / §13: if `Standard_B1ms` is not offered in `northeurope`, stop and report; no region fallback without a further decision.
- Execution is split: steps 0 and 1 now, step 2 with Dermot present.

**Approved at:** 2026-10-01T12:47:35Z
