# Prompt 11 — Phase 8.3: Explainability Panel Fixes

## Read first

This is a small, focused three-fix phase. All three fixes serve the same goal: making the explainability surfaces actually usable end-to-end — Phase 6 promised *"each card expands to show exactly what ran — the prompt the agent used, and its raw response, pulled straight from the audit log,"* and added a chain-verifiable Audit page. Currently the expand panel doesn't deliver either half of the prompt/response promise, *and* the Audit page isn't reachable from a run without manual URL-fiddling.

Before doing anything else, read these files:

- `CLAUDE.md` — standing instructions, locked architectural decisions, "Locked interface extensions since Phase 4" subsection (which this prompt will extend by one more entry).
- `docs/prompts/10-phase-8.2-doc-parser-refactor-report.md` — what 8.2 shipped; the additive `"fields_source"` audit field is the precedent for the audit extension this phase makes.
- `frontend/src/components/AgentCard.tsx` — the expand panel; both fixes land here.
- `frontend/src/hooks/queries.ts` and `frontend/src/hooks/useRunStream.ts` — how the panel reads agent data.
- `backend/app/api/agents_test.py` — the existing `GET /api/agents/{agent}/prompt?variant=<name>` endpoint added in Phase 6 D6. Its semantics need rethinking after this fix.
- `backend/app/agents/{doc_parser,validator,adjuster,guardrail}.py` — the four agents whose audit payloads gain the new `prompt: {system, user}` block.
- `backend/app/agents/*_models.py` — the agent output models (unchanged); no shape change here.
- `backend/tests/test_{doc_parser,validator,adjuster,guardrail}.py` — existing audit-payload assertions; new fields need new assertions.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout: plan-first, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts, system/user separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Three surgical fixes. All three ship in the same commit.

