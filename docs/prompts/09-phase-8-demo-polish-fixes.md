# Prompt 09 — Phase 8: Demo Polish Fixes (Rehearsal Discoveries)

## Read first

This phase is a small, focused fix-pack discovered during the Phase 7 demo rehearsal against the deployed prototype. The architecture is unchanged; everything here is bug-fix or polish on existing surfaces. Plan-first still applies — but the plan is short and the cross-cutting decisions are few.

Before doing anything else, read these files:

- `CLAUDE.md` — standing instructions, locked architectural decisions, the "Locked interface extensions since Phase 4" subsection.
- `BUILD-PLAN.md` — Phase 7 was the planned end of build; this Phase 8 is a polish addition.
- `docs/prompts/08-phase-7-demo-polish-and-documentation-report.md` — what Phase 7 shipped and what it deferred.
- `frontend/src/pages/ClaimsPage.tsx` — the `trigger` function (lines 23–34) is fix #1 below; it's the root of the no-live-progress bug.
- `frontend/src/pages/RunDetailPage.tsx` — needs to handle the "no audit entries yet" state gracefully.
- `frontend/src/components/AgentCard.tsx` — needs a "running" state with expected-duration and per-agent description.
- `frontend/src/hooks/useRunStream.ts` — the SSE consumer; verify the cache-write path on the new fire-and-forget POST flow.
- `backend/data/seed_claims.py` — the three demo claims' narratives need to include dollar amounts (Doc-Parser can't extract amounts that aren't in the text).
- `backend/app/prompts/system/guardrail.md` — needs a sentence about Adjuster market vocabulary.
- `README.md` — confirm whether the audit-payload addendum (the additive interface extensions from Phase 5/6) is documented in the architecture section; add it if not.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout: plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts, system/user separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute six concrete fixes discovered during the Phase 7 demo rehearsal. The prototype's architecture is correct; what's broken or thin is the polish around the live demo experience. Each fix is small and well-bounded.

The fixes:

**1. Restore live pipeline visualisation (the critical fix).** `ClaimsPage.tsx`'s `trigger` function awaits the entire ~27-second pipeline runtime before navigating to the run-detail page. By the time the page mounts and opens the SSE stream, the pipeline has finished and only the terminal `pipeline_completed` event arrives — the agent cards render as "done" without ever showing "running." The Phase 5 D4 design was *"the frontend opens the SSE stream first, then triggers the run with the same correlation_id"*; Phase 6 collapsed this into a synchronous `await` pattern. Restore the original intent: navigate immediately, kick the POST off in the background (no await), let the run-detail page's SSE subscription deliver events live.

**2. Make the run-detail page handle "no run data yet" gracefully.** Once fix #1 lands, the page will mount before any audit entries exist for the correlation_id. `GET /api/runs/{cid}` and `GET /api/audit?correlation_id=...` will 404. The page must treat 404 during in-flight as expected (not an error), rely on the SSE stream for live state, and let the queries refetch when the SSE stream emits a terminal event.

**3. AgentCard "while running" UI.** Each agent card in the running state currently shows a static "running" label. It needs to show: an expected duration (per-agent constant), a one-sentence description of what's happening, and an animated progress bar that fills proportionally to the expected duration. If the agent completes before the expected duration, the bar snaps to 100% and the card flips to "done." If it runs over, the bar caps at 100% but the card stays in "running" state until the actual completion event. This turns the 5–9 seconds of per-agent runtime from "is it stuck?" into "the system is doing this, that's why it takes this long."

**4. Update seeded narratives to include dollar amounts.** The current seeded narratives (in `backend/data/seed_claims.py`) describe the loss but do not mention the claimed dollar figure. Doc-Parser asks Claude Haiku to extract `claimed_amount` from the narrative; Haiku correctly returns `0.00` when no amount is mentioned; the Pydantic schema rejects `0.00` because of the `greater_than: 0` constraint; the run aborts with `failing_agent="doc_parser"`. The three demo-scenario claims (auto-approve, threshold escalation, guardrail escalation) need their narratives rewritten to embed the relevant dollar figure naturally in the text. Other seeded background claims may or may not need updating; flag the scope decision in the plan.

**5. Tune the Guardrail prompt to recognise Adjuster market vocabulary as non-policy.** The Guardrail's LLM check is currently flagging phrases like `"market band"`, `"mid-range"`, and `"within range"` as hallucinated policy citations. They are not citations — they are the Adjuster's market-data-derived vocabulary. Add a sentence to `backend/app/prompts/system/guardrail.md` explicitly naming this vocabulary as Adjuster framing language to be ignored by the hallucinated-citation check. Targeted prompt tuning, not a behaviour change.

