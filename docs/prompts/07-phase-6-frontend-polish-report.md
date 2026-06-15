# Report 07 — Phase 6: Frontend Polish

## Summary

**Recap.** Phase 6 turns the functional Phase 5 UI into a polished routed React SPA — live pipeline visualisation, an audit viewer with one-click whole-ledger chain verification, a human-review panel, and an agent test bench — backed by the new endpoints and the schema migration those surfaces require. Next: Phase 7 — demo polish and documentation.

**Completed at:** 2026-06-15T00:05:00Z
**Phase:** 6 — Frontend polish
**Status:** Complete (no deferrals; optional enhancements carried forward, labelled)

**Links**

- Prompt: [`docs/prompts/07-phase-6-frontend-polish.md`](07-phase-6-frontend-polish.md)
- Plan (approved): [`docs/prompts/07-phase-6-frontend-polish-plan.md`](07-phase-6-frontend-polish-plan.md) — approved 2026-06-14T21:16:53Z
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 6 entry)
- Repository: pushed to `main` after this commit lands; Render auto-redeploys.

**CI status.** Unchanged. The frontend Vitest runner was already present. No new gated categories; the agent-test-bench happy paths are gated (`RUN_LLM_E2E_TESTS=1`, real LLM calls) — their guard tests (422/404) run in CI with no network.

---

## Two approval notes (honoured)

1. **Whole-ledger chain-verify copy.** The audit viewer's button reads **"Verify chain (whole ledger)"** and the success badge says **"Chain verified · N rows (whole ledger)"**. The endpoint runs the full-ledger `verify_chain` (the hash chain spans every `audit_log` row, so a per-run sub-chain cannot be verified in isolation); the `correlation_id` only scopes the 404 and the viewer context. The semantics are reviewer-evident.
2. **Human-panel evidence source.** The human review panel assembles its evidence from `GET /api/audit?correlation_id=`, **not** from the reconstructed `PipelineResult`: `ValidatorVerdict.cited_chunks` carries chunk IDs without the clause text, so the policy-clause content lives only in the validator's `coverage_check` audit payload. This is documented here and should carry into the Phase 7 documentation.

---

## Files created and modified, by tier

### Migration + schema
- **created** `0002_audit_human_agent.py` — `audit_log` agent CHECK +`human`; `claims` status CHECK +`aborted` (see Deviations). **modified** `audit/event.py` (`AgentName` +`human`), `claims/models.py` (`ClaimStatus` +`aborted`).

### Agents (additive, behaviour-preserving)
- **modified** `prompts/loader.py` (`raw`), `agents/_shared.py` (`ProbeMetadata`), and the four agents (`parse`/`assess`/`estimate`/`check` probe methods). `evaluate` paths untouched — all Phase 2–5 agent tests still pass.

### Backend API
- **created** `api/audit.py`, `api/human.py`, `api/agents_test.py`; **modified** `api/__init__.py` (mount). **modified** `pyproject.toml` (0.6.0).
- **created** tests: `test_migration_0002.py`, `test_agent_probe.py`, `test_audit_api.py`, `test_human_decision_api.py`, `test_agents_test_api.py`; **modified** `test_prompt_loader.py`.

### Frontend
- **modified** `package.json` (+2 deps), `main.tsx`, `App.tsx`, `api/{client,types}.ts`, `setupTests.ts`.
- **created** `styles/tokens.ts`; `components/{ui,AgentCard,HumanReviewPanel,AgentTestPanel}.tsx`; `pages/{ClaimsPage,ClaimDetailPage,RunDetailPage,ComparePage,AuditPage,AgentsPage}.tsx`; `hooks/queries.ts`; `test/utils.tsx`; component/page/routing tests.
- **rewired** `hooks/useRunStream.ts` (feeds the Query cache). **removed** superseded `components/{ClaimList,ProgressStrip,CompareView}.tsx` + tests and `hooks/useClaims.ts`.

---

## Test counts and pass rates

