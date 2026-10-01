# Phase 9.1 — Report: Azure foundation deployed, bootstrapped and verified

Prompt: [`19-phase-9.1-azure-foundation-bicep-container-apps.md`](19-phase-9.1-azure-foundation-bicep-container-apps.md) · Plan: [`19-…-plan.md`](19-phase-9.1-azure-foundation-bicep-container-apps-plan.md) · 1 October 2026 · `0.8.6.1 → 0.9.0`

## Summary

The prototype runs on Azure. Bicep provisioned the whole resource group in two passes, the backend image was built in the registry, the database was bootstrapped from the deploying machine, and **all three scripted scenarios reached their expected terminal states** with seven audit entries each on a verified chain. The stop/start round trip brought the deployment back with its data intact. This is the **first of the two verification passes** required before retiring Render / Neon is considered; Render / Vercel / Neon is unchanged and remains canonical for demos.

One acceptance criterion was not met as written: the idempotence what-if does not print "No changes". Every reported line was checked against live state and none is a pending change; Dermot accepted it as verified noise.

## Deployed resources

**URL:** `https://ca-claimsai-dev-backend.victorioushill-60f56bb8.northeurope.azurecontainerapps.io`

Resource group `rg-claimsai-dev`, North Europe:

| Resource | Name |
|---|---|
| User-assigned managed identity | `id-claimsai-dev-backend` |
| Log Analytics workspace | `log-claimsai-dev` |
| PostgreSQL Flexible Server (17.11, `Standard_B1ms`, 32 GiB, pgvector 0.8.2) | `psql-claimsai-dev-ojemo` |
| Container Registry (Basic, admin user disabled) | `acrclaimsaidevojemo` |
| Key Vault (RBAC mode, purge protection off) | `kv-claimsai-dev-ojemo` |
| Container Apps environment (consumption) | `cae-claimsai-dev` |
| Container App (1 vCPU / 2 GiB, 0–1 replicas) | `ca-claimsai-dev-backend` |

Image: `acrclaimsaidevojemo.azurecr.io/claims-backend:967a348`, `linux/amd64`, 519 MB in the registry, built in 3 min 21 s by `az acr build`.

RBAC: the managed identity holds *Key Vault Secrets User* on the vault and *AcrPull* on the registry; the deploying user holds *Key Vault Secrets Officer* on the vault. No subscription-scope assignment.

## Files

Step 1 (commit `967a348`):

| File | Change |
|---|---|
| `infra/bicep/main.bicep`, `main.bicepparam`, `modules/{identity,monitoring,postgres,acr,keyvault,containerapps}.bicep`, `README.md` | New. The whole Azure deployment as code. |
| `Dockerfile`, `.dockerignore` | New. Two-stage `uv` build, non-root, embedding model baked, allow-list context. |
| `scripts/azure-common.sh`, `azure-deploy.sh`, `azure-start.sh`, `azure-stop.sh` | New. |
| `pyproject.toml`, `uv.lock` | `0.9.0`; `torch==2.11.0` from the PyTorch CPU index on Linux only. |
| `backend/tests/conftest.py`, `backend/tests/test_db_isolation.py` | Deployed-host guard extended to `*.postgres.database.azure.com`; 2 new tests. |
| `.github/workflows/ci.yml` | Postgres service image pinned to `pg17`. |
| `README.md`, `docs/architecture-stack-reference.md`, `infra/azure-devops-pipeline.yml`, `docs/BACKLOG.md`, `CLAUDE.md` | Azure deployment documented. |

Step 2 (this commit):

| File | Change |
|---|---|
| `docs/build-log.md` | Phase 9.1 entry: inventory, RBAC, what-if noise categories, bootstrap counts, verification table, cold start, round trip. |
| `README.md`, `infra/bicep/README.md` | Idempotence comment: "no real changes (verified against live state)". |
| `scripts/azure-stop.sh` | Header comment only: describes the cooldown drain. No behaviour change. |
| `docs/BACKLOG.md` | Phase 9 status; new 9.x follow-on (wait for zero replicas before stopping Postgres); one verification pass recorded. |
| `CLAUDE.md` | Current Status. |
| `docs/prompts/19-…-report.md` | This report. |

No application code changed in step 2. No interface change. No new dependency.

## Tests

**375 passed, 0 failed, 7 skipped** (373 → +2), re-run at the end of step 2, along with `ruff check .` and `uv run mypy backend` (110 files), both clean. `shellcheck` is not installed on this machine and was not run; all four scripts pass `bash -n`.

Discriminator proof for the guard tests (applied, observed, reverted, file confirmed byte-identical afterwards): with `_DEPLOYED_HOST_SUFFIXES` reverted to `(".neon.tech",)`, `test_guard_fires_on_azure_test_url` and `test_guard_fires_on_azure_database_url_fallback` both fail with `DID NOT RAISE`; the other three tests in the file pass.

## Deployment sequence

| Step | Result |
|---|---|
| Pass 1, `deploy` | `claimsai-dev-967a348-20261001T160005Z`, succeeded 16:10:22Z |
| `build` | ACR run 16:48:49Z → 16:52:10Z, succeeded |
| `what-if <image>` (preview) | 1 create (the Container App); 3 noise "modify"; 12 no change; 2 unsupported |
| Pass 2, `deploy <image>` | `claimsai-dev-967a348-20261001T170755Z`, succeeded 17:11:54Z |
| `what-if <image>` (idempotence) | 4 noise "modify"; 12 no change; 2 unsupported |

