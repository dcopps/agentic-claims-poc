# Plan 11 — Phase 8.3: Explainability Panel Fixes

Three surgical fixes, one commit. All make the agent expand panel and the
audit page usable end-to-end. No new dependencies, no settings, no CI
changes. The one interface event is an **additive** extension to the four
agents' audit payloads (`llm_call.prompt`), joining the locked-extensions
list.

---

## Cross-cutting questions (answers / push-back)

1. **Where does the literal prompt live?** — **Agree:** nested as
   `llm_call.prompt: { system: str, user: str }`. The `llm_call` block already
   holds "what we sent" metadata; the prompt text is its natural extension and
   keeps all LLM-call detail in one place.

2. **What does it include?** — **Agree:** the *substituted* user prompt (the
   exact string `PromptLoader.user(name, **kwargs)` returned for this call) plus
   the system prompt (`PromptLoader.system(name)`). Both plain UTF-8, no extra
   formatting, stored verbatim (no excerpt truncation — the whole point is to
   capture the literal text the model saw). Validator's is the largest (~retrieved
   chunks inline); comfortably within JSONB at prototype scale.

3. **Backwards-compat for old entries.** — **Agree, with a small precision note.**
   The panel renders the filled prompt when `llm_call.prompt` exists; otherwise it
   falls back to the existing template endpoint with the caveat banner. I will use
   the spec's exact caveat text ("Showing the prompt template — this run pre-dates
   the audit-prompt-capture change."). **Note:** the same fallback also fires in the
   rare in-flight case where a card is expanded *before* its audit entry is written;
   there the "pre-dates" wording is slightly inaccurate but transient and harmless.
   I judge a second caveat variant to be over-engineering for a sub-second window;
   flagging it rather than silently building it.

4. **Keep `GET /api/agents/{agent}/prompt`?** — **Agree, keep, unchanged.** Still
   serves the agent test bench and the Fix-A fallback. Its semantics (raw template,
   placeholders intact) do not change. Only the run-detail panel switches its
   *primary* source to the audit entry.

5. **Authoritative completion signal for the response panel.** — **Agree:** the
   audit entry's existence. SSE still drives the live status badge; the response
   *content* always comes from the audit entry's response block.

