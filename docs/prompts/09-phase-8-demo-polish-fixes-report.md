# Report 09 — Phase 8: Demo Polish Fixes from Rehearsal Discoveries

## Summary

**Recap.** Phase 8 is a focused six-fix pack from the Phase-7 demo rehearsal. The
headline fix restores **live** pipeline visualisation: the run page now mounts and
starts watching the SSE stream *before* the ~27 s run completes, so the agent cards
light up progressively (running → done) instead of all appearing pre-completed. The
remaining fixes make the run page tolerant of the in-flight 404, give each agent card
a real "running" state, embed dollar figures in the demo narratives so Doc-Parser can
extract `claimed_amount`, stop the Guardrail false-positiving on the Adjuster's market
vocabulary, and surface POST failures via an `ErrorBanner`. Version bumped to 0.8.0.
Next: clone-and-run verification.

**Completed at:** 2026-06-15T14:20:00Z
**Phase:** 8 — Demo polish fixes
**Status:** Complete (no deferrals)

**Links**

- Prompt: [`docs/prompts/09-phase-8-demo-polish-fixes.md`](09-phase-8-demo-polish-fixes.md)
- Plan (approved): [`docs/prompts/09-phase-8-demo-polish-fixes-plan.md`](09-phase-8-demo-polish-fixes-plan.md) — approved 2026-06-15T13:45:28Z
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 8 entry)
- Repository: pushed to `main` after this commit lands; Render auto-redeploys.

**CI status.** Unchanged. No new gated categories.

---

## The six fixes

### Fix #1 — Restore live pipeline visualisation

**Symptom (rehearsal).** Clicking *Process* hung on the claims list for the full run,
then jumped to a run page where every agent was already `done`. No live progression.

**Root cause.** Phase 6 had collapsed the Phase-5 "open the stream, *then* trigger"
ordering into `await runPipeline(...)` followed by `navigate(...)`. Awaiting the POST
serialised the entire ~27 s run before the watching page ever mounted.

**Fix.** `ClaimsPage.trigger` is now synchronous: mint a correlation id, `navigate` to
the run page **first**, then fire the run/replay POST fire-and-forget. The event bus
buffers events for late subscribers, so the run page — which mounts a moment after the
POST starts — still receives `pipeline_started` and every subsequent event. The agent
cards now animate as designed.

### Fix #2 — Run page tolerates the in-flight 404

Immediately after navigation there is no run-of-record yet, so `GET /api/runs/{cid}`
404s. `RunDetailPage` no longer treats that as an error: it derives status from the SSE
stream and shows an `awaiting-hint` ("Awaiting pipeline_started…") until the first
event lands. The 404 is the *expected* in-flight state, not a failure.

### Fix #3 — AgentCard "running" state

Each card now has a running block: a per-agent expected duration (`AGENT_EXPECTED_MS`),
a one-line description of what the agent is doing (`copy/agent-descriptions.ts`), and a
`role="progressbar"` driven by a `useProgress` hook.

### Fix #4 — Dollar figures in the demo narratives

The three demo narratives now state their figures in the prose ($85,000 / $850,000 /
$1,400,000), so Doc-Parser extracts a non-zero `claimed_amount` from the text instead
of aborting on `0.00`. The `reported_amount` Decimals are unchanged — only the
narrative copy gained the figures.

### Fix #5 — Guardrail recognises market vocabulary

The Guardrail system prompt now teaches that the Adjuster's settlement framing —
"market band", "mid-range", "within range", "lookup table", "market data" — comes from
an internal market-data table, **not** the policy, and must not be flagged as a
hallucinated citation. Only references to absent policy clauses, endorsements,
sub-limits, exclusions, or named sections count. Scenario 3's real hallucinated
endorsement is still caught (the rule-engine citation regex keys on
endorsement/clause/section keywords that market vocabulary lacks).

### Fix #6 — Surface POST failures via ErrorBanner

A failed run/replay POST is recorded under a `['runError', cid]` query-cache key; the
run page reads it reactively and renders an `ErrorBanner`. Previously a failed POST
silently un-greyed the button with no user-visible signal.

### Fix #7 (bonus) — README audit-payload addendum

The "audit log is the trusted record" design-decision bullet now enumerates the six
additive audit-payload extensions (full Adjuster reasoning; truthful Validator
provider/model; `variant` on `pipeline_started`; the `human` agent +
human_approval/human_rejection steps; the `aborted` status; the `demo_fixture` bool),
with a note that all are additive and the locked list lives in CLAUDE.md.

---

## Design decisions worth recording (per the approval note)

- **D3 — JS-driven progress, not CSS.** A CSS-interpolated width is invisible to jsdom,
  so a pure-CSS bar could not be tested beyond "it exists". The `useProgress` hook ticks
  a percentage with `setInterval`; jsdom can read the value and vitest fake timers can
  advance it, so `advances the progress bar as time passes` is a genuine assertion.
- **D6 — two independent error signals, and *not* `EventSource.onerror`.** A failed
  *start* (POST rejects) and a failed *run* (pipeline aborts mid-flight) are distinct
  failure modes with distinct sources: the POST `.catch` → `['runError', cid]` cache key
  for the former, the `pipeline_aborted` SSE event for the latter. `EventSource.onerror`
  is deliberately avoided as an error signal because it *also* fires on a normal stream
  close, which would raise a spurious banner at the end of every successful run.
- **D1 — drop the per-claim `busy` state.** Because the page navigates away immediately,
  `ClaimsPage` unmounts before the POST resolves; the old "grey the button while
  awaiting" state had no surviving component to render into, and keeping it would only
  produce a setState-on-unmounted warning. The Process button is simply always enabled.

---

## Tests

| Suite | Count | Delta |
|---|---|---|
| Backend (`uv run pytest`) | 330 passing, 7 skipped | +4 |
| Frontend (`vitest`) | 30 passing | +8 |

**Backend additions (4).** `test_demo_narrative_contains_dollar_figure` (parameterised
×3) asserts each demo narrative contains its dollar figure;
`test_market_vocabulary_is_not_flagged` runs the Guardrail over Adjuster reasoning full
of market vocabulary and asserts `passed is True` with no `hallucinated_citation` flag.

**Frontend additions (8).** New `ClaimsPage.test.tsx` (navigates immediately on
Process; fires the POST in the background); new `RunDetailPage.test.tsx` (queued cards +
awaiting hint on 404; `pipeline_aborted` → alert; `['runError', cid]` → alert);
`AgentCard` running-state ×3 (description + duration + progressbar; bar advances under
fake timers; no bar once done).

**Static checks.** `ruff` clean; `mypy backend` clean (106 source files); frontend
`tsc` and `eslint` clean.

---

## Deviations from the approved plan

None. All decisions D1–D7 were approved as written; the only request was that the D3,
D6, and D1 reasoning be carried into this report, which the section above does.

---

## Action items for the architect

1. **Confirm `/health` reports `version=0.8.0`** on the deployed backend after Render
   redeploys.
2. **Re-seed the deployed Neon database** so the three demo claims carry the new
   narratives (with dollar figures) — otherwise Doc-Parser will still see `0.00` from
   the old seed rows.
3. **Re-run the demo rehearsal end-to-end** against the deployed stack and watch the
   live agent cards progress (running → done) for all three scenarios.
4. **Spot-check scenario 3** still escalates on the real hallucinated endorsement now
   that the Guardrail prompt tolerates market vocabulary.
