# Prompt 07 — Phase 6: Frontend Polish (and the Backend Endpoints That Polish Requires)

## Read first

Before doing anything else, read these files:

- `CLAUDE.md` — global standards, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 6.
- `docs/prompts/06-phase-5-decoupling-and-replay-report.md` — what Phase 5 delivered: the functional (unpolished) frontend, the claims/runs/replay/compare APIs, the variant mechanism, the status lifecycle, and the four audit additions (full Adjuster reasoning, truthful Validator provider/model, `variant` on `pipeline_started`).
- `frontend/src/App.tsx`, `frontend/src/components/*.tsx`, `frontend/src/hooks/*.ts`, `frontend/src/api/*.ts`, `frontend/src/copy/tooltips.ts` — the current functional UI Phase 6 polishes.
- `frontend/package.json` — the current dependency set: React 19, React DOM, Tailwind v4 (via `@tailwindcss/vite`), Vitest + Testing Library. No router, no server-state library, no UI component library installed.
- `backend/app/audit/verify.py` — the existing chain-integrity verifier; Phase 6 exposes it via a new endpoint.
- `backend/app/api/{claims,runs,pipeline}.py` — the existing API routers; Phase 6 adds new ones alongside.
- `backend/db/migrations/versions/0001_initial_schema.py` — the `audit_log` CHECK constraint listing the six allowed `agent` values (`system`, `doc_parser`, `validator`, `adjuster`, `guardrail`, `orchestrator`). Phase 6 extends this with one additional value (`human`) via a forward-only migration.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. Plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts, system/user separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 6 of `BUILD-PLAN.md` — Frontend polish. The phase name undersells the scope: polish requires several substantive backend endpoints (chain verification, human decision capture, per-agent test bench) and one schema migration (extending the `audit_log` agent CHECK to include `human`). The backend additions are first-class Phase 6 work; the report's headline is "the polished frontend, end-to-end."

By the end of this phase:

- The frontend is a **proper SPA with routing** (no more in-app view toggle), a **consistent visual language**, and the following polished surfaces:
  - **Claim submission form** — visually polished, with the three "Load demo claim" buttons (already shipped in Phase 5) refreshed to be the primary call-to-action for a reviewer; live form-validation feedback; clear submit confirmation.
  - **Claim list** — polished table/cards with sortable status badges, clear action buttons.
  - **Single-claim view** — claim metadata, status timeline, the runs list for this claim, and a live progress strip when a run is in flight.
  - **Live pipeline visualisation** — for an in-flight or completed run, each agent is a card showing status indicator, completion time, and a click-to-expand detail panel revealing the agent's prompt (system + user, sourced from `prompts/system/` and `prompts/user/`) and the LLM response (raw structured output from the audit log). Replaces the current bare "ProgressStrip".
  - **Audit log viewer** — a dedicated page that, given a correlation_id (URL param or selectable from the runs list), lists every audit entry under that ID in chain order with their `step`, `agent`, `created_at`, and the truncated `payload`. A "**Verify chain**" button calls the chain-integrity verifier and shows a clear pass/fail with the first break (if any).
  - **Human review panel** — for any claim in `awaiting_human` status, the panel shows the evidence: the Validator's cited policy chunks, the Adjuster's reasoning and recommended settlement, the Guardrail's flags. **Approve** and **Reject** buttons capture a typed human decision (with an optional comment) and write a new audit entry under the same correlation_id with `agent="human"`.
  - **Agent test bench** — a separate page with one panel per agent (Doc-Parser, Validator, Adjuster, Guardrail). Each panel accepts arbitrary typed input and POSTs to a new per-agent test endpoint, displaying the typed output, the audit entry, and the LLM call timing. Useful for the demo *and* for ongoing development.
  - **Side-by-side comparison view** (already functional in Phase 5) — polished to highlight the diff fields prominently, with deep-link routing so a specific comparison URL is shareable.
- The backend gains the endpoints the polished UI requires (chain verification, human decision, per-agent test bench, plus a small audit-listing endpoint) and the audit_log schema extension for the `human` agent.
- The three locked demo scenarios continue to pass end-to-end. The auto-approve and threshold scenarios reproduce live; the guardrail scenario remains forced via the integration test (Phase 7 demo polish addresses live reproducibility).

The per-phase preamble fix-up bundled into the same Phase 6 commit:

- Bump `pyproject.toml` version `0.5.0` → `0.6.0`. The `/health` `version` field then reads `0.6.0` after the Phase 6 push, confirming Phase 6 code is live.

## Current state of the project (for orientation)

Phase 5 delivered:

