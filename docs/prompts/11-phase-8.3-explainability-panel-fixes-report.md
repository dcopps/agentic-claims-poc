# Report 11 — Phase 8.3: Explainability Panel Fixes

## Summary

| | |
|---|---|
| **Phase** | 8.3 — Explainability Panel Fixes |
| **Date** | 2026-06-16 |
| **Prompt** | [`11-phase-8.3-explainability-panel-fixes.md`](11-phase-8.3-explainability-panel-fixes.md) |
| **Plan (approved)** | [`11-phase-8.3-explainability-panel-fixes-plan.md`](11-phase-8.3-explainability-panel-fixes-plan.md) — approved 2026-06-16T11:24:52Z |
| **Plan iterations** | 0 rejected |
| **Version** | 0.8.2 → 0.8.3 |
| **Tests** | 331 backend passing (7 skipped), +4; 36 frontend passing, +6 |
| **Quality gates** | ruff clean · mypy clean (106 files) · tsc clean · eslint clean · vitest clean |
| **New dependencies** | none |
| **New settings** | none |

Three surgical fixes, shipped in one commit, to make the explainability surfaces
deliver on the Phase 6 promise ("each card expands to show exactly what ran — the
prompt the agent used, and its raw response, pulled straight from the audit log")
and to make the chain-verifiable Audit page reachable in one click from a run.

---

## Fix A — the expand panel shows the *filled* prompt the LLM actually received

**What shipped.** Each agent now captures the literal system + user prompt it sent
to the model and records it in the audit payload under `llm_call.prompt`. The
run-detail expand panel reads from there (the single source of truth) instead of
fetching the raw template, so a reviewer sees the substituted text — the real claim
summary, the retrieved chunks, the market range — not `{claim_summary}` /
`{retrieved_chunks}` placeholder tokens.

**How it works.**
- `backend/app/agents/_shared.py` gained a frozen `CapturedPrompt(system, user)`
  and an `attach_prompt(llm_call, prompt)` helper. Each agent's `_invoke_llm`
  builds the `CapturedPrompt` *before* the provider call and returns it as a 5th
  tuple element, so the prompt is captured on every path — success, parse-failure,
  and provider-exception alike. `evaluate` threads it through `_write_audit` into
  `_build_audit_payload`, which calls `attach_prompt` on the `llm_call` block.
- `frontend/src/components/AgentCard.tsx` extracts `llm_call.prompt` from the audit
  entry (`extractPrompt`) and renders the two strings in `<pre>` blocks. When the
  field is absent it falls back to the existing template endpoint with a caveat
  banner (`TemplateFallback`).

**What proves it.**
- Backend, one test per agent: after `evaluate(...)`, `llm_call.prompt.system` and
  `.user` are non-empty strings equal to what the mock provider received. The
  **Validator** test asserts a retrieved chunk's content appears verbatim in the
  captured user prompt and `{retrieved_chunks}` does not — direct proof that
  substitution happened. The **Adjuster** test asserts the market range; the
  **Doc-Parser** the narrative; the **Guardrail** the adjuster reasoning.
- Frontend `AgentCard.test.tsx`: the panel renders `FILLED-SYSTEM` / `FILLED-USER`
  from a mocked audit entry, asserts no `{claim_narrative}` placeholder leaks, and
  asserts the template endpoint was **not** fetched (`fetchMock` uncalled).

---

## Fix B — the response panel uses the audit entry as the completion signal

**What shipped.** The response section renders the agent's output block whenever
its audit entry exists, and only shows "Waiting…" when the entry genuinely is not
yet written. A new, distinct error state appears if an agent reports `done` but has
no audit entry.

**Diagnostic correction (called out per the approval).** The prompt hypothesised
the persistent "Waiting…" came from the panel testing for SSE-event presence. That
was not the mechanism in this codebase: the response already read from the audit
log (`RunDetailPage._payload` → `audit.data`), not from SSE. The actual defect was
that an `undefined` response payload **silently merged two distinct missing-entry
cases** — "entry not written yet" (legitimately in flight) and "entry missing for a
completed agent" (an audit-integrity problem). The new `ResponsePanel` makes the
state machine explicit:

| Audit entry | SSE status | Renders |
|---|---|---|
| present | any | the response block (`output ?? verdict ?? payload`) |
| absent | not `done` | "Waiting for this agent to complete…" |
| absent | `done` | "Audit entry not found for this completed agent — this may indicate a write failure." |

This fixes the reported behaviour regardless of the original hypothesis, and it
turns a silent gap into a surfaced error — consistent with the project's
audit-log-as-trusted-record posture.

**What proves it.** `AgentCard.test.tsx` covers all three rows: response renders
from the audit `output`; "Waiting…" shows only when the entry is absent and the
agent is not `done`; the audit-integrity error shows when the entry is absent and
the agent is `done`.

---

## Fix C — the audit page is reachable from the run, correlation_id pre-filled

**C1 — full correlation_id + copy.** The run header now shows the full UUID
(replacing the 8-char prefix) alongside a new `CopyButton` (`ui.tsx`) that writes to
`navigator.clipboard` and flips to "Copied" for 1500ms (the revert timer is cleared
on unmount via an effect, avoiding a setState-after-unmount warning).

**C2 — one-click audit view.** A "View audit log" `<Link to="/audit?correlation_id=…">`
sits next to the id. `AuditPage` already reads the `correlation_id` query param on
mount and seeds its filter, so the deep link lands on the audit view of the same
run with **no change to that page**.

**What proves it.** `RunDetailPage.test.tsx`: the full UUID renders (not a prefix);
the copy button calls `navigator.clipboard.writeText` with the full UUID; the link
points to `/audit?correlation_id=<uuid>`.

---

## The additive audit extension (locked)

`llm_call.prompt: { system: str, user: str } | (absent)` joins the four agents'
audit payloads (`doc_extract`, `coverage_check`, `settlement_estimate`,
`output_check`). It is strictly additive — every existing key is unchanged — so the
audit-log-as-trusted-record property holds: the log alone still reconstructs and
explains any past decision, now including the literal prompt the model saw. The
Adjuster demo-fixture path emits **no** `prompt` key, because no prompt was sent;
fabricating the prompt-that-would-have-been-sent would have been a lie in the trail.
This entry is recorded in CLAUDE.md's "Locked interface extensions since Phase 4".

## Backwards-compatibility fallback

Historical audit entries written before this phase carry no `llm_call.prompt`. For
those, `AgentCard` falls back to the raw template endpoint (`GET
/api/agents/{agent}/prompt`) and renders a caveat banner ("Showing the prompt
template — this run pre-dates the audit-prompt-capture change."), so old runs stay
viewable without misleading the reviewer into thinking the placeholders are the
substituted text. The same fallback also covers the transient in-flight window
where a card is expanded before its entry is written; the "pre-dates" wording is
slightly imprecise there but the window is sub-second (flagged in the plan, a second
caveat variant deferred as over-engineering).

## Deviations from the plan

- **None of substance.** The plan was executed as written. The one notable
  implementation detail not specified in the plan: the copy-button test uses
  `fireEvent.click` rather than `userEvent.click`, because `userEvent.setup()`
  installs its own `navigator.clipboard` stub that would shadow the test's spy.

## Guard clauses / defensive notes added beyond the spec

- `extractPrompt` defensively checks that `llm_call`, `prompt`, and both
  `system`/`user` are the expected types before returning — a malformed or partial
  `llm_call.prompt` falls back to the template rather than rendering `undefined`.
- `attach_prompt` is the single place the additive field is written, so the
  "present only when a call happened" invariant cannot drift across the four agents.

## Optional enhancements (labelled, not built)

- A second caveat variant distinguishing "historical run" from "entry not yet
  written" (sub-second window, low value).
- A backfill migration for `llm_call.prompt` on historical entries (the fallback
  handles them).
- Per-agent audit pagination in the viewer (current runs ~12 entries).

## Action items for the architect

- Verify the Render redeploy completes and `/health` reports `version=0.8.3`.
- Re-run any one demo scenario, expand the Adjuster card, confirm the prompt panel
  shows real values (no `{placeholders}`) and the response panel shows the JSON
  output rather than "Waiting…".
- Spot-check one audit entry in the viewer and confirm `llm_call.prompt` is present
  with substituted values.
