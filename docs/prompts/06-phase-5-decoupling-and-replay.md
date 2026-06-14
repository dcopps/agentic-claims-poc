# Prompt 06 — Phase 5: Decoupling and Replay

## Read first

Before doing anything else, read these files:

- `CLAUDE.md` — global standards, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 5.
- `docs/prompts/05-phase-4-pipeline-orchestrator-report.md` — what Phase 4 delivered and the interfaces it locked: `PipelineResult`, `EscalationDecision`, `PipelineState`, the six SSE event names and their payloads, the pipeline-level audit steps (`pipeline_started`, `escalation_decision`, `pipeline_settled`/`pipeline_awaiting_human`/`pipeline_aborted`), and the two endpoints (`POST /api/pipeline/run/{claim_id}` and `GET /api/pipeline/stream/{correlation_id}`).
- `backend/app/orchestrator/pipeline.py` — the orchestrator surface this phase builds on top of (the public `run(claim_id, *, correlation_id=None, emit=None)` signature).
- `backend/app/orchestrator/models.py` and `backend/app/escalation/models.py` — the typed contracts Phase 5 reads/writes.
- `backend/app/api/pipeline.py` — the existing endpoints; Phase 5 adds new endpoints alongside, does not modify the locked ones.
- `backend/db/migrations/versions/0001_initial_schema.py` — the `claims` table already has a `status` column with a CHECK constraint enumerating the seven lifecycle values; no migration is needed to introduce statuses.
- `backend/data/seed_claims.py` — the nine seeded claims, three of them tagged with `scenario_tag`.
- `frontend/src/App.tsx` and `frontend/src/main.tsx` — the current placeholder UI. Phase 5 replaces it with a functional but unpolished pipeline UI.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. Plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts, system/user separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 5 of `BUILD-PLAN.md` — Decoupling and replay. By the end of this phase:

- A claim is **submitted** (persisted to `claims` with `status='received'`) **before** any agent fires. A new `POST /api/claims` endpoint is the synchronous submission step; the pipeline is then triggered separately via the existing `POST /api/pipeline/run/{claim_id}`. The two-step pattern simulates the production "Claims of Record receives the FNOL; Service Bus emits a `ClaimReceived` event that triggers the pipeline" decoupling.
- The orchestrator **updates `claims.status` as the pipeline progresses**, mapping each agent's completion to one of the lifecycle values (`extracted`, `coverage_verified`, `estimated`, `guardrail_checked`) and the terminal state (`settled` or `awaiting_human`) at finalisation. On abort, the status freezes at the last completed step.
- A **replay capability**: `POST /api/pipeline/replay/{claim_id}?variant=<name>` runs the pipeline again against the same claim with a configured variant (different prompt template, different model, or both). A **new correlation_id** is minted; the prior run is **never overwritten** in the audit vault. Both runs are queryable side-by-side.
- A **runs API** reconstructs a `PipelineResult`-shaped object for any past correlation_id from the audit_log (`GET /api/runs/{correlation_id}`), and a **runs list** returns every run that targeted a given claim (`GET /api/claims/{claim_id}/runs`).
- A **comparison API** returns the two reconstructed runs together for the frontend: `GET /api/runs/compare/{correlation_id_a}/{correlation_id_b}` (with a guard that both target the same claim).
- A **functional frontend** wired to the new endpoints: claim submission form, claim list with statuses, "Process Claim" / "Re-process with v2" buttons (each with a tooltip naming its production equivalent), an SSE-driven live progress strip, and a basic side-by-side comparison view. **Functional only — Phase 6 is the polish.**
- The three locked demo scenarios still pass end-to-end. The auto-approve and threshold scenarios reproduce live; the guardrail scenario remains forced via the integration test (Phase 7 demo polish addresses live reproducibility).

The per-phase preamble fix-up bundled into the same Phase 5 commit:

- Bump `pyproject.toml` version `0.4.0` → `0.5.0`. The `/health` `version` field then reads `0.5.0` after the Phase 5 push, confirming Phase 5 code is live.

## Current state of the project (for orientation)

Phase 4 delivered:

