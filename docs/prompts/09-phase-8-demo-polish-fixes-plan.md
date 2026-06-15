# Plan 09 — Phase 8: Demo Polish Fixes

A focused six-fix polish pack from the Phase 7 demo rehearsal. No architecture
change, no locked-interface change — bug fixes and UI polish on existing surfaces,
plus a Guardrail prompt tweak and three seed-narrative rewrites. Short plan; the
cross-cutting decisions mostly accept the prompt's recommendations, with two small
implementation flags noted below.

---

## 1. Decisions

### D1 — Fix #1: navigate-first, fire-and-forget POST (accept)
`ClaimsPage.trigger` is rewritten to **navigate immediately**, then kick the POST
off without `await`. The run-detail page mounts and opens the SSE subscription
while the POST is still early; the Phase 4 event bus buffers late subscribers, so
the SSE-first sequencing is safe. `.then(refetch)` refreshes the claims list when
the POST resolves; `.catch(...)` records the error (D6). The per-claim `busy`
state is **dropped** — navigation is the immediate feedback, and setting state on
the now-unmounted ClaimsPage would warn.

### D2 — Fix #2: 404 during in-flight is expected (accept)
`useRun` / `useAuditEntries` already use `retry:false`. The run-detail page already
renders the agent cards from SSE events (queued when none yet) and never renders
`run.error` — so a 404 is already non-fatal. The fix adds: an **"Awaiting
pipeline_started…"** hint while no events have arrived, and ensures the error
banner (D6) shows only for *real* failures (a POST failure or a `pipeline_aborted`
event), never the in-flight 404.

### D3 — Fix #3: expected durations + JS-driven progress (accept, with a flag)
Per-agent expected durations as a single config object beside `AgentCard`
(empirical from Phase 8 rehearsal, conservative): **Doc-Parser 6s, Validator 9s,
Adjuster 7s, Guardrail 5s** — display-only; the SSE `agent_completed` always wins.
Per-agent one-sentence descriptions live in a new `frontend/src/copy/agent-descriptions.ts`.
**Flag:** the progress bar is **JS-driven** (a small `setInterval` advancing a
percentage from elapsed/expected, smoothed with a CSS `width` transition) rather
than pure CSS. Reason: a pure-CSS transition sets the inline width to the target
immediately and only the browser interpolates — jsdom can't observe intermediate
widths, so the "width increases over time" test would be untestable. The JS
percentage is observable with Vitest fake timers. No animation library; ~12 lines.
The bar caps at 100% if the agent runs over; the card stays `running` until the
actual completion event.

### D4 — Fix #4: rewrite the three demo narratives only (accept)
Rewrite the auto-approve, threshold-escalation, and guardrail-escalation seed
narratives to naturally embed the dollar figure (`$85,000` / `$850,000` /
`$1,400,000`). Background claims are left untouched — they're off the demo path and
are useful edge cases. The amounts stay consistent with the existing
`reported_amount` Decimals and the market-data ranges that drive each scenario.

### D5 — Fix #5: Guardrail prompt sentence (accept)
Add a sentence to `backend/app/prompts/system/guardrail.md` near the
hallucinated-citation instructions naming the Adjuster's market vocabulary
("market band", "mid-range", "within range", "lookup table", "market data") as
non-policy framing to ignore — surgically, without weakening detection of real
hallucinated endorsements (scenario 3's "Endorsement Coastal Surge Rider" is a
genuine clause-like citation and must still flag). Externalised prompt; no inline
f-string.

### D6 — Fix #6: ErrorBanner + two error signals (accept, with a flag)
A small `ErrorBanner` primitive in `components/ui.tsx` (styled `div`, no toast
library). Two error signals reach the run-detail page:
1. **POST transport failure** (502 cold start, timeout, network) — the `.catch`
   in ClaimsPage's fire-and-forget writes `queryClient.setQueryData(['runError', cid], message)`;
   the run-detail page reads that key and renders the banner. This works across the
   navigation because the QueryClient is app-level.
2. **Backend pipeline abort** — the `pipeline_aborted` SSE event (already in the
   stream); the page renders the aborted state visibly.
**Flag:** `EventSource.onerror` is **not** used as an error signal — it fires on
every normal stream close (after our terminal sentinel) and on reconnect attempts,
so it cannot distinguish "couldn't connect" from "finished". Transport failures are
covered by signal (1); backend failures by signal (2). Documented.

### D7 — Fix #7: README audit-payload addendum
The README's "Design decisions and trade-offs" section already carries an
"audit log is the trusted record" bullet **summarising** the additive extensions
and linking to `CLAUDE.md`'s locked list — but it does not enumerate them. Per fix
#7, add a one-paragraph note enumerating the additive extensions (full Adjuster
reasoning, truthful Validator provider/model, run `variant`, `human` agent,
`aborted` status, `demo_fixture`) so an outward-facing reader sees them without
opening `CLAUDE.md`.