**Fix A — show the literal filled prompt the LLM actually received.** Right now the expand panel calls `GET /api/agents/{agent}/prompt?variant=<name>` which returns the *raw template* (per Phase 6 D6's intent). The template carries placeholder strings like `{claim_summary}`, `{validator_verdict}`, `{claim_type}`, `{severity}` — exactly what a reviewer should *not* see. They should see what Haiku/Mistral actually got: the placeholders substituted with the real values from this specific run.

The architecturally honest fix is to extend each agent's audit payload to record the literal system + user prompts that were sent. The expand panel then reads from the audit (single source of truth), not from a separate "raw template" endpoint. This is an additive interface-stability extension to four locked Phase 3 audit payloads — joins the Phase 5/6/7/8.2 extensions in `CLAUDE.md`. The win: *"the audit log captures the literal text the LLM saw"* — a strictly stronger explainability story than the current template-with-placeholders.

**Fix B — response panel uses the audit entry as the authoritative completion signal.** Currently the panel says *"Waiting for this agent to complete…"* even when the agent has clearly completed (✓ done, duration shown) — because the panel's "waiting vs loaded" check is probably testing for SSE-event presence in the session cache, which doesn't exist for runs completed before the user navigated to the page. The fix: the panel renders the response from the audit entry's `output` block whenever the audit entry exists. The "waiting" state only shows when the audit entry genuinely doesn't exist yet (mid-run subscription).

This is structurally identical to Phase 8's fix #2 (the RunDetailPage handling "no run data yet" gracefully): the audit log is authoritative when it has data; the SSE event is the live signal *during* in-flight; the panel's logic shouldn't conflate the two.

**Fix C — make the audit page reachable from the run with the correlation_id pre-filled.** Currently the Pipeline run header shows a truncated correlation_id (`run 0fa06cb9`) and there's no way to copy the full UUID. A user navigating from the run-detail page to the Audit page lands on an empty filter with no obvious way to populate it. Two sub-fixes:

- **C1 — display the full correlation_id with a copy button** on the run-detail page header, replacing the truncated prefix. Standard copy-to-clipboard UX: click → brief "Copied" confirmation. Useful for sharing the run ID externally or pasting elsewhere.
- **C2 — add a "View audit log" link or button** on the run-detail page header that navigates straight to `/audit?correlation_id=<full-uuid>` with the filter pre-populated. The one-click path from agent timeline to audit-view of the same run.

C2 is the better UX for the common path; C1 is the fallback for sharing. Both are small — together maybe twenty lines plus tests.

Per-phase preamble fix-up bundled into the same commit:

- Bump `pyproject.toml` version `0.8.2` → `0.8.3`. The `/health` `version` field then reads `0.8.3` after the push, confirming this code is live.

## Current state of the project (for orientation)

Phase 8.2 refactored Doc-Parser to source structured fields from the claim record. All three demo scenarios reproduce live cleanly through to the orchestrator's terminal event. The agent expand panel is the next surface where the explainability story breaks: the prompt panel shows placeholders; the response panel says "Waiting…" indefinitely on completed runs. Both are demo-visible defects that any reviewer who clicks to expand a card will hit immediately.

`/health` reports `version=0.8.2`. 327 backend + 30 frontend tests passing. ruff and mypy clean.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a short plan covering everything below.

### Cross-cutting questions

Each has a recommendation; confirm or argue back.

1. **Where does the literal prompt live in the audit payload?** Recommended: nested under the existing `llm_call` block as `llm_call.prompt: { system: str, user: str }`. The `llm_call` block already holds "what we sent to the LLM" metadata (provider, model, prompt_tokens, completion_tokens, latency_ms); the prompt text is the natural extension. Alternative: a new top-level `prompt` block alongside `input` / `llm_call` / `output`. Recommend the nested approach — it groups all LLM-call detail in one place.

2. **What does the literal prompt include?** Recommended: the *substituted* user prompt (the string returned by `PromptLoader.user(name, **kwargs)` for that specific call, with all placeholders filled) plus the system prompt (the string returned by `PromptLoader.system(name)`). Both as plain UTF-8 strings, no extra formatting. The prompt panel renders them in a `<pre>` block with monospace font. Total typical size: ≤10KB per audit entry for Validator (which has retrieved chunks); smaller for the others. JSONB storage handles this comfortably at prototype scale.

3. **Backwards compatibility for old audit entries.** Recommended: the expand panel checks `if audit_entry.llm_call.prompt exists → render it; else → fall back to the existing template endpoint with a small caveat banner above the prompt block: "Showing the prompt template — this run pre-dates the audit-prompt-capture change."* The fallback path keeps old runs viewable (so the comparison-view of historical replays still works) without misleading the viewer. Confirm.

4. **Does the existing `GET /api/agents/{agent}/prompt?variant=<name>` endpoint still serve a purpose?** Recommended: keep it. It's still useful for the **agent test bench** (`AgentTestPanel` shows the template a probe will use), and for the backwards-compatibility fallback in fix A. Its semantics don't change — it returns the raw template (with placeholders) as before. Only the run-detail expand panel switches to reading from the audit instead.

5. **Response panel — what's the authoritative completion signal?** Recommended: the audit entry's existence. Specifically: `useAuditEntries(correlation_id)` returns the list of entries; if there's an entry for this agent's step name, the response panel renders its `output` block. The SSE `agent_completed` event still updates the card's status badge live during in-flight, but the response *content* always reads from the audit entry. No more dependence on SSE-event presence for the response. Confirm.

6. **Fix B implementation shape.** Recommended:
   - The expand panel's "response" section consults the audit entries (via the existing `useAuditEntries(correlation_id)` query — already wired post-Phase 6).
   - When an entry for this agent's step exists, render its `output` block as JSON (the existing render).
   - When the entry doesn't exist *and* the agent's SSE status is not yet `done`, render the "Waiting for this agent to complete…" state.
   - When the entry doesn't exist *and* the SSE status is `done`, render an explicit error state: "Audit entry not found for this completed agent — this may indicate a write failure." This case should never happen in normal operation; if it does, the audit log is the trusted record and a missing entry is a real problem worth surfacing.

### Backend changes

For each of the four agents (`doc_parser`, `validator`, `adjuster`, `guardrail`):

- Modify the agent's `_invoke_llm` (or equivalent) to capture the system and user prompt strings just before calling `self._provider.complete(...)`. These are already constructed via `PromptLoader.system(...)` and `PromptLoader.user(..., **kwargs)`; just retain them as local variables and pass through to `_write_audit`.
- Modify the agent's `_build_audit_payload` to include `prompt: { system: str, user: str }` nested under `llm_call`. Only present when the LLM call actually happened (i.e., not on early aborts before the LLM was reached, and not on the Doc-Parser's Phase 8.2 sentinel-summary code path — though that path *does* call the LLM, so it's still present there).
- The Adjuster's demo-fixture path (Phase 7) bypasses the LLM call entirely; its `llm_call` block currently reflects `provider: "demo_fixture"` with no model call. In that case, `llm_call.prompt` should be `None` or omitted (not the synthesized prompt that would have been sent had the LLM run). Document the choice in the plan and lock it.

The audit-payload extension is **additive only**. Existing keys unchanged; new optional field added. Joins the locked-extensions list.

`backend/app/api/agents_test.py` — no change to the existing `prompt-display` endpoint. It still serves the raw template for the test bench and the backwards-compatibility fallback.

### Frontend changes

- `frontend/src/components/AgentCard.tsx`:
  - **Fix A:** When the expand panel renders, look up the audit entry for this agent's step in the `useAuditEntries(correlation_id)` cache. If `entry.llm_call.prompt` exists, render it (`{prompt.system}` and `{prompt.user}` in two clearly-labelled `<pre>` blocks). If the field is missing (historical run), fall back to the existing template-endpoint fetch with the caveat banner from Q3.
  - **Fix B:** The "response" section's loading-state condition changes from "no SSE agent_completed event" to "no audit entry exists for this agent's step." If the entry exists, render `entry.output` as JSON. If it doesn't and the agent's SSE status is `done`, render the explicit error state from Q6. Otherwise, render "Waiting for this agent to complete…".
- `frontend/src/hooks/queries.ts` — likely already exposes `useAuditEntries(correlation_id)`; confirm and reuse.
- `frontend/src/components/AgentCard.test.tsx` — update the relevant test cases: expand panel renders the filled prompt when audit has `llm_call.prompt`, falls back to template when missing, renders response from audit `output`, shows error state when audit entry is missing for a `done` agent.

- `frontend/src/pages/RunDetailPage.tsx`:
  - **Fix C1:** Replace the truncated correlation_id display in the page header with the full UUID alongside a `CopyButton` primitive. Click → writes to `navigator.clipboard`, shows a brief "Copied" confirmation (e.g. 1500ms toast or inline state flip), reverts.
  - **Fix C2:** Add a "**View audit log**" link/button next to the correlation_id, navigating to `/audit?correlation_id=<full-uuid>`. Standard `<Link to=...>` from `react-router-dom`.
- `frontend/src/components/ui.tsx`:
  - Add a small `CopyButton({ value, label? })` primitive — Tailwind-styled, uses `navigator.clipboard.writeText`, shows "Copied" state for 1500ms. ~15 lines.
- `frontend/src/pages/RunDetailPage.test.tsx`:
  - Test the full correlation_id is rendered (not truncated).
  - Test the copy button calls `navigator.clipboard.writeText` with the full UUID (mock the clipboard API).
  - Test the "View audit log" link points to `/audit?correlation_id=<uuid>`.
- `frontend/src/pages/AuditPage.tsx`: confirm the page reads the `correlation_id` query param on mount and pre-populates the filter input. If it doesn't already (Phase 6 may have wired it; verify), add it.

### Settings additions

**None.**

### Testing strategy (~10 new + ~4 modified tests)

- **Backend per-agent audit-payload tests** (4 new, one per agent): assert that after a successful `evaluate(...)` call, the resulting audit payload's `llm_call` block contains `prompt: { system: str, user: str }` with the actual filled prompts. The Validator's test should specifically assert that the user prompt contains the retrieved chunks (proving placeholder substitution happened).
- **Backend Doc-Parser test**: the sentinel-summary path (Phase 8.2) still calls the LLM, so `llm_call.prompt` should be present even for runs that lean on the record for structured fields.
- **Backend Adjuster demo-fixture test**: assert that when the fixture path triggers (scenario 3), `llm_call.prompt` is `None` or absent (we didn't actually send a prompt to the LLM).
- **Frontend AgentCard test**: expand panel renders the filled prompt from the audit entry (mocked) — assert no `{placeholder}` strings appear in the rendered output.
- **Frontend AgentCard test**: backwards-compatibility — when the audit entry lacks `llm_call.prompt`, the panel falls back to the template endpoint and renders the caveat banner. Mock the audit response without the field; mock the template endpoint to return a template; assert both are rendered.
- **Frontend AgentCard test**: response panel renders from audit `output` when the entry exists; "Waiting…" state only shows when entry is missing AND SSE status is not `done`; error state shows when entry is missing AND SSE status is `done`.

Existing tests that may need updating: any backend audit-shape assertions need to either accept the new field or be widened to ignore it; frontend tests that mocked the prompt endpoint response now need to mock the audit response with `llm_call.prompt`.

### CI changes

**None.**

### New dependencies — flag each one

Expected answer: **none**. All work is structural — adding a field to an audit payload, changing what a frontend component reads from the existing query cache.

### Risks and downstream impacts

**Locked at end of Phase 8.3** (joins the existing extensions list):

- The `llm_call.prompt: { system: str, user: str } | None` field on each of the four agents' audit payloads (`doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`). Additive; existing keys unchanged. The Adjuster demo-fixture path explicitly emits `None` (or omits the field) because no LLM call happened.

**Flagged simplifications/risks:**

- Audit payload size grows. Validator's audit will now be ~10KB instead of ~3KB because retrieved chunks appear in the prompt text. At prototype scale (a few demo runs per day), no concern. In production at scale, JSONB column size and audit-log query performance would need consideration; this is the prototype's deliberate "audit captures everything" posture.
- Backwards compatibility for historical audit entries is handled via the template-endpoint fallback path. Confirm that path is robust.

### Deployment steps requiring architect involvement

- Verify the Render redeploy completes and `/health` reports `version=0.8.3`.
- Re-run the rehearsal end-to-end. The three scenarios should still reproduce as before (no behavioural change in the pipeline). The new observable change is in the expand panel: click into the Adjuster card on the threshold-escalation scenario, confirm the prompt panel shows the *substituted* values (e.g., the actual claim summary text, not `{claim_summary}`), and the response panel shows the JSON output rather than "Waiting…".

### Optional enhancements (labelled; not built)

Carried forward (still deferred): retry via `tenacity`; pricing-table population; real PII redactor; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings` fields; idempotent re-run helper exposed on UI; `claim_status_history` table; auth on the human decision endpoint; audit pagination; dark mode; prompt-diff in the comparison view; standalone ADR log; eager orchestrator construction option; narrative-vs-record consistency check; vision-enabled Doc-Parser.

New for Phase 8.3 (labelled, not built):

- **Migration to backfill `llm_call.prompt` on historical audit entries.** Not done; not worth it. The fallback path handles old entries fine.
- **Per-agent audit pagination in the audit viewer.** The audit list endpoint already returns the full set; the viewer would benefit from pagination once a correlation_id has more than ~50 entries. Current pipelines produce ~12. Deferred.

### Save the plan

Save the plan **before** asking me to review it. Write to:

```
docs/prompts/11-phase-8.3-explainability-panel-fixes-plan.md
```

Top-level heading: `# Plan 11 — Phase 8.3: Explainability Panel Fixes`. Below that, the body of the plan.

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

**If I reject**, append a `## Rejection` footer, rename to `11-phase-8.3-explainability-panel-fixes-plan-rejected-NN.md`, produce a revised plan, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 8.3. Constraints from `CLAUDE.md` apply throughout:

- Defensive programming on the new audit-payload extraction in each agent.
- Function size limits — the changes are small.
- Type hints throughout.
- Tests per the strategy above.
- Anonymisation: client name does not appear anywhere.
- Externalised prompts: no prompt-file changes in this phase.
- Interface stability: the audit payload extension is additive; `llm_call.prompt` is the only new field. The four agent output models are unchanged. The SSE event payloads are unchanged. The frontend types gain one optional field.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.8.2` → `0.8.3`.

## Step 4 — Log

Append a new entry to `docs/build-log.md` with the standard fields.

## Step 5 — Write the report

Save to `docs/prompts/11-phase-8.3-explainability-panel-fixes-report.md`. Standard `## Summary` block.

Body sections cover the two fixes individually (what shipped and what test proves it), the additive audit extension, the backwards-compatibility fallback behaviour, deviations from the plan.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section:

- Date: today's date in ISO format.
- Phase: "Phase 8.3 complete; clone-and-run verification next".
- What works: a one-line summary noting the expand panel now shows the filled prompts and the response from the audit log; the three demo scenarios still reproduce as designed.
- What's next: "Clone-and-run verification."

Also add the `llm_call.prompt` field to the "Locked interface extensions since Phase 4" subsection.

## Step 7 — Git

Single commit covering all the Phase 8.3 work, message:

```
Phase 8.3: explainability panel fixes (filled prompts + response loading)

- Each agent's audit payload now captures the literal system+user prompt sent to the LLM under llm_call.prompt (additive; locked-extension)
- AgentCard expand panel reads the filled prompt from the audit entry instead of the raw template endpoint; falls back to template for historical entries
- AgentCard response panel uses audit-entry existence as the completion signal; "Waiting..." state no longer leaks into post-completion
- Adjuster demo-fixture path explicitly emits llm_call.prompt=None (no LLM call happened)
- pyproject.toml version bumped 0.8.2 -> 0.8.3
- Approved plan archived; build log appended; report written
- CLAUDE.md Current Status updated; locked-extensions list extended
```

Push to `main`; Render auto-deploys.

## Step 8 — Report back

Per the global "After coding" section. End with the action items:

- Verify the Render redeploy completes and `/health` reports `version=0.8.3`.
- Re-run any one demo scenario, expand the Adjuster card, confirm the prompt panel shows real values (no `{placeholders}`) and the response panel shows the JSON output rather than "Waiting…".
- Spot-check one audit entry via the audit viewer and confirm `llm_call.prompt` is present with substituted values.

## Save this prompt

Per the "Save every prompt" standing instruction in `CLAUDE.md`, save this prompt verbatim to `docs/prompts/11-phase-8.3-explainability-panel-fixes.md` if it isn't already there.