**6. Surface POST errors instead of swallowing them.** The current `trigger` function uses a `try/finally` that catches nothing and shows nothing to the user when a POST fails (e.g., 502 from a cold start, timeout, network error). The fire-and-forget refactor in fix #1 must include an error path that surfaces the failure — at minimum a toast or inline error message on the run-detail page; ideally rendered from a `pipeline_aborted` SSE event when the backend produces one, with a UI-side fallback for transport-level failures (no SSE event because the connection itself failed).

Bonus check, not a fix but worth verifying as part of this phase:

**7. Confirm the audit-payload addendum is in `README.md`'s architecture section.** Phase 7 landed it in `CLAUDE.md` under "Locked interface extensions since Phase 4." The Phase 5 report-back noted it should also surface in the README's "Design decisions and trade-offs" section for outward-facing readers who never open `CLAUDE.md`. If it's not there, add a one-paragraph note. If it is, no change.

The per-phase preamble fix-up bundled into the same Phase 8 commit:

- Bump `pyproject.toml` version `0.7.0` → `0.8.0`. The `/health` `version` field then reads `0.8.0` after the Phase 8 push, confirming Phase 8 code is live.

## Current state of the project (for orientation)

Phase 7 shipped the full demo-ready documentation set, the scenario-3 deterministic fixture, and the audit-payload addendum in CLAUDE.md. 348 backend + frontend tests passing, ruff and mypy clean, `/health` reports `version=0.7.0`. The deployment is on Render Standard with adequate resources (1 CPU, 2 GB). All three demo scenarios behave correctly end-to-end *in test*; live reproduction of scenarios 1 and 2 was exercised during Phase 7 rehearsal and surfaced the six issues above.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a short plan covering everything below.

### Cross-cutting questions

Each has a recommendation; confirm or argue back in the plan.

1. **Fix #1 implementation shape.** Recommended: the `trigger` function navigates synchronously, kicks off the POST without `await`, and uses `.then()`/`.catch()` to refresh the claims list when the POST completes and to surface errors when it doesn't. The run-detail page must mount and open the SSE subscription before the POST has progressed far enough to emit `pipeline_started`. The Phase 4 EventBus already buffers late subscribers, so the SSE-first sequencing is safe.

2. **Fix #2 surface for the "no run yet" state.** Recommended: the run-detail page treats 404 from `GET /api/runs/{cid}` during in-flight as expected — render the agent cards in `queued` state, show a brief "Awaiting pipeline_started…" hint, and rely on the SSE stream for state. Once the SSE stream emits any agent event, the cards update; once it emits a terminal event, the queries refetch (already wired via `useRunStream`).

3. **Fix #3 expected durations.** Recommended: per-agent constants based on observed Render Standard live numbers, rounded conservatively upward — Doc-Parser 6s, Validator 9s, Adjuster 7s, Guardrail 5s. These are display-only; the actual SSE timing always wins. Source the durations from a single config object alongside the AgentCard component, with a one-line comment that they're empirical from Phase 8 rehearsal and may be tuned over time. Animated progress bar can use plain CSS `transition` on a `width` style; no animation library needed.

4. **Fix #4 narrative rewrites — scope.** Recommended: rewrite the three demo-scenario claims' narratives only (the auto-approve, threshold-escalation, and guardrail-escalation seeds). Other seeded background claims stay as they are — they're not on the demo path and are useful as edge cases for unit tests. The demo-trio narratives should naturally embed the dollar figure, e.g. *"…damage to dry-stored inventory and structural cleanup is estimated at $85,000…"*. Confirm in the plan.

5. **Fix #5 Guardrail prompt — text.** Recommended addition to `backend/app/prompts/system/guardrail.md`, somewhere near the existing citation-check instructions: *"Note: the Adjuster uses phrases such as 'market band', 'mid-range', 'within range', and 'lookup table' to describe its settlement decision, which is derived from a market-data lookup table — not from the insurance policy. These are not policy citations and should not be flagged as hallucinated. Only flag references to specific policy clauses, endorsements, or sub-limits that are not present in the retrieved policy chunks."* The exact wording is up to you; the constraint is that it surgically addresses the false-positive without weakening detection of real hallucinated endorsements (which is what scenario 3 deliberately surfaces).

6. **Fix #6 error display — surface.** Recommended: a small `ErrorBanner` or `ErrorToast` component in `frontend/src/components/ui.tsx`, shown by the run-detail page when `useRunStream` reports a stream-level error (couldn't connect) or when the page detects the POST failed (the `.catch()` from fix #1 sets an error state in the QueryClient cache). For SSE-emitted `pipeline_aborted` events, the existing cache update path already handles them — the page should just render the aborted state visibly rather than leaving the cards stuck. Plain styled banner with the error message; no toast library needed.