**Net new dependencies: none.**

---

## 2. Files created / modified

**Backend**
- `backend/app/prompts/system/guardrail.md` — the market-vocabulary sentence (D5).
- `backend/data/seed_claims.py` — three demo narratives rewritten with dollar amounts (D4).
- `backend/tests/test_seed_claims.py` — assert each demo narrative contains its dollar figure.
- `backend/tests/test_guardrail.py` — regression: stock Adjuster reasoning with market vocabulary is not flagged (mocked benign LLM).
- `pyproject.toml` — `0.7.0 → 0.8.0`.

**Frontend**
- `frontend/src/pages/ClaimsPage.tsx` — navigate-first, fire-and-forget, error-aware `.catch` (D1, D6).
- `frontend/src/pages/RunDetailPage.tsx` — "awaiting" hint, error-banner wiring, in-flight 404 tolerance (D2, D6).
- `frontend/src/components/AgentCard.tsx` — running-state UI: expected duration, description, JS-driven progress bar (D3).
- `frontend/src/copy/agent-descriptions.ts` — new; per-agent description strings.
- `frontend/src/components/ui.tsx` — new `ErrorBanner` primitive (D6).
- `frontend/src/hooks/useRunStream.ts` — verified; minor: expose nothing new (onerror not used, D6). No signature change needed beyond what the page reads.
- Component tests updated/added for the new shapes.

**Docs**
- `README.md` — enumerate the audit-payload addendum (D7).
- `CLAUDE.md` — Current Status (Step 6).

---

## 3. Testing strategy (~13 new/updated)

- **ClaimsPage** (~3): clicking Process navigates immediately (URL changes before the POST mock resolves); a rejected POST writes the run-error and the banner shows on the run page; the claims list refetches after a resolved POST.
- **RunDetailPage** (~3): renders queued cards + "awaiting" hint when the runs API 404s; a synthetic SSE event updates a card's state; a `pipeline_aborted` event renders the ErrorBanner.
- **AgentCard** (~3): running state shows the expected duration + description; the progress percentage increases as fake-timer time advances; the bar/card flip to done at 100% on `agent_completed`.
- **Guardrail regression** (~1): a stock reasoning containing "market band" / "within range" trips no hallucinated-citation flag (rule engine + mocked benign LLM).
- **Seed regression** (~3): each demo narrative contains `$85,000` / `$850,000` / `$1,400,000`.

Existing tests touching these components are updated for the new props.

---

## 4. Risks / interface stability
No locked contract changes. PipelineResult, EscalationDecision, SSE payloads, and
audit payloads are unchanged. The Guardrail prompt change is internal (output shape
unchanged). The narrative rewrites change seed *content*, not *shape*. The
agent-description copy and `ErrorBanner` are additive. The `['runError', cid]`
Query key is a frontend-only convention.

---

## 5. Optional enhancements (labelled; not built)
Carried forward (unchanged list). New for Phase 8: an env-driven `LAZY_ORCHESTRATOR`
flag to optionally eager-build the orchestrator in demo environments (removes the
first-request cold-load; default stays lazy); per-variant running-state copy via the
variant registry (likely over-engineered).

---

## 6. Execution order
1. `pyproject.toml` 0.7.0→0.8.0.
2. Backend: guardrail prompt sentence; seed narratives; seed + guardrail tests.
3. Frontend: `ErrorBanner` + `agent-descriptions.ts`; AgentCard running UI; ClaimsPage fire-and-forget; RunDetailPage 404/error handling; useRunStream check; tests.
4. README addendum; CLAUDE.md status.
5. ruff/mypy/pytest + frontend tsc/eslint/vitest green; build-log; report; commit; push.

---

**Verdict requested.** Please review — especially **D3** (JS-driven progress bar
rather than pure CSS, so "width increases over time" is testable in jsdom) and
**D6** (the two error signals — POST `.catch` via a `['runError', cid]` cache key
and the `pipeline_aborted` SSE event — with `EventSource.onerror` deliberately not
used because it fires on normal close). On approval I'll record the `## Approval`
footer and proceed to Step 3.

---

## Approval

**Approval message:** "Approved as written. D3 (JS-driven progress for testability), D6 (two error signals, no EventSource.onerror), and the busy-state drop in D1 are all correct calls and worth recording the reasoning in the report. Then append the ## Approval footer and proceed to Step 3."

**Approval note:** D3 (JS-driven progress for jsdom testability), D6 (two error signals — POST `.catch` via `['runError', cid]` + `pipeline_aborted` SSE; `EventSource.onerror` deliberately not used), and the D1 busy-state drop are confirmed; their reasoning is carried into the report. All decisions (D1–D7) approved as written.

---

**Approved by:** Dermot Copps
**Approved at:** 2026-06-15T13:45:28Z