- Submission decoupled from processing: `POST /api/claims` writes the claim with `status='received'` before any agent fires; the orchestrator updates the lifecycle as it progresses.
- Replay against the same claim under a fresh correlation_id with configured variants (`default`, `v2_strict_validator`, `v2_haiku_validator`).
- Runs reconstruction from `audit_log` (`GET /api/runs/{cid}`, `/api/claims/{cid}/runs`, `/api/runs/compare/{a}/{b}`).
- Functional frontend: `App.tsx` view toggle (`claims` ↔ `compare`); plain `fetch` + custom hooks; tooltips naming the production equivalents.
- 277 backend + 13 frontend tests passing.
- `/health` reports `version=0.5.0`.

The frontend has React 19, Tailwind v4, Vitest. **Not** installed: any server-state library, any router, any UI component library.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering everything below.

### Cross-cutting design questions

Each has a recommendation; confirm or argue back in the plan.

1. **TanStack Query — adopt now?** Recommend yes. Phase 6's polish goals (post-mutation refetches, optimistic UI updates on human review, cached runs lists, SSE-driven cache invalidation) buy real polish that plain `fetch` plus useEffect would re-implement badly. Cost: one new dep (`@tanstack/react-query`) and replacing the three Phase 5 hooks with QueryClient-backed equivalents. Recommend adopt; flag the dep.

2. **Routing — adopt `react-router-dom`?** Recommend yes. Phase 6 introduces five distinct top-level views (claims list, single-claim, audit, agent test bench, compare). The in-app view-toggle from Phase 5 doesn't scale, and a shareable URL per comparison is part of "polish." Cost: one new dep (`react-router-dom`). Recommend adopt; flag the dep. The router structure:

   | Path | Component |
   |---|---|
   | `/` | Claims list (default landing) |
   | `/claims/:claimId` | Single-claim view (metadata + runs + progress for live runs) |
   | `/claims/:claimId/runs/:correlationId` | Single-run detail (live pipeline viz when in-flight, audit-driven view when historical) |
   | `/claims/:claimId/compare/:a/:b` | Comparison view |
   | `/audit` | Audit log viewer (correlation_id from query param) |
   | `/agents` | Agent test bench |