6. **Fix B state machine.** — **Agree**, implemented exactly as the three explicit
   states: entry exists → render response block; entry missing **and** SSE status
   ≠ `done` → "Waiting…"; entry missing **and** SSE status = `done` → explicit
   error state ("Audit entry not found for this completed agent — this may indicate
   a write failure."). This last state should never occur in normal operation; if
   it does, a missing entry on a done agent is a real audit-integrity problem worth
   surfacing rather than hiding behind "Waiting…".

**One design decision beyond the questions — frontend data flow.** The prompt
suggests `AgentCard` consult `useAuditEntries(correlation_id)` itself. `AgentCard`
currently has no `correlationId` prop, and `RunDetailPage` *already* holds
`audit.data` and does the per-step lookup (`_payload`). Rather than open a second
subscription and thread `correlationId` down, I will **pass the resolved
`AuditEntry | undefined` down as a prop** (replacing today's `responsePayload`).
The data still originates from `useAuditEntries` (satisfying "single source of
truth = the audit log"); `AgentCard` stays a thin component whose tests inject
props directly. This is a prop-shape change on an internal component only — no
cross-boundary contract moves. Flagging it as the one interface change inside the
frontend. If you'd rather `AgentCard` call the hook itself (closer to the prompt's
literal wording), say so and I'll thread `correlationId` instead.

---

## Files to modify

### Backend — Fix A (capture the literal prompt)

A small frozen dataclass carries the two prompt strings from each agent's
`_invoke_llm` out to its audit builder, so the four call sites share one typed
shape instead of a bare `tuple[str, str]`.

- **`backend/app/agents/_shared.py`**
  - Add `@dataclass(frozen=True) class CapturedPrompt: system: str; user: str`.
    One reusable type; documents the two-field shape; type-checks at every call
    site.

- **`backend/app/agents/doc_parser.py`**
  - `_invoke_llm`: build `prompt = CapturedPrompt(system_prompt, user_prompt)`
    right after the two strings are constructed; add it as the **5th** element of
    every return tuple (success, summary-validation-fail, provider-exception — the
    prompt exists on all three because it is built before the call).
  - `evaluate` / `parse`: unpack the new element; `evaluate` passes
    `prompt=prompt` into `_write_audit`; `parse` ignores it (`_prompt`).
  - `_write_audit` + `_build_audit_payload`: accept `prompt: CapturedPrompt | None`
    and, when non-None, set `llm_call["prompt"] = {"system": …, "user": …}`. Added
    to **both** branches of the existing `llm_call` conditional (the prompt is
    present whether or not a `ProviderResponse` came back).

- **`backend/app/agents/validator.py`** — same pattern: 5th tuple element from
  `_invoke_llm`; `evaluate` threads `prompt`, `assess` ignores it;
  `_build_audit_payload` adds `llm_call["prompt"]` when present.

- **`backend/app/agents/adjuster.py`** — same pattern, plus the demo-fixture lock:
  - `_invoke_llm` returns the 5th element.
  - `evaluate`: the live branch unpacks `prompt`; the **fixture branch** sets
    `prompt = None` (no `_invoke_llm` call, so no prompt was built or sent).
  - `_llm_call_block(response, latency_ms, demo_fixture, prompt)`: gains a `prompt`
    param; adds `"prompt"` only when `prompt is not None`. The `demo_fixture`
    branch is always called with `prompt=None`, so **the fixture path emits no
    `prompt` key** — locked, truthful (no prompt was sent).
  - `estimate` (probe) ignores the new element.

- **`backend/app/agents/guardrail.py`** — same pattern as doc_parser/validator;
  `evaluate` threads `prompt`, `check` ignores it.

No prompt-template files change. No agent output model changes. No
`agents_test.py` change.

### Backend — version bump

- **`pyproject.toml`** — `version = "0.8.2"` → `"0.8.3"`. `/health` reads this via
  `importlib.metadata.version`, so it reports `0.8.3` once deployed.

### Frontend — Fix A + Fix B (`AgentCard`)

- **`frontend/src/components/AgentCard.tsx`**
  - Replace prop `responsePayload?: unknown` with `auditEntry?: AuditEntry`.
  - Add two small typed extractors (module-local helpers, defensive shape checks
    over `payload: Record<string, unknown>`):
    - `extractPrompt(entry?): { system: string; user: string } | null` — reads
      `payload.llm_call.prompt` only when both fields are strings.
    - `extractResponseBlock(entry?): unknown` — moves today's `output ?? verdict ??
      payload` logic out of `RunDetailPage._payload` into the card.
  - **Fix A prompt panel:** if `extractPrompt` returns a value → render its
    `system`/`user` in the existing two `<pre>` blocks, no fetch, no caveat. Else →
    fall back to `useAgentPrompt(agent, variant, expanded && !hasFilledPrompt)`
    (lazy + only when needed) and render the caveat banner above it.
  - **Fix B response panel:** three explicit states per Q6 — entry present →
    `JsonBlock` of `extractResponseBlock`; entry absent & `status === 'done'` →
    error state; otherwise → "Waiting…".

- **`frontend/src/pages/RunDetailPage.tsx`**
  - Pass `auditEntry={_entry(agent.step, audit.data)}` (new tiny helper returning
    the `AuditEntry` for that step) instead of `responsePayload={_payload(...)}`.
    `_payload` is removed; its extraction logic now lives in `AgentCard`.
  - **Fix C1:** replace the truncated `correlationId.slice(0, 8)` in the header
    with the full UUID plus a `CopyButton`.
  - **Fix C2:** add a `<Link to={\`/audit?correlation_id=${correlationId}\`}>View
    audit log</Link>` in the header.

- **`frontend/src/components/ui.tsx`**
  - Add `CopyButton({ value, label? })` (~15 lines): Tailwind-styled, calls
    `navigator.clipboard.writeText(value)`, flips to "Copied" for 1500ms via a
    `setTimeout`, then reverts. Cleans the timer on unmount.

- **`frontend/src/api/types.ts`**
  - No required change to `AuditEntry` (its `payload` stays `Record<string,
    unknown>`; the extractors read defensively). The TS types gain nothing
    mandatory; the audit-prompt shape is read structurally.

- **`frontend/src/pages/AuditPage.tsx`** — **no change.** It already reads
  `?correlation_id=` via `useSearchParams` and seeds the filter input
  (`useState(cid)`), so the Fix-C2 deep link pre-populates and renders on mount.
  Verified, called out so we don't touch a working page.

---

## Tests (~10 new, ~4 modified)

### Backend (new)

- **One per agent** (`test_doc_parser.py`, `test_validator.py`,
  `test_adjuster.py`, `test_guardrail.py`): after a successful `evaluate(...)`
  with the mock provider, assert
  `payload["llm_call"]["prompt"]["system"]` and `["user"]` are non-empty strings.
  - **Validator** additionally asserts the captured `user` prompt contains a
    retrieved chunk's content — proving placeholder substitution actually happened
    (the whole point of Fix A).
  - **Adjuster** additionally asserts the `user` prompt contains a market-range
    bound / the claim summary.
  - **Doc-Parser** additionally asserts the `user` prompt contains the claim
    narrative (the Phase-8.2 record-sourced path still calls the LLM, so the prompt
    is captured there too).
- **`test_demo_fixture.py`** (modify): alongside the existing
  `llm_call.provider == "demo_fixture"` assertion, add
  `assert "prompt" not in row[0]["llm_call"]` — the fixture path sent no prompt.

### Frontend (new / modified — `AgentCard.test.tsx`)

- Expand panel renders the **filled** prompt from a mocked `auditEntry` carrying
  `llm_call.prompt`; assert **no `{placeholder}` strings** appear and the template
  endpoint is **not** fetched.
- Backwards-compat: `auditEntry` lacks `llm_call.prompt` → panel fetches the
  template endpoint and renders the caveat banner (mock both).
- Response panel: renders from the audit response block when `auditEntry` exists;
  shows "Waiting…" when absent and status ≠ `done`; shows the error state when
  absent and status = `done`.
- Update the existing two tests that pass `responsePayload=` to pass `auditEntry=`.

### Frontend (new / modified — `RunDetailPage.test.tsx`)

- Full correlation_id is rendered (not the 8-char prefix).
- `CopyButton` calls `navigator.clipboard.writeText` with the full UUID (mock the
  clipboard API).
- "View audit log" link points to `/audit?correlation_id=<cid>`.

---

## Interface stability — locked at end of Phase 8.3

- **`llm_call.prompt: { system: str, user: str } | (absent)`** on each of the four
  agents' audit payloads (`doc_extract`, `coverage_check`, `settlement_estimate`,
  `output_check`). Additive; all existing keys unchanged; preserves the
  audit-log-as-trusted-record property. The Adjuster demo-fixture path emits **no**
  `prompt` key (no LLM call happened). This entry is added to CLAUDE.md's
  "Locked interface extensions since Phase 4" subsection.
- **Internal frontend prop change** (not a crossing contract): `AgentCard`'s
  `responsePayload?: unknown` → `auditEntry?: AuditEntry`.

---

## Risks / flagged items

- **Audit row size grows** (Validator ~3KB → ~10KB as retrieved chunks now appear
  in the captured prompt). No concern at prototype scale; in production, JSONB size
  and audit-query cost would warrant attention. This is the prototype's deliberate
  "audit captures everything" posture.
- **Caveat-text precision** in the in-flight-before-entry window (Q3 note above) —
  flagged, not separately handled.
- **No behavioural change** to the pipeline: the three demo scenarios reproduce
  exactly as before; the only observable change is inside the expand panel and the
  run header.

## New dependencies

**None.**

## Optional enhancements (labelled; not built)

- Second caveat variant distinguishing "historical run" from "entry not yet
  written" (Q3). Deferred — sub-second window, low value.
- Backfill migration for `llm_call.prompt` on historical entries. Not worth it;
  the fallback handles old runs.
- Per-agent audit pagination in the viewer. Deferred (current runs ~12 entries).

---

## Execution order (after approval)

1. Backend: `CapturedPrompt` + thread through four agents + audit builders.
2. Backend tests (4 new + `test_demo_fixture.py` assertion); run `pytest`, `ruff`,
   `mypy`.
3. Frontend: `CopyButton`, `AgentCard` (A+B), `RunDetailPage` (C1+C2 + prop swap).
4. Frontend tests; run `vitest`, `tsc`, `eslint`.
5. `pyproject.toml` 0.8.2 → 0.8.3.
6. Build log, report, CLAUDE.md status + locked-extensions entry.
7. Single commit, push to `main`.

---

## Approval

**Approval message:** "Approved as written. The frontend data-flow design (pass AuditEntry down as a prop from RunDetailPage rather than have AgentCard call useAuditEntries itself) is the better architecture and the right answer. Include the Fix B diagnostic correction in the report explicitly — the actual bug was undefined merging the two missing-entry cases, not SSE-event presence; the three-state machine handles both correctly regardless. Then append the ## Approval footer and proceed to Step 3."

---

**Approved by:** Dermot Copps
**Approved at:** 2026-06-16T11:24:52Z