### Files created / modified

**Backend:**
- `backend/app/prompts/system/guardrail.md` — added sentence per fix #5.
- `backend/data/seed_claims.py` — three demo-scenario narratives rewritten per fix #4.
- `backend/tests/test_seed_claims.py` (or wherever the seed tests live) — assert each demo claim's narrative contains its expected dollar figure (`"$85,000"`, `"$850,000"`, `"$1,400,000"` or `"$1.4M"`).
- `backend/tests/test_guardrail.py` — a regression test that the Guardrail does NOT flag a stock Adjuster reasoning containing market-band vocabulary, with a mocked LLM provider returning a benign response.
- `pyproject.toml` — version `0.7.0 → 0.8.0`.

**Frontend:**
- `frontend/src/pages/ClaimsPage.tsx` — fix #1; the `trigger` function reorders to navigate-first, fire-and-forget POST, error-aware catch.
- `frontend/src/pages/RunDetailPage.tsx` — fix #2; handle 404 from runs API as in-flight state; render gracefully.
- `frontend/src/components/AgentCard.tsx` — fix #3; "running" state shows expected duration, description, and progress bar.
- `frontend/src/copy/agent-descriptions.ts` (new file) — per-agent description strings (alongside `tooltips.ts`).
- `frontend/src/components/ui.tsx` — small `ErrorBanner` primitive for fix #6.
- Existing component tests updated for the new shapes.

**Documentation:**
- `README.md` — verify and add the audit-payload addendum to the architecture section if it isn't there already (per fix #7).
- `CLAUDE.md` — Current Status updated per Step 6.

### Testing strategy

Aim ~10–15 new tests across:

- **Frontend `ClaimsPage`** (~3): clicking Process navigates immediately (assert URL changed before the POST mock resolves); POST failure surfaces an error message; the claims list refetches after a successful POST resolves in the background.
- **Frontend `RunDetailPage`** (~3): renders queued cards when runs API returns 404; receives a synthetic SSE event and updates the card state; renders an error banner when a `pipeline_aborted` event arrives.
- **Frontend `AgentCard`** (~3): renders expected duration and description in the running state; progress bar width increases over time; bar snaps to 100% when an `agent_completed` event arrives.
- **Backend Guardrail regression** (~1): stock Adjuster reasoning containing "market band" / "within range" does not trip the hallucinated-citation check (with mocked benign LLM response).
- **Backend seed-data regression** (~3): each of the three demo-scenario claims has a narrative containing its expected dollar figure.

Every guard clause from the changes gets a triggering test asserting on message content where applicable.

### CI changes

None. No new gated test categories.

### New dependencies — flag each one

Expected answer: **none**. The progress bar uses CSS `transition`; the error banner is a styled `div`. If you find yourself wanting an animation or toast library, surface why before writing code.

### Risks and downstream impacts

None of these fixes change a locked interface. The Phase 4/5/6 contracts (PipelineResult, EscalationDecision, SSE event payloads, audit payloads) are unchanged. The Guardrail prompt change is internal; the agent's output shape is unchanged. The narrative rewrites change the *content* of seed_claims output but not its *shape*. The agent-description copy is new and additive.

### Deployment steps requiring architect involvement