- `PipelineOrchestrator` at `backend/app/orchestrator/pipeline.py` with `run(claim_id, *, correlation_id=None, emit=None) -> PipelineResult`. Asyncio-agnostic; async machinery lives at the API edge.
- `EscalationPolicy` at `backend/app/escalation/policy.py` driven by `policy.yaml`. OR semantics; locked rule names.
- `PipelineEventBus` at `backend/app/orchestrator/event_bus.py` — in-process, per-correlation `asyncio.Queue`, buffered late-subscriber semantics.
- Two endpoints under `/api/pipeline/`: synchronous `run` and SSE `stream`.
- Three pipeline-level audit steps under `agent="orchestrator"`.
- 227 tests passing, 6 skipped, 0 failing; ruff and mypy clean.
- `/health` reports `version=0.4.0`.

The frontend is still the Phase 0 placeholder (a `backend: ok` probe in `App.tsx`). The `claims` table's `status` column has been defined since Phase 1 but no code currently writes to it past the default `'received'`.

The current API surface is read-only against pre-seeded claims; there is no submission path. The nine seeded claims include three tagged with `scenario_tag` for the locked demo scenarios.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering everything below.

### Cross-cutting design questions

Before describing the implementation, address these decisions in the plan. Each has a recommendation; either confirm it or argue back.

1. **Where does the claim-submission endpoint live and what is its body shape?**
   - Recommended: `POST /api/claims` in a new `backend/app/api/claims.py`. Request body is a typed `ClaimSubmission` Pydantic model carrying the **minimum fields necessary to drive the pipeline**: `claimant_name`, `policy_number`, `loss_date`, `reported_date`, `jurisdiction`, `narrative`, `claim_type`, `reported_amount`. The endpoint generates `claim_id` and `claim_number` server-side, inserts with `status='received'`, returns the typed `ClaimRecord` (the full row).
   - Open question for the plan: do we accept a `scenario_tag` in the body (lets the demo UI pre-tag a submitted claim) or reject it (only seeded claims may carry the tag)? Recommendation: **accept and validate**, so a demo-mode flow can submit a tagged claim.
   - Defensive guards: every text field length-bounded; `loss_date <= reported_date`; `reported_amount > 0`; `claim_type` must be a recognised value (read from a small Literal/enum populated from the existing market_data keys plus `flood`); `jurisdiction` non-empty after strip.

2. **Status lifecycle — who writes, when, and how?**
   - Recommended mapping (Phase 4 outcomes wired to the existing CHECK constraint values):

     | Trigger | New status |
     |---|---|
     | `pipeline_started` event | `received` → (no change; default) |
     | Doc-Parser `agent_completed` | `extracted` |
     | Validator `agent_completed` | `coverage_verified` |
     | Adjuster `agent_completed` | `estimated` |
     | Guardrail `agent_completed` | `guardrail_checked` |
     | `_finalise` with `decision.escalate == False` | `settled` |
     | `_finalise` with `decision.escalate == True` | `awaiting_human` |
     | Any abort path | (frozen at last completed status) |

   - The orchestrator writes the status update directly via a new `ClaimsRepository.update_status(claim_id, status)` call, opening its own connection (mirrors how pipeline-level audit entries are written). One status update per agent completion + one at finalisation.
   - **Replay implications**: a replay run on a claim already at `settled` or `awaiting_human` does **not** revert the status to `received`. It writes new audit entries under a fresh correlation_id but the claim's `status` column reflects the **most recent terminal outcome of any run**. The frontend reads the per-run status from the runs API, not from `claims.status`, for any UI element that displays a specific run.
   - Document the race semantics in the plan: a replay started while a prior run is still in flight is rejected with 409 (see question 3). The status column is single-writer per claim at any moment.

3. **Concurrent runs on the same claim — reject or queue?**
   - Recommended: **reject with 409 Conflict** if `claims.status` is not in a terminal state (`settled`, `awaiting_human`, or `received`-with-no-active-run). The "active run" check is "is there a `pipeline_started` audit entry without a corresponding terminal entry under the same correlation_id?" — implement as a simple SQL query in the runs repository, not as in-memory state.
   - Alternative (queueing) is over-engineered for the prototype; the production equivalent is Service Bus + Durable Functions handling concurrency. Document the alternative in the plan; pick rejection.