| Area | Tests |
|---|---|
| Migration 0002 | 4 |
| PromptLoader.raw | 5 |
| Agent probe | 4 |
| Audit API | 5 |
| Human decision API | 7 |
| Agent test API (+ prompt) | 9 (+1 gated) |
| **Backend new** | **34** |
| Frontend (Vitest, total) | 22 |

Repository: **311 backend passing, 7 skipped** + **22 frontend passing** = **333 passing, 7 skipped, 0 failing**. `ruff` clean; `mypy backend` clean (104 source files); frontend `tsc -b --noEmit` and `eslint .` clean.

---

## Deviations from the plan, with reasons

1. **`aborted` added to the `claims.status` CHECK (and `ClaimStatus`).** The prompt (q7) assumed human-rejection → `aborted` would just work, but the Phase 1 `claims.status` CHECK enumerated only the seven lifecycle values — `aborted` existed solely as a *pipeline* outcome, never a claim status. Migration 0002 therefore also extends `claims.status` with `aborted` so a rejected claim has a distinct terminal state (approval → `settled`, rejection → `aborted`). This is the migration's second constraint change; flagged on the interface-stability list.
2. **Live progress lives on the run-detail route, not inline on the claim view.** The plan put a "live progress strip when a run is in flight" on the single-claim view; in practice the Process/Replay actions navigate to `/claims/:id/runs/:cid`, where the full live pipeline visualisation (agent cards) renders. Cleaner than two progress UIs.
3. **The agent test bench needed an additive `probe` per agent** (D5, approved) — `evaluate` writes audit and needs a claim; the probe runs the same core without either.

No interface deviations beyond the additive ones the plan flagged (the new endpoints, the `human` agent value, the `aborted` claim status, `PromptLoader.raw`).

---

## Guard clauses added (each with a triggering test)

- Audit API: 404 for an unknown correlation_id (list + verify); chain-break detection (tampered row → `row_hash_mismatch`).
- Human decision: 404 missing claim; 409 not-`awaiting_human`; 409 idempotent re-decide; 422 blank `decided_by` / oversized comment.
- Agent test: 422 malformed body; 404 unknown variant; 404 unknown agent (prompt endpoint).
- `PromptLoader.raw`: unknown kind, missing file, path-traversal.
- Migration: the documented downgrade hazard (six-value CHECK re-add fails with `human` rows present).

## Guard clauses added that were not in the spec

- The frontend test fetch stub coerces a non-string `fetch` input (URL/Request) to a string before matching, rather than assuming a string argument.

---

## Optional enhancements recommended for follow-on work

Carried forward: retry/`tenacity`; pricing table; real PII redactor; prompt golden fixtures; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings`; `claim_status_history`. New for Phase 6: **auth on the human-decision endpoint** (Entra ID role — the prototype is intentionally open); audit-log pagination (>50 rows); dark mode; prompt-diff in the comparison view (surface the variant's prompt change alongside the outcome diff).

---

## Outstanding items requiring architect involvement

1. **Verify the Render redeploy completes and `/health` reports `version=0.6.0`.**
2. **Run migration 0002 against the deployed Postgres before the human-review path goes live:** `uv run alembic --config backend/alembic.ini upgrade head`. Order matters — the human-decision endpoint writes `agent='human'` / sets `status='aborted'`, both of which the new CHECKs must already allow.
3. **Walk the full demo flow in the browser:** submit → process → expand each agent card (confirm prompt + response render) → open the audit-log viewer → "Verify chain (whole ledger)" → on an escalated claim, open the human-review panel and approve (watch the status flip to `settled`) → exercise each agent test-bench panel.
4. **Confirm the comparison deep-link is shareable** — `/claims/:claimId/compare/:a/:b` reconstructs and renders without any prior in-app navigation.

**Prototype simplifications flagged:** the human-decision endpoint is unauthenticated (production gates on an Entra ID role); the agent test bench writes no audit entries by design (only an APILogger record); the prompt-source endpoint exposes prompt files over HTTP (already public in git); chain verification is necessarily whole-ledger.

No new env vars are required. No CI changes.