- Verify `/health` reports `version=0.8.0` after the Render auto-redeploy.
- Re-seed the database (`uv run python -m backend.data.seed_claims --allow-truncate`) against the deployed Neon instance so the rewritten narratives are live. This is a one-time architect action; the seed script is idempotent.
- Re-run the demo rehearsal end-to-end. All three scenarios should reproduce live: scenario 1 auto-approves cleanly with the Guardrail no longer false-positiving on market vocabulary; scenario 2 escalates on threshold only (no spurious guardrail_failed); scenario 3 escalates on guardrail_failed as designed (the fixture's "Endorsement Coastal Surge Rider" is a real hallucinated citation, not market vocabulary).

### Optional enhancements

Carried forward (still deferred): retry via `tenacity`; pricing-table population; real PII redactor; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings` fields; idempotent re-run helper exposed on UI; `claim_status_history` table; auth on the human decision endpoint; audit pagination; dark mode; prompt-diff in the comparison view; standalone ADR log.

New for Phase 8 (labelled, not built):

- **Eager orchestrator construction option** controlled by an env-driven `LAZY_ORCHESTRATOR` flag. Default lazy (preserve Phase 6 deviation); flag-flip to eager for demo environments to remove the first-request cold-load. Flagged but not built; trade-off is documented elsewhere.
- **Configurable agent-description strings via the variant registry**, so a variant could carry its own running-state copy. Probably over-engineered for the prototype.

### Save the plan

Save the plan **before** asking me to review it. Write to:

```
docs/prompts/09-phase-8-demo-polish-fixes-plan.md
```

Top-level heading: `# Plan 09 — Phase 8: Demo Polish Fixes`. Below that, the body of the plan.

After saving the file, point me at it and ask for my verdict. Do not write any other code yet.

## Step 2 — Approval or rejection

Same workflow as previous phases.

**If I approve:**

Append a horizontal rule and an `## Approval` section to the plan file. Order so the timestamp closes the file:

```
## Approval

**Approval message:** "<my exact approval message, quoted>"

---

**Approved by:** Dermot Copps
**Approved at:** <ISO 8601 timestamp in UTC>
```

Then proceed to Step 3.

**If I reject**, append a `## Rejection` footer, rename to `09-phase-8-demo-polish-fixes-plan-rejected-NN.md`, produce a revised plan, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 8. Constraints from `CLAUDE.md` apply throughout:

- Defensive programming on the new error surfaces (fix #6).
- Function size limits — these are small fixes; helpers stay small.
- Type hints everywhere.
- Tests per the strategy above.
- Anonymisation: client name does not appear in narratives, copy strings, comments, commit message.
- Externalised prompts: the Guardrail prompt change is in the existing `.md` file; no inline f-string prompts.
- Interface stability: no locked contract changes.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.7.0` → `0.8.0`.

## Step 4 — Log

Append a new entry to `docs/build-log.md` with the standard fields:

- Date.
- Phase / Prompt: link to this prompt.
- Plan (approved): link to the plan.
- Plan iterations: count of rejected revisions.
- Report: link to the report file.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate.
- Issues discovered.
- Next: clone-and-run verification (per the original BUILD-PLAN end state).

## Step 5 — Write the report

Save to `docs/prompts/09-phase-8-demo-polish-fixes-report.md`. Standard `## Summary` block in the established order:

- Recap — done plus next.
- Completed at — ISO 8601 UTC.
- Phase — `8 — Demo polish fixes (rehearsal discoveries)`.
- Status — Complete / Complete with deferrals.
- Links to prompt, approved plan, repository.
- CI status if relevant.

Body sections cover the six fixes individually (what shipped and what test proves it), deviations from the plan, any optional enhancements newly recommended.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section to:

- Date: today's date in ISO format.
- Phase: "Phase 8 complete; clone-and-run verification next".
- What works: a one-line summary noting the live pipeline visualisation is now live, the three demo scenarios reproduce cleanly, the Guardrail no longer false-positives on market vocabulary.
- What's next: "Clone-and-run verification."

## Step 7 — Git

Single commit covering all the Phase 8 work, message:

```
Phase 8: demo polish fixes from rehearsal discoveries

- Restored live pipeline visualisation: ClaimsPage navigates immediately, POST fires in background, SSE stream observes from page mount
- RunDetailPage handles "no run data yet" state via 404 fallback to SSE
- AgentCard "running" state: expected duration + description + animated progress bar
- Seeded demo-scenario narratives rewritten to include dollar amounts (Doc-Parser can extract claimed_amount from the text)
- Guardrail prompt tuned to recognise Adjuster market vocabulary as non-policy
- Frontend now surfaces POST failures via ErrorBanner instead of silently un-greying the button
- README architecture section confirmed/updated with audit-payload addendum
- pyproject.toml version bumped 0.7.0 -> 0.8.0
- Approved plan archived; build log appended; report written
- CLAUDE.md Current Status updated
```

Push to `main`; Render auto-deploys.

## Step 8 — Report back

Per the global "After coding" section:

- Files created and modified.
- Test count and pass rate, with per-fix breakdown.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend.

End the report with the action items I still need to handle:

- Verify the Render redeploy completes and `/health` reports `version=0.8.0`.
- Re-seed the database against the deployed Neon instance so the new narratives are live.
- Re-run the demo rehearsal end-to-end. Confirm scenarios 1/2/3 all reproduce as designed (auto-approve, threshold-only escalation, guardrail-only escalation).
- Watch the live agent cards light up progressively — that's the one outcome that validates fix #1 worked.

## Save this prompt

Per the "Save every prompt" standing instruction in `CLAUDE.md`, save this prompt verbatim to `docs/prompts/09-phase-8-demo-polish-fixes.md` if it isn't already there.