4. **Variant mechanism — where does "v2" live and what does it override?**
   - Recommended: a declarative `backend/app/orchestrator/variants.yaml` registering named variants. Schema:

     ```yaml
     version: 1
     variants:
       default:
         description: "Baseline configuration matching Phase 4."
         # No overrides — the orchestrator runs with the agents as constructed.
       v2_strict_validator:
         description: "Validator uses the strict prompt template; same model."
         validator:
           prompt_template: "validator_strict.md"   # under prompts/user/
       v2_haiku_validator:
         description: "Validator runs on Claude Haiku instead of Mistral."
         validator:
           model: "claude-haiku-4-5-20251001"
           provider: "anthropic"
     ```

   - The variant mechanism overrides on a per-agent basis: a `model`/`provider` swap (constructs a different `LLMProvider` for that agent only) and/or a `prompt_template` override (overrides the user-message template path; the system prompt stays unchanged unless an `instructions` field is added — recommend deferring instructions override to Phase 7).
   - Unknown variant name → `404 Unknown variant`. Variant identity is part of the audit record: an extra field `variant: str` on the pipeline-level `pipeline_started` audit entry and on the SSE `pipeline_started` event payload. **This is an interface-stability change**; flag explicitly in the plan that the locked Phase 4 contracts are *extended* by one field, default `"default"`, present for both fresh runs and replays.
   - The variant override path is read at the start of `POST /api/pipeline/replay/{claim_id}?variant=<name>` (or as an optional query parameter on the existing `POST /api/pipeline/run/{claim_id}?variant=<name>`). Recommend keeping the two endpoints separate even if both accept the variant parameter — the semantic difference (`run` is the first run; `replay` requires a prior terminal run) is worth a clean URL boundary.