Pass 1 and the build were run by Dermot; pass 2 onward ran in the Claude Code session on his `az login`.

## The idempotence what-if

It reports `4 to modify`, in three categories, none a real change:

1. **Probe order.** Template: Startup, Readiness, Liveness. Azure returns: Liveness, Readiness, Startup. what-if compares arrays by index; the live probe values equal the template's.
2. **Unresolved `reference()` expressions.** The registry server, three Key Vault secret URLs and the Log Analytics `customerId` are printed as `live value => "[reference(...)]"`; the live values are what the expressions resolve to.
3. **Server-defaulted properties the template does not declare**, shown as deletions (for example `storage.iops`, `peerAuthentication`, `anonymousPullEnabled`, `runningStatus`). An incremental deployment does not remove them. Three of the four resources showed these lines in the preview, before pass 2.

The 2 "unsupported" entries are the identity's two role assignments, whose names depend on a `principalId` unknown until deployment. The full line-by-line list is in the build log.

## Bootstrap

| Step | Expected | Actual |
|---|---|---|
| Hostname echo | Azure host only | `psql-claimsai-dev-ojemo.postgres.database.azure.com` |
| `alembic upgrade head` | head | `0002_audit_human_agent (head)` |
| `index_policy` | 12 | 12 chunks, 2388 tokens |
| `seed_claims --allow-truncate` | 9 | 9 claims (3 scripted + 6 background) |

The URL lived in one shell process and was never written to `.env`.

## Verification

`/health` → `{"status":"ok","version":"0.9.0"}`. **Cold start 28.0 s** from zero replicas; 0.06 s warm.

| | Auto-approve ($85k) | Threshold ($850k) | Guardrail ($1.4M) |
|---|---|---|---|
| Correlation id | `08d514f2-5d47-4d0a-8f58-ddb82a691950` | `9a92333f-cc4a-4f05-b76f-f509be3b7759` | `c66b9f3c-0f4a-4fab-9bdc-2fe30c49e8f6` |
| Terminal status | `settled` ✓ | `awaiting_human` ✓ | `awaiting_human` ✓ |
| Fired rules | none ✓ | `settlement_over_ceiling` ✓ | `guardrail_failed`, `settlement_over_ceiling` ✓ |
| Audit entries | 7 ✓ | 7 ✓ | 7 ✓ |
| Providers / models | all `anthropic`, `requested_model` = `model` = `claude-haiku-4-5-20251001`, `prompt` present ✓ | same ✓ | same, except `settlement_estimate`: `demo_fixture: true`, `provider = "demo_fixture"`, no `prompt` / `model` / `requested_model` ✓ |

**Chain:** `{"ok": true, "rows_checked": 21, "first_break": null}` — whole-ledger, 3 × 7 rows.

The three runs took 28 s in total. They were driven by `scripts/verify-demo-scenarios.py`, not the UI: Vercel still points at Render, so the Azure backend has not yet been exercised from the frontend.

## Stop/start round trip

`azure-stop.sh` took 261 s (Postgres `Stopped`, `minReplicas` 0). `azure-start.sh` took 173 s (Postgres `Ready`, `minReplicas` 1, `/health` 200 on the third poll). Re-reading the ledger through the restarted app returned 12 claims, seven entries per run and a verified chain over 21 rows.

## Deviations from the plan

1. **what-if idempotence (§7.4).** "No changes" is not printed; accepted as verified noise. Both READMEs corrected.
2. **`containerImage` in `main.bicepparam` (§11, step 2).** Not written. The parameter file reads `CONTAINER_IMAGE` from the environment, so the image is a script argument and nothing is committed per deploy.
3. **pgvector 0.8.2, not 0.8.0.** The plan expected an exact match with Neon. No behavioural difference observed.
4. **Stop script (§8).** `minReplicas = 0` does not stop a running replica; it drained about five minutes after its last request, after Postgres had stopped. Comment corrected; the behavioural fix is in the backlog.
5. **Start script exit code not captured** in the round-trip run (a wrapper slip). Success rests on the script's final `healthy after 3 attempt(s)` line and the state checks.

## Guard clauses added beyond the spec

None in the repository. Operationally, the bootstrap was run with two guards not in the README procedure: abort if the Key Vault secret comes back empty, and abort unless the hostname resolved through `Settings()` equals the expected Azure host. The first matters because an empty `DATABASE_URL` falls back to `.env`, where `--allow-truncate` would hit the local dev database.

## Suggestions (not built)

- **Put the two bootstrap guards into the README procedure** (or a `scripts/azure-bootstrap.sh`), so the protection does not depend on who runs it.
- **Reorder the probes in `containerapps.bicep`** to Liveness, Readiness, Startup. It removes the only what-if noise category that is ours to remove, and needs no image rebuild.
- **Run the second verification pass through the UI**, with the frontend pointed at the Azure backend, so the pass that unlocks the Render / Neon decision also covers CORS and the SSE stream. Phase 9.2 (Static Web Apps) is the natural point.
- **Install `shellcheck`** and run it over `scripts/azure-*.sh`.