3. **UI component library — shadcn/ui, Headless UI, or Tailwind primitives only?** Recommend **Tailwind primitives + a small internal component set** (button variants, badges, cards, modals, status indicators) in `frontend/src/components/ui/`. shadcn would add a heavier dependency (it's a copy-the-source pattern, but Tailwind v4 compatibility is still settling) and a learning curve; the internal-component approach keeps the surface area small, easy to read, and consistent. If a specific shadcn component is genuinely better than a hand-rolled equivalent for a specific surface (e.g. accessible dropdowns), flag it in the plan and we can decide one-by-one. Default = primitives + internal components.

4. **Visual design system.** The plan should specify:
   - **Colour tokens**: a small palette (primary, success, warning, danger, neutral grays). Concrete hex values. Map status badge colours to the seven lifecycle values plus the future `human`-related ones (see question 7) — e.g. `received` neutral, `extracted/coverage_verified/estimated/guardrail_checked` blue progression, `settled` success-green, `awaiting_human` warning-amber, `aborted` danger-red.
   - **Typography scale**: 3–4 sizes, named.
   - **Spacing scale**: standard Tailwind scale unless there's a reason to deviate.
   - **Layout**: top navigation bar, content area, optional sidebar. Mobile-responsive only insofar as the demo lands cleanly on a 1440×900 reviewer laptop; phone-screen polish is out of scope.
   The plan locks these so Phase 7 polish can reference them without re-litigating.

5. **Live pipeline visualisation — what does "expandable detail panel" show, exactly?**

   For each agent card (Doc-Parser, Validator, Adjuster, Guardrail):
   - **Collapsed**: agent name, status icon (queued/running/done/escalated/failed), duration, brief summary (one or two fields per agent — the same shape Phase 4 locked on `agent_completed` SSE events).
   - **Expanded**: the **prompt** (system + user, fetched from a new lightweight endpoint that returns the externalised prompt file contents for the variant in use) and the **LLM response** (the agent's full audit-step payload — already fully reconstructable from `audit_log` after Phase 5's amendments).
   - For an in-flight run, the expanded panel shows a "waiting" state until the audit entry is written (i.e. the panel is populated lazily as `agent_completed` events arrive).

   Open question for the plan: do we fetch the prompt and audit payload eagerly (preload when the agent card renders) or lazily (only on expansion)? Recommend **lazy** — keeps the run-detail view fast on first paint; expansion is a deliberate user action.

6. **Audit log viewer — what does it show?**

   Default view: the correlation_id is taken from the URL query (`/audit?correlation_id=…`) or selected from the runs list. The viewer renders a table:

   | created_at | agent | step | payload (truncated) | chain_hash (short) |
   |---|---|---|---|---|

   Each row click-expands to show the full payload (JSON-formatted). At the top of the page: a "**Verify chain**" button that calls `GET /api/audit/verify/{correlation_id}`. The result renders as:
   - Green badge "Chain verified" + the row count.
   - Red badge "Chain break at audit_id N" + the first break details (which row's `row_hash` or `chain_hash` didn't match).

   The "Verify chain" tooltip names the production equivalent (per `frontend/src/copy/tooltips.ts`): *"In production, the audit ledger is SQL Server with Ledger Tables; chain verification is a single `sys.sp_verify_database_ledger` call."*

7. **Human review — how is the human's decision recorded?**

   Recommend:
   - Extend `audit_log` agent CHECK constraint to include `'human'` (one-line migration).
   - New audit steps: `human_approval`, `human_rejection`. Each entry's payload carries `decision: "approved"|"rejected"`, `decided_at`, `decided_by` (free-text name field from the form), `comment` (optional, up to 1000 chars). Status lifecycle: on approval, the claim's `status` is updated to `settled`; on rejection, the status is updated to `aborted`. The decision audit entry is the trusted record of *who* and *why*; the status column is a UI convenience.
   - A new endpoint `POST /api/claims/{claim_id}/human-decision` accepts the typed decision body and writes the audit entry + status update.
   - Guard: 409 if the claim is not currently `awaiting_human`. Idempotent at the API level (a second decision attempt on a claim now `settled` or `aborted` returns 409).

   **Open question for the plan**: should the `claim_status` CHECK constraint also gain new values (`human_approved`, `human_rejected`)? Recommend **no** — reuse `settled` and `aborted` as the terminal states; the *reason* (`human_approval`) lives in the audit entry. Fewer states is simpler and the audit_log is the trusted reason record.

8. **Agent test bench — what does each agent's panel accept and produce?**

   One panel per agent. The plan should specify the test-input form per agent (each driven by the agent's existing typed input model) and the response shape (the agent's existing typed output model). All test calls are *out-of-band* — they don't touch a real claim, don't update a claim's status, and write a "test mode" audit entry (or no audit entry — decide deliberately and lock).

   Recommendation: test-mode calls **do not write audit entries**. The audit_log is for production-shaped claim runs; the test bench is for development and demo exploration. Test calls write a transient `ApiLogger` entry only (so the developer can see the LLM call metadata). The test bench is explicit about this in its UI copy.

   Per-agent API surface (all under `/api/agents/test/{agent}`):

   | Agent | Method & path | Input | Output |
   |---|---|---|---|
   | Doc-Parser | `POST /api/agents/test/doc-parser` | `{ narrative: str }` | `DocParserOutput` |
   | Validator | `POST /api/agents/test/validator` | `{ narrative: str, claim_type: ClaimType }` | `ValidatorVerdict` + `retrieved_chunks` |
   | Adjuster | `POST /api/agents/test/adjuster` | `{ doc_parser_output: DocParserOutput, validator_verdict: ValidatorVerdict }` | `AdjusterOutput` |
   | Guardrail | `POST /api/agents/test/guardrail` | `{ adjuster_output: AdjusterOutput, retrieved_chunks: list[Chunk] }` | `GuardrailOutput` |

   Each endpoint optionally accepts `?variant=<name>` to apply a variant override (the same registry Phase 5 ships).

### Backend additions

The plan should specify, for each new endpoint:

- File location (`backend/app/api/audit.py`, `backend/app/api/human.py`, `backend/app/api/agents_test.py`).
- Request and response Pydantic models.
- Guards (per-endpoint).
- Test coverage.

Plus the migration:

- `backend/db/migrations/versions/0002_audit_human_agent.py` — `ALTER TABLE audit_log DROP CONSTRAINT audit_log_agent_check;` then re-add with the seven values. Forward-only; document the downgrade behaviour explicitly (re-add the six-value constraint; existing `human` entries would block the downgrade — flag this rather than silently allowing).

### Frontend structure

The plan should sketch the component tree, the route definitions, the QueryClient setup, the SSE-to-Query cache integration, and the design-system tokens (in `frontend/src/styles/tokens.ts` or similar).

For routing: standard `react-router-dom` v6 setup with `BrowserRouter`, route components per the table in question 2.

For server state: TanStack QueryClient with sensible defaults (5-minute staleTime for claims; 0 staleTime for in-flight runs; refetchOnWindowFocus disabled for the demo). Mutations (submit, run, replay, human decision) invalidate the relevant query keys.

For SSE: the `useRunStream` hook continues to exist but is rewired to *also* write into the Query cache so the agent timeline updates without a separate state path.

### Settings additions

The plan should flag any. The expected answer is **none new** — the agent test bench reuses the existing variant registry and LLM Gateway. If a new setting crops up, surface it before writing code.

### Testing strategy

Aim ~30–40 new backend tests and ~25–35 new frontend tests across:

- **Audit API**: list-by-correlation-id (~3), verify-chain happy path + injected break (~3).
- **Human decision API**: approve happy path, reject happy path, on a claim not `awaiting_human` (~3), idempotency (~2).
- **Agent test API**: one happy-path test per agent (~4), variant override applied (~2), guards on malformed input (~3).
- **Audit migration**: forward and reverse migration tests, plus a triggering test that asserts a `human` agent is now valid.
- **Frontend component tests** (Vitest + Testing Library):
  - Claims list table with status badges (~4)
  - Single-claim view (~3)
  - Live pipeline visualisation: agent cards, expand/collapse, prompt fetch, response render (~6)
  - Audit log viewer: list rendering, chain-verify button (~4)
  - Human review panel: form validation, submit, optimistic UI (~4)
  - Agent test bench: one happy-path per agent panel (~4)
  - Routing: top-nav links, deep-link to comparison view (~3)

Every guard clause gets a triggering test asserting on message content. Frontend tests use mocked fetch (or `msw` if introduced — flag if so).

### CI changes

The frontend test runner is already in place. No new gated categories. The `RUN_LLM_E2E_TESTS=1` gated tests are unchanged.

### New dependencies — flag each one

The plan should flag:

- `@tanstack/react-query` (frontend) — adopted per D1.
- `react-router-dom` (frontend) — adopted per D2.

Any *other* new dependency (e.g. `msw`, a date library, a JSON-viewer component) needs explicit justification per the dependency-discipline standard. The expected answer is "the two above and no more"; if you find yourself adding anything else, surface why before writing code.

### Risks and downstream impacts

**Locked at end of Phase 6** (Phase 7 consumes these):

1. The frontend routing structure.
2. The new endpoint paths, methods, and status-code policy (audit list, audit verify, human decision, agent test).
3. The audit_log agent CHECK extension to include `human` and the two new audit step names (`human_approval`, `human_rejection`).
4. The design-system tokens (colour palette, typography, spacing).
5. The agent test bench's per-agent request/response shapes.

**Flagged risks / prototype simplifications:**

- The agent test bench bypasses the audit chain on purpose (test calls don't write audit entries). Document.
- The human decision endpoint is API-key-free in the prototype (no auth). Production would gate this on an Entra ID role. Document explicitly.
- The "fetch the prompt file contents to display in the expand panel" endpoint exposes prompt sources over HTTP. Acceptable for a public-repo prototype where the prompts are already in git; document.

### Deployment steps requiring architect involvement

- Verify `/health` reports `version=0.6.0` after the Render auto-redeploy.
- Run the new migration (`uv run alembic --config backend/alembic.ini upgrade head`) against the deployed Postgres before the frontend goes live with the human-review path. Document the order in the plan.
- Walk through the full demo flow in the browser: submit a claim, watch the live pipeline visualisation, expand each agent card to confirm the prompt + response render, open the audit log viewer, click "Verify chain," open the human review panel (with an escalated claim), approve it, watch the status flip to settled, open the agent test bench, exercise each agent panel.

### Optional enhancements

Carried forward (still deferred): retry via `tenacity`; pricing-table population; real PII redactor; prompt golden fixtures; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings` fields; idempotent re-run helper exposed on UI; `claim_status_history` table.

New for Phase 6 (labelled, not built):

- **Auth on the human decision endpoint** — Entra ID role gate; deferred to production.
- **Audit log pagination** — only relevant once a single correlation_id has more than ~50 entries; current pipelines produce ~12.
- **Dark mode** — pure UX polish, deferred unless trivially free.
- **Prompt diff in the comparison view** — when comparing a default run with a v2_strict run, surface the prompt difference too. Polishes the variant story; deferred to Phase 7 if the demo benefits.

### Save the plan

Save the plan **before** asking me to review it. Write to:

```
docs/prompts/07-phase-6-frontend-polish-plan.md
```

Top-level heading: `# Plan 07 — Phase 6: Frontend Polish`. Below that, the body of the plan.

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

**If I reject**, append a `## Rejection` footer, rename the file to `07-phase-6-frontend-polish-plan-rejected-NN.md`, produce a revised plan as the fresh canonical file, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 6. Constraints from `CLAUDE.md` apply throughout:

- **Defensive programming** (sanitise → validate → abort → execute) on every function that takes input. Every guard has a triggering test that asserts on message content.
- **Function size:** 30 lines is a prompt to reconsider; 50 lines is a hard limit. Frontend components stay focused (one concern per component); React hooks decompose into named helpers.
- **Settings hierarchy:** any new fields appear in both `backend/settings.py` and `backend/settings.yaml.template`. No hardcoded values. No magic numbers without a named constant and a comment. Frontend tokens live in a single source file.
- **Type hints** on every function signature (Python) and TypeScript everywhere on the frontend.
- **Tests:** every new function gets tests; every guard clause gets a triggering test asserting on error-message content.
- **Anonymisation:** the client name does not appear anywhere — code, comments, tests, fixtures, prompt files, copy strings, commit messages.
- **Security:** no new credentials introduced. The human decision endpoint is intentionally unauthenticated in the prototype (flagged in the plan as a production gap to close).
- **Externalised prompts:** no new prompt files in Phase 6. The agent test bench reuses the existing externalised prompts via the existing PromptLoader.
- **System/user separation:** unchanged.
- **Interface stability:** Phase 6 adds new endpoints and one schema migration. Locked Phase 4/5 contracts are not modified.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.5.0` → `0.6.0`. The `/health` `version` field then reflects Phase 6 once deployed.

## Step 4 — Log

When the code work is complete, append a new entry to `docs/build-log.md`. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/07-phase-6-frontend-polish.md`.
- Plan (approved): link to `docs/prompts/07-phase-6-frontend-polish-plan.md`.
- Plan iterations: count of rejected revisions, with links to each.
- Report: link to `docs/prompts/07-phase-6-frontend-polish-report.md`.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate, with breakdown by area.
- Issues discovered.
- Next: Phase 7 — Demo polish and documentation.

## Step 5 — Write the report

Save the report to `docs/prompts/07-phase-6-frontend-polish-report.md`. The report opens with a `## Summary` block in the established order:

- **Recap** — one sentence stating what's done plus one sentence stating what comes next.
- **Completed at** — ISO 8601 UTC timestamp.
- **Phase** — `6 — Frontend polish`.
- **Status** — Complete / Complete with deferrals.
- Links to the prompt, the approved plan, and the repository.
- CI status if relevant.

Body sections cover files created and modified by tier, test counts and pass rates with the breakdown above, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 6:

- Date: today's date in ISO format.
- Phase: "Phase 6 complete; Phase 7 next".
- What works: a one-line summary of the new capability (e.g. "Polished React SPA with routing: claim submission, claim list, single-claim view with live pipeline visualisation and expandable agent prompt+response panels, audit log viewer with one-click chain verification, human review panel writing audit entries under `agent='human'`, and an agent test bench for ad-hoc per-agent invocation. The polish story is end-to-end; Phase 7 is demo and documentation.").
- What's next: "Phase 7 — Demo polish and documentation."

## Step 7 — Git

Make a single commit covering all the Phase 6 work, with the commit message:

```
Phase 6: frontend polish + supporting backend endpoints

- React Router + TanStack Query adopted; SPA shell with five top-level routes
- Live pipeline visualisation: agent cards with expand-to-prompt-and-response
- Audit log viewer + one-click chain verification (GET /api/audit/verify/{cid})
- Human review panel: approve/reject writing audit entries under agent='human'
- Agent test bench: per-agent test endpoints (POST /api/agents/test/{agent})
- audit_log agent CHECK extended to include 'human'; new audit steps human_approval / human_rejection
- Design-system tokens, status badge palette, typography scale
- Defensive guards throughout, every guard with a triggering test
- pyproject.toml version bumped 0.5.0 -> 0.6.0
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

- Verify the Render redeploy completes and `/health` reports `version=0.6.0`.
- Run the audit migration against the deployed Postgres before the human-review path goes live.
- Walk through the full demo flow in the browser: submit → run → expand agent cards → audit log viewer + verify chain → human review on an escalated claim → agent test bench.
- Confirm the polished comparison view's deep-link URL is shareable.

## Save this prompt

Per the "Save every prompt" standing instruction in `CLAUDE.md`, save this prompt verbatim to `docs/prompts/07-phase-6-frontend-polish.md` if it isn't already there.