5. **Runs reconstruction — how is a past `PipelineResult` rebuilt from the audit log?**
   - Recommended: a new `backend/app/runs/repository.py` with `RunsRepository.get_run(correlation_id) -> PipelineResult | None`. Implementation walks the audit_log entries under the correlation_id in `created_at` order and reconstructs:
     - `claim_id` from any entry.
     - `doc_parser_output`, `validator_output`, `adjuster_output`, `guardrail_output` from the agent-step entries (each agent's existing audit payload already carries enough fields; document any gaps in the plan).
     - `escalation_decision` from the `escalation_decision` audit entry.
     - `status`, `aborted_agent`, `error_type`, `completed_at` from the terminal entry.
     - `variant` from the `pipeline_started` entry.
   - Document gaps: if any audit payload does not currently carry enough information to reconstruct its part of `PipelineResult`, **enumerate** the gap in the plan and recommend either (a) extending the agent's audit payload (an interface-stability event in Phase 5, ack required) or (b) accepting the gap in the reconstructed result (with the field nulled). Prefer (a) and surface explicitly which agents need the extension.
   - **Constraint**: the reconstruction is a pure read from `audit_log`; the runs repository writes nothing.

6. **Runs and comparison API shape**
   - `GET /api/runs/{correlation_id}` → `PipelineResult` (200) or 404 if the correlation_id has no audit entries.
   - `GET /api/claims/{claim_id}/runs` → list of `RunSummary` (one per correlation_id targeting the claim): `correlation_id`, `variant`, `status`, `started_at`, `completed_at`, `escalate: bool | null`. Most recent first.
   - `GET /api/runs/compare/{correlation_id_a}/{correlation_id_b}` → typed `RunComparison`: both reconstructed `PipelineResult`s plus a small `diff_summary` (fields where the two differ: settlement amount, escalation decision, fired rules, guardrail pass/fail). Guard: both correlation_ids must reference the same `claim_id` or 400.

7. **Frontend scope — what's the minimum viable UI for Phase 5?**
   - **In scope (functional, not polished):**
     - Claim submission form: minimal fields (narrative, claim_type select, reported_amount, jurisdiction, policy_number, claimant_name, loss_date, reported_date). On submit, POST `/api/claims`. Three "Load demo claim" buttons that pre-fill from the locked scenarios (no backend change; client-side fixtures matching the seeded shapes).
     - Claims list: GET `/api/claims` (a new lightweight list endpoint — `GET /api/claims?limit=50` returning `ClaimRecord` rows ordered by `created_at` desc, status filter optional). Each row shows claimant, claim_type, reported_amount, status, and two action buttons: "Process" (POST `/api/pipeline/run/{claim_id}`) and "Re-process with v2" (POST `/api/pipeline/replay/{claim_id}?variant=v2_strict_validator`), the latter only enabled when `status` is `settled` or `awaiting_human`.
     - Pipeline progress strip: when a run is in flight, opens an `EventSource` to `/api/pipeline/stream/{correlation_id}` and shows the agent-by-agent progress (agent name, status indicator, brief summary, duration).
     - Comparison view: a separate page (or panel) that lists a claim's runs (most recent on top), lets the user pick two by correlation_id, and shows the side-by-side reconstructed results with the diff fields highlighted.
     - Tooltips on every button explaining the production equivalent. Phrasing in `frontend/src/copy/tooltips.ts` (one file, plain object) so Phase 6 polish can revise wording in one place.
   - **Out of scope (Phase 6 territory):**
     - Audit log viewer with chain-integrity check.
     - Agent test bench page.
     - Rich expandable panels per agent exposing the full prompt and response.
     - Visual polish, animation, design system.

8. **Tooltip phrasing — name the production equivalents explicitly**
   - "Submit Claim" → "In production, the FNOL form posts to the Claims of Record system, which emits a `ClaimReceived` event on Azure Service Bus."
   - "Process Claim" → "In production, this is triggered automatically by the `ClaimReceived` event handled by Azure Durable Functions."
   - "Re-process with v2" → "In production, this is triggered by a model-promotion event raised by the Azure DevOps deployment pipeline."
   - "Verify Chain" (if added) → "In production, the audit ledger is SQL Server with Ledger Tables; chain verification is a single `sys.sp_verify_database_ledger` call."
   - The text lives in `frontend/src/copy/tooltips.ts`; treat as locked at end of Phase 5 (Phase 6 may revise wording for polish).

### Pipeline orchestrator changes

The Phase 4 orchestrator is the spine; Phase 5 extends it minimally. The plan should specify:

- The `ClaimsRepository.update_status(claim_id, status)` call site inside each per-agent helper and `_finalise`/abort paths. Each status write opens its own short-lived connection (mirrors pipeline-level audit writes). Document the failure mode: a status write that fails (e.g., DB unreachable mid-pipeline) is logged but does not abort the pipeline — the audit_log entries are the trusted record; status is a denormalised UI convenience.
- The variant resolution at `run` entry: if `variant != "default"`, resolve overrides via the `VariantRegistry.resolve(variant_name) -> dict[AgentName, AgentOverride]`. Apply per-agent overrides (model swap or prompt-template swap) by constructing new agent instances *within `run`* for the duration of that run only. The lazy-built orchestrator from Phase 4 caches the default agents; variant agents are not cached.
- The `variant` field added to the `pipeline_started` audit payload and the `pipeline_started` SSE event payload (both as `variant: str` with default `"default"`). This is the interface-stability extension flagged in question 4.

### Replay endpoint details

- `POST /api/pipeline/replay/{claim_id}?variant=<name>` — async handler.
  - Guards: claim exists (404 if not); claim has at least one prior terminal run (409 if not — "nothing to replay"); no active run in flight on the same claim (409); variant is recognised (404 if not).
  - Mints a fresh correlation_id (or accepts an optional injected one for frontend SSE-first wiring, same pattern as `/run`).
  - Triggers `orchestrator.run(claim_id, correlation_id=..., emit=...)` in a threadpool, same shape as `/run`.
  - Returns the `PipelineResult` of the replay.

### Settings additions

- New top-level `variants_path: Path` on `Settings` pointing at `backend/app/orchestrator/variants.yaml` (or sub-model `PipelineSettings.variants_path`).
- No other new settings.

### Testing strategy

Aim ~40–50 new tests across:

- **`ClaimsRepository`** (~6): insert + read-back; status update transitions in each direction allowed by the CHECK; reject illegal transitions; list with filter.
- **`RunsRepository`** (~10): reconstruct from a full happy-path audit trace; reconstruct from an aborted trace; reconstruct from a replay trace (variant field); missing correlation_id returns None; gaps in agent payloads (if any) handled per the plan's policy.
- **`VariantRegistry`** (~6): load happy path; unknown variant → error; malformed YAML; override application (model swap; prompt swap; both); cross-checks the locked variant names ship.
- **Pipeline orchestrator** (~6 extending Phase 4): status writes fire at each agent completion; status freezes on abort; variant override constructs the right agent; status write failure is logged but does not abort the pipeline.
- **Claims API** (~6): submit happy path; validate each guard with a triggering test; list endpoint; one-claim GET.
- **Replay + runs + comparison APIs** (~10): replay happy path; replay on claim with no prior run → 409; replay during active run → 409; runs list; runs GET; compare happy path; compare on different claims → 400; compare on missing correlation_id → 404.
- **Frontend** (~12 component/integration via Vitest + Testing Library): submission form validation; list rendering and status badge; "Process" button POSTs and opens SSE; SSE event rendering; comparison view diff highlighting; tooltip text presence.
- **Integration scenarios** (3 reused from Phase 4 + 1 new replay scenario): the three demo scenarios continue to pass with the new orchestrator status writes in place. A new integration test exercises submit → run → replay-with-`v2_strict_validator` → compare, asserting both runs are in the audit vault and the comparison reveals the expected diff.

### CI changes

- The frontend test runner is already in place (Vitest). No new gated categories. The new gated `RUN_LLM_E2E_TESTS=1` replay test joins the existing gated tests; none run in CI.

### New dependencies — flag each one

If the plan introduces any, justify per the dependency-discipline standard. The expected answer is **at most one** (a frontend SSE polyfill is *not* needed — modern browsers ship `EventSource`; React + TanStack Query are already in `package.json`). If a new dep crops up, surface it before writing code.

### Risks and downstream impacts

**Locked at end of Phase 5** (Phases 6 and 7 consume these):

1. `ClaimSubmission`, `ClaimRecord`, `RunSummary`, `RunComparison` Pydantic shapes.
2. The new endpoints' paths, methods, and status-code policy.
3. The variants.yaml schema and the locked variant names that ship.
4. The status lifecycle mapping.
5. The `variant` field extension on Phase 4's `pipeline_started` audit payload and SSE event.
6. The tooltip copy in `frontend/src/copy/tooltips.ts`.

**Flagged risks / prototype simplifications:**

- Active-run detection via audit_log query is a single-process simplification; in production this would be a state-machine field. Document it.
- Status column denormalisation can drift from audit_log truth on partial failures; document the audit_log as authoritative.
- Replay variants in the prototype are limited to model/prompt swaps; richer variants (e.g. policy_yaml swap, different retrieval embedder) are deferred.

### Deployment steps requiring architect involvement

- Verify `/health` reports `version=0.5.0` after the Render auto-redeploy.
- Submit a new claim through the live UI; trigger a run; trigger a replay with `v2_strict_validator`; open the comparison view; confirm the diff fields make sense for the variant chosen.
- Open the SSE stream during a replay run and confirm the `variant` field appears on the `pipeline_started` event.

### Optional enhancements

Carried forward (still deferred): retry via `tenacity`; pricing-table population for `cost_usd`; real PII redactor; prompt golden-text fixtures; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings` fields.

Newly flagged for Phase 5:

- **Idempotent re-run guard on `/run`** — addressed by the active-run detection; promote the same check to a public `is_run_active(claim_id) -> bool` helper if Phase 7 needs it on the demo UI.
- **Claim revision history** — every status transition writes a row to a `claim_status_history` table. Deferred; the audit_log already records the underlying events; the dedicated history table is for ops convenience.
- **Variant audit extension** — extending other agent audit payloads to record which variant was active when they ran. Deferred to keep Phase 5's interface-stability changes small.

### Save the plan

Save the plan **before** asking me to review it. Write to:

```
docs/prompts/06-phase-5-decoupling-and-replay-plan.md
```

Top-level heading: `# Plan 06 — Phase 5: Decoupling and Replay`. Below that, the body of the plan.

After saving the file, point me at it and ask for my verdict. Do not write any other code or modify any other files yet.

## Step 2 — Approval or rejection

Same workflow as previous phases (per `docs/prompts/README.md`).

**If I approve** (any reply along the lines of "yes", "go ahead", "approved", or similar):

Append a horizontal rule and an `## Approval` section to the plan file. Order the section so the timestamp closes the file:

```
## Approval

**Approval message:** "<my exact approval message, quoted>"

---

**Approved by:** Dermot Copps
**Approved at:** <ISO 8601 timestamp in UTC>
```

Then proceed to Step 3.

**If I reject**, append a `## Rejection` footer, rename the file to `06-phase-5-decoupling-and-replay-plan-rejected-NN.md`, produce a revised plan as the fresh canonical file, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 5. Constraints from `CLAUDE.md` apply throughout:

- **Defensive programming** (sanitise → validate → abort → execute) on every function that takes input. Every guard has a triggering test that asserts on message content.
- **Function size:** 30 lines is a prompt to reconsider; 50 lines is a hard limit. Helpers stay small.
- **Settings hierarchy:** any new fields appear in both `backend/settings.py` and `backend/settings.yaml.template`. No hardcoded values. No magic numbers without a named constant and a comment.
- **Type hints** on every function signature (Python) and TypeScript everywhere on the frontend.
- **Tests:** every new function gets tests; every guard clause gets a triggering test asserting on error-message content.
- **Anonymisation:** the client name does not appear anywhere — code, comments, tests, fixtures, prompt files, variants file, tooltip copy, commit messages.
- **Security:** no new credentials introduced. No secret in any SSE event payload or in the runs API responses.
- **Externalised prompts:** the variant `v2_strict_validator` introduces a new user-template file at `backend/app/prompts/user/validator_strict.md`. Specify its persona/format in the plan; no inline f-string prompts.
- **System/user separation:** unchanged.
- **Interface stability:** Phase 5 extends the Phase 4 `pipeline_started` contracts by one field (`variant`). Acknowledge this explicitly in the plan.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.4.0` → `0.5.0`. The `/health` `version` field then reflects Phase 5 once deployed.

## Step 4 — Log

When the code work is complete, append a new entry to `docs/build-log.md`. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/06-phase-5-decoupling-and-replay.md`.
- Plan (approved): link to `docs/prompts/06-phase-5-decoupling-and-replay-plan.md`.
- Plan iterations: count of rejected revisions, with links to each.
- Report: link to `docs/prompts/06-phase-5-decoupling-and-replay-report.md`.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate, with breakdown by area.
- Issues discovered.
- Next: Phase 6 — Frontend polish.

## Step 5 — Write the report

Save the report to `docs/prompts/06-phase-5-decoupling-and-replay-report.md`. The report opens with a `## Summary` block in the established order:

- **Recap** — one sentence stating what's done plus one sentence stating what comes next.
- **Completed at** — ISO 8601 UTC timestamp.
- **Phase** — `5 — Decoupling and replay`.
- **Status** — Complete / Complete with deferrals.
- Links to the prompt, the approved plan, and the repository.
- CI status if relevant.

Body sections cover files created and modified by tier, test counts and pass rates with the breakdown above, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 5:

- Date: today's date in ISO format.
- Phase: "Phase 5 complete; Phase 6 next".
- What works: a one-line summary of the new capability (e.g. "Claims submission, processing, replay with a configured variant, and side-by-side comparison all work end-to-end. The frontend is functional but unpolished; Phase 6 is the polish.").
- What's next: "Phase 6 — Frontend polish."

## Step 7 — Git

Make a single commit covering all the Phase 5 work, with the commit message:

```
Phase 5: decoupling and replay

- POST /api/claims submission endpoint; status lifecycle written by orchestrator
- POST /api/pipeline/replay/{claim_id}?variant=<name> with a configured variant registry
- GET /api/runs/{correlation_id}, /api/claims/{claim_id}/runs, /api/runs/compare/{a}/{b}
- variants.yaml registry; v2_strict_validator and v2_haiku_validator shipped
- variant field extension on pipeline_started audit payload and SSE event
- Functional frontend: submission form, claims list, process/replay buttons, SSE progress, comparison view, production-equivalent tooltips
- ClaimsRepository, RunsRepository, VariantRegistry; new claims/runs APIs
- Defensive guards throughout, every guard with a triggering test
- pyproject.toml version bumped 0.4.0 -> 0.5.0
- Approved plan archived; build log entry appended; report written
- CLAUDE.md Current Status updated
```

Push to `main` so Render auto-deploys.

## Step 8 — Report back

Per the global "After coding" section, report:

- Files created and modified.
- Test count and pass rate, with breakdown by area.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend for follow-on work.

End the report with the action items I still need to handle:

- Verify the Render redeploy completes and `/health` reports `version=0.5.0`.
- Submit a new claim through the live UI; run it; replay it with `v2_strict_validator`; open the comparison view.
- Open the SSE stream during a replay and confirm the `variant` field on `pipeline_started`.
- Document any audit-payload extensions that were necessary on individual agents to support runs reconstruction (and flag whether Phase 4's interface-stability list needs an addendum).

## Save this prompt

Per the "Save every prompt" standing instruction in `CLAUDE.md`, save this prompt verbatim to `docs/prompts/06-phase-5-decoupling-and-replay.md` if it isn't already there.
