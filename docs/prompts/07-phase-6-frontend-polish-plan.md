# Plan 07 — Phase 6: Frontend Polish

Turn the Phase 5 functional UI into a polished React SPA with routing, a
consistent design system, live pipeline visualisation, an audit-log viewer with
one-click chain verification, a human-review panel, and an agent test bench —
plus the backend endpoints and the one schema migration that those surfaces
require. The three demo scenarios continue to pass.

Written against the real Phase 4/5 interfaces (the orchestrator, the runs/claims
APIs, the audit writer + verifier, the variant registry, the PromptLoader) and
the actual frontend dependency set. Collisions and judgement calls are surfaced
under **Decisions needing confirmation**.

---

## 1. Decisions needing confirmation

### D1 — Adopt TanStack Query (new dependency)
**Recommend yes**, per the prompt. Post-mutation refetches (submit/run/replay/
human-decision), cached runs lists, per-route staleness, and SSE-driven cache
invalidation are real polish that plain `fetch`+`useEffect` re-implements badly.
The three Phase 5 hooks (`useClaims`, `useRunStream`, plus inline fetches in
`CompareView`) are replaced by `useQuery`/`useMutation` equivalents. **New dep:
`@tanstack/react-query`.**

### D2 — Adopt `react-router-dom` (new dependency)
**Recommend yes**, per the prompt. Six routes (below) replace the Phase 5 view
toggle; a comparison URL becomes shareable. **New dep: `react-router-dom`.**

| Path | Component |
|---|---|
| `/` | Claims list (landing) |
| `/claims/:claimId` | Single-claim view (metadata + status timeline + runs + live progress) |
| `/claims/:claimId/runs/:correlationId` | Single-run detail (live pipeline viz / historical) |
| `/claims/:claimId/compare/:a/:b` | Comparison view (deep-linkable) |
| `/audit` | Audit-log viewer (`?correlation_id=`) |
| `/agents` | Agent test bench |

### D3 — UI: Tailwind primitives + a small internal component set
**Recommend yes**, per the prompt. An internal `components/ui/` (Button, Badge,
Card, Modal, StatusBadge, Spinner) — no shadcn/Headless dependency. Keeps the
surface small, readable, and Tailwind-v4-native.

### D4 — Chain verification is **global**, not per-correlation_id (flag)
The hash chain spans the **entire** `audit_log` — `chain_hash` links every row
across the ledger in `audit_id` order, so a single correlation_id's rows cannot
be verified as an isolated chain. The prompt specifies
`GET /api/audit/verify/{correlation_id}`.

**Recommendation:** keep the path, but the endpoint runs the existing
**full-ledger** `verify_chain` and returns its `ChainVerification`. The
`correlation_id` is used to (a) 404 if it has no audit entries and (b) give the
UI context. The "Verify chain" UI copy says it verifies *the whole ledger* (which
is the truthful, correct tamper-evidence semantics — a break anywhere matters).
This is a documented prototype framing, not a behavioural compromise.

> Alternative offered: drop the path param and expose `GET /api/audit/verify`
> (global). I recommend keeping the prompt's path with the global semantics
> documented, since the UI reaches it from a run context. Confirm.

### D5 — Agent test bench needs a no-audit "probe" path (additive agent refactor)
`evaluate(...)` writes an audit entry and requires a real `claim_id` (the audit
FK). A test-bench call has an arbitrary narrative, no claim, and must write **no**
audit entry (per the prompt — only the APILogger entry that `provider.complete`
already emits).

**Recommendation:** extract each agent's non-audit core into an additive public
method; `evaluate` becomes *probe + audit*. Behaviour-preserving (existing tests
unchanged):

| Agent | New method | Does |
|---|---|---|
| Doc-Parser | `parse(narrative) -> DocParserResultCore` | build prompt → complete → parse |
| Validator | `assess(narrative) -> ValidatorAssessment` | embed → retrieve → complete → parse |
| Adjuster | `estimate(parsed, verdict) -> AdjusterEstimate` | lookup range → complete → parse |
| Guardrail | `check(adjuster_output, chunks) -> GuardrailOutput` | rules → complete → parse → combine |

Each core method returns the typed output plus the `ProviderResponse` metadata
(model, tokens, latency) the bench displays. `evaluate` calls the core then writes
audit exactly as today. The Validator's `assess` needs a `claim_id`-free path:
the test endpoint supplies the narrative directly (no DB claim read). This is the
one substantive agent change in Phase 6; flagged as additive.

### D6 — Prompt-display endpoint + `PromptLoader.raw`
The expand panel shows the **system + user** prompt for the agent/variant. The
PromptLoader's `user(name, **kwargs)` *formats* (strict) — the panel wants the raw
template with placeholders. **Recommendation:** add `PromptLoader.raw(kind, name)`
returning the unformatted file content (additive; same path-traversal + size
guards), and an endpoint `GET /api/agents/{agent}/prompt?variant=<name>` returning
`{system, user, variant}`. The variant resolves which user template the agent
uses (e.g. `validator_strict` for `v2_strict_validator`).

### D7 — Human decision: add `'human'` to the audit agent set; reuse `settled`/`aborted`
Per the prompt. The `AuditEvent.agent` Literal (`event.py`) and the `audit_log`
agent CHECK both gain `'human'` (additive). New audit steps `human_approval` /
`human_rejection`. On approval → claim `status='settled'`; on rejection →
`status='aborted'`. **No new `claim_status` values** (the *reason* lives in the
audit entry). The human decision is written under the claim's **most recent run's
correlation_id**, so it links to the run it decides.

### D8 — Lazy fetch of prompt + payload on card expansion
Per the prompt. The run-detail view paints fast; expanding an agent card fetches
its prompt and audit payload on demand.

### D9 — Frontend test mocking: mocked `fetch`, no `msw`
**Recommend no `msw`.** A small `renderWithProviders` helper (QueryClient with
retries off + MemoryRouter) plus `vi.stubGlobal('fetch', …)` covers the component
tests without a third dependency. Flag: if a test genuinely needs request
interception we'll reconsider, but the expected answer is no `msw`.

**Net new dependencies: exactly two — `@tanstack/react-query`, `react-router-dom`.**

---

## 2. Backend additions

### 2.1 Migration — `backend/db/migrations/versions/0002_audit_human_agent.py`
- `upgrade()`: `ALTER TABLE audit_log DROP CONSTRAINT audit_log_agent_check;` then
  re-add the CHECK with the **seven** values (six + `human`).
- `down_revision = "0001_initial_schema"`.
- `downgrade()`: re-add the six-value CHECK. **Documented hazard:** if any
  `human` rows exist, the downgrade's CHECK re-add fails — that is correct (the
  data would violate it); the downgrade docstring states this rather than silently
  deleting rows. Forward-only in practice.
- `backend/app/audit/event.py` — `AgentName` Literal gains `"human"` (additive).

### 2.2 Audit API — `backend/app/api/audit.py`
- `GET /api/audit?correlation_id=<uuid>` → `list[AuditEntryView]` (rows under the
  id in `audit_id` order). `AuditEntryView { audit_id, agent, step, created_at,
  payload, chain_hash }`. 404 if the correlation_id has no entries. Payload is the
  full JSONB (the viewer truncates client-side; pipelines produce ~12 small rows).
- `GET /api/audit/verify/{correlation_id}` → `ChainVerificationView { ok,
  rows_checked, first_break: {audit_id, kind, expected, actual} | null }` via the
  existing **global** `verify_chain` (D4). 404 if the correlation_id has no
  entries.

### 2.3 Human decision API — `backend/app/api/human.py`
- `POST /api/claims/{claim_id}/human-decision` body `HumanDecision { decision:
  Literal["approved","rejected"], decided_by: str (1–120, stripped), comment: str
  | None (≤1000) }` → returns the updated `ClaimRecord`.
- Guards: claim exists (404); claim status is `awaiting_human` (409 otherwise —
  idempotent: a second attempt on a now-terminal claim returns 409); body
  validation (422).
- Effect: writes an audit entry `agent="human"`, step `human_approval` /
  `human_rejection`, payload `{decision, decided_by, comment, decided_at}`, under
  the claim's **latest run correlation_id** (looked up via `RunsRepository`); then
  `ClaimsRepository.update_status` → `settled` (approved) / `aborted` (rejected).
  Both writes in one connection; the audit entry is the trusted record.
- **Flagged:** unauthenticated in the prototype (production gates on an Entra ID
  role). Documented, not built.

### 2.4 Agent test bench API — `backend/app/api/agents_test.py`
All under `/api/agents/test/{agent}`, optional `?variant=<name>`. Each builds the
agent (default or variant via the Phase 5 factory pieces) and calls its **probe**
method (D5) — no audit write; the APILogger entry from `provider.complete` is the
only side effect.

| Agent | `POST` path | Request | Response |
|---|---|---|---|
| Doc-Parser | `/api/agents/test/doc-parser` | `{narrative}` | `AgentTestResult[DocParserOutput]` |
| Validator | `/api/agents/test/validator` | `{narrative, claim_type}` | `…[ValidatorVerdict] + retrieved_chunks` |
| Adjuster | `/api/agents/test/adjuster` | `{doc_parser_output, validator_verdict}` | `…[AdjusterOutput]` |
| Guardrail | `/api/agents/test/guardrail` | `{adjuster_output, retrieved_chunks}` | `…[GuardrailOutput]` |

`AgentTestResult { output, model, latency_ms, prompt_tokens, completion_tokens }`.
Guards: body validation (422); unknown variant (404). The Validator/Adjuster/
Guardrail test inputs reuse the existing typed models (`DocParserOutput`,
`ValidatorVerdict`, `AdjusterOutput`, `RetrievedChunk`) so the request bodies are
already validated shapes.

> **CI note:** these endpoints make real LLM calls. Their happy-path tests are
> **gated** (`RUN_LLM_E2E_TESTS=1`); the *guard* tests (422/404) run in CI with no
> network (they fail validation before any provider call). This matches the
> existing gated-test posture and avoids requiring keys in CI.

### 2.5 Prompt-display endpoint — in `agents_test.py`
- `GET /api/agents/{agent}/prompt?variant=<name>` → `AgentPromptView { agent,
  variant, system, user }` via `PromptLoader.raw` (D6). 404 unknown agent /
  variant.

### 2.6 Mounting + lifespan
- Mount the four routers in `backend/app/api/__init__.py`. No lifespan change
  beyond what Phase 5 added (the variant registry is already on `app.state`); the
  agent-test endpoints reuse it.

### Settings additions
**None.** The test bench reuses the variant registry and LLM Gateway. (Confirms
the prompt's expectation.)

---

## 3. Frontend structure

### 3.1 Dependencies + bootstrap
- Add `@tanstack/react-query`, `react-router-dom` to `frontend/package.json`.
- `main.tsx`: wrap `<App/>` in `<QueryClientProvider>` + `<BrowserRouter>`.
- `App.tsx`: the SPA shell — top nav bar (Claims / Audit / Agents) + `<Routes>`.

### 3.2 Design system — `frontend/src/styles/tokens.ts` (single source)
- **Colour tokens** (concrete hex): `primary #2563eb`, `success #16a34a`,
  `warning #d97706`, `danger #dc2626`, neutrals `#0f172a / #475569 / #94a3b8 /
  #e2e8f0 / #f8fafc`.
- **Status → badge colour** map (the seven lifecycle values): `received` neutral;
  `extracted / coverage_verified / estimated / guardrail_checked` a blue
  progression; `settled` success-green; `awaiting_human` warning-amber; `aborted`
  danger-red. Run statuses (`running` blue-pulse) included.
- **Typography scale**: `xs / sm / base / lg / xl / 2xl` named in `tokens.ts`.
- **Spacing**: standard Tailwind scale. **Layout**: top nav + max-w content;
  tuned for 1440×900 (no phone polish).

### 3.3 Component tree
```
App (nav + Routes)
├─ ui/                Button, Badge, StatusBadge, Card, Modal, Spinner, JsonBlock
├─ pages/
│  ├─ ClaimsPage          (/)            ClaimForm + ClaimList
│  ├─ ClaimDetailPage     (/claims/:id)  metadata + StatusTimeline + RunsList + live ProgressStrip
│  ├─ RunDetailPage       (/claims/:id/runs/:cid)  PipelineViz (agent cards)
│  ├─ ComparePage         (/claims/:id/compare/:a/:b)  DiffTable (deep-linked)
│  ├─ AuditPage           (/audit)       AuditTable + VerifyChainButton
│  └─ AgentsPage          (/agents)      four AgentTestPanel cards
├─ components/
│  ├─ AgentCard           collapsed summary + expand → PromptPanel + ResponsePanel
│  ├─ HumanReviewPanel    evidence + Approve/Reject form (on ClaimDetailPage when awaiting_human)
│  ├─ StatusTimeline, RunsList, ClaimForm, ClaimList, AgentTestPanel
└─ hooks/                useClaims, useClaim, useClaimRuns, useRun, useRunStream,
                         useAuditEntries, useVerifyChain, useAgentPrompt + mutations
```

### 3.4 Server state (TanStack Query)
- Query keys: `['claims']`, `['claim', id]`, `['claim', id, 'runs']`,
  `['run', cid]`, `['audit', cid]`, `['agentPrompt', agent, variant]`.
- staleTime: claims 5 min; in-flight run 0; `refetchOnWindowFocus: false`.
- Mutations (submit, run, replay, human-decision, agent-test) invalidate the
  relevant keys.

### 3.5 SSE ↔ Query integration
`useRunStream` (rewired): on each `agent_completed` event it writes into the
Query cache (invalidates `['run', cid]` / `['audit', cid]`) so the agent timeline
and lazily-expanded panels update without a separate state path. Terminal events
invalidate `['claim', id]` and `['claim', id, 'runs']`.

### 3.6 Live pipeline visualisation (AgentCard)
- **Collapsed**: agent name, status icon (queued/running/done/escalated/failed),
  duration, the locked `agent_completed` summary fields.
- **Expanded (lazy, D8)**: `PromptPanel` (system+user from
  `GET /api/agents/{agent}/prompt`) + `ResponsePanel` (the agent's audit-step
  payload from `GET /api/audit?correlation_id=`). In-flight: "waiting" until the
  `agent_completed`/audit entry exists.

### 3.7 Human review panel
Shown on `ClaimDetailPage` when status is `awaiting_human`. Evidence from the
latest run: Validator cited chunks **with content** (from the `coverage_check`
audit payload — `cited_chunks` alone lacks text), Adjuster reasoning + settlement,
Guardrail flags. Approve/Reject → `POST …/human-decision`; optimistic status
update + invalidate on success.

---

## 4. Files created / modified

**Backend created:** `api/audit.py`, `api/human.py`, `api/agents_test.py`,
`db/migrations/versions/0002_audit_human_agent.py`. **Models:** small request/
response models colocated or in `api/_models.py` (decide at execution; lean to
colocated per-router).
**Backend modified:** `agents/{doc_parser,validator,adjuster,guardrail}.py`
(extract probe), `prompts/loader.py` (add `raw`), `audit/event.py` (+`human`),
`api/__init__.py` (mount), `pyproject.toml` (0.5.0→0.6.0).
**Backend tests:** `test_audit_api.py`, `test_human_decision_api.py`,
`test_agents_test_api.py`, `test_agent_probe.py`, `test_migration_0002.py`,
`test_prompt_loader.py` (+`raw`).

**Frontend created:** `styles/tokens.ts`; `components/ui/*`; `pages/*`;
`components/{AgentCard,HumanReviewPanel,StatusTimeline,RunsList,AgentTestPanel}`;
new hooks; their `.test.tsx`.
**Frontend modified:** `main.tsx`, `App.tsx` (+ test), `api/{client,types}.ts`
(new endpoints + types), existing components refactored onto Query, `package.json`.

---

## 5. Testing strategy (~30–40 backend, ~25–35 frontend)

- **Audit API** (~6): list happy + 404; verify happy (ok) + injected break
  (tamper a row → `first_break`) + 404.
- **Human decision API** (~7): approve→settled; reject→aborted; not-awaiting_human
  →409; idempotent second attempt→409; missing claim→404; body guards (blank
  `decided_by`, oversized comment)→422; audit entry written under `agent="human"`.
- **Agent test API** (~9): per-agent guard tests (422 malformed / 404 unknown
  variant) in CI; per-agent happy path **gated**; prompt endpoint happy + 404.
- **Agent probe** (~5): each agent's probe returns typed output without writing an
  audit row (assert `audit_log` empty after a probe) — mocked provider.
- **Migration 0002** (~3): upgrade makes `agent="human"` insertable; a `human`
  entry persists; downgrade behaviour documented + tested (re-add fails with rows
  present, succeeds when empty).
- **PromptLoader.raw** (~3): returns unformatted content (placeholders intact);
  path-traversal + missing-file guards.
- **Frontend** (~28): `ui/` primitives (badge colour per status) (~4); ClaimsPage
  list + form (~4); ClaimDetailPage timeline + runs (~3); AgentCard expand → prompt
  + response (mocked) (~6); AuditPage table + verify button pass/fail (~4); Human
  review panel form + submit + optimistic (~4); AgentsPage one panel per agent (~4);
  routing/nav + compare deep-link (~3).

Every guard has a triggering test asserting on message content. Frontend uses a
`renderWithProviders` (QueryClient retries-off + MemoryRouter) + mocked `fetch`.

---

## 6. New dependencies
`@tanstack/react-query`, `react-router-dom` (frontend). **No others** — no `msw`,
no UI library, no date/JSON-viewer lib. If any third dep surfaces during
execution I'll stop and flag.

---

## 7. Locked at end of Phase 6 (Phase 7 consumes)
1. The routing structure (§D2 table).
2. New endpoint paths/methods/status-code policy (audit list+verify, human
   decision, agent test, agent prompt).
3. `audit_log` agent CHECK +`human`; audit steps `human_approval` /
   `human_rejection`; `AgentName` Literal +`human`.
4. Design-system tokens (`tokens.ts`).
5. Agent-test request/response shapes.

**Flagged simplifications:** chain verify is whole-ledger (D4); test bench writes
no audit (deliberate); human endpoint unauthenticated (production gap); prompt
endpoint exposes prompt sources over HTTP (already public in git).

---

## 8. Optional enhancements (labelled; not built)
Carried forward: retry/`tenacity`; pricing table; real PII redactor; prompt golden
fixtures; per-agent timeout; SSE heartbeat; consolidate superseded
`EscalationSettings`; `claim_status_history`; TanStack-not-yet… (now adopted).
New: auth on human decision (Entra ID); audit pagination (>50 rows); dark mode;
prompt-diff in the comparison view.

---

## 9. Execution order
1. `pyproject.toml` 0.5.0→0.6.0.
2. Migration 0002 + `AgentName` +`human` + migration tests.
3. `PromptLoader.raw` + tests.
4. Agent probe extraction (four agents) + probe tests (existing agent tests must
   stay green).
5. Backend endpoints: audit, human, agents_test (+ prompt) + mount + tests.
6. Backend full green (ruff/mypy/pytest).
7. Frontend deps + bootstrap (QueryClient + Router) + design tokens + `ui/`.
8. Pages + components + hooks (onto Query) + SSE-cache rewire.
9. Frontend tests; tsc + eslint + vitest green.
10. Build-log, report, CLAUDE.md, single commit, push.

---

**Verdict requested.** Please review — especially **D4** (chain verify is
whole-ledger; the `/{correlation_id}` path runs a global verification with the
correlation_id as context), **D5** (the additive per-agent `probe` extraction so
the test bench writes no audit), **D6** (`PromptLoader.raw` + prompt endpoint),
and **D9** (mocked fetch, no `msw`). On approval I'll record the `## Approval`
footer and proceed to Step 3.

---

## Approval

**Approval message:** "Approved as written. Two small notes for the report (not changes): (1) Make the "Verify chain" UI copy explicit that it verifies the whole ledger, not just this run, so the chain-verify semantics are reviewer-evident. (2) Call out in the report and Phase 7 documentation that the human review panel depends on /api/audit?correlation_id= to assemble evidence — cited_chunks alone carries IDs without text. Then append the ## Approval footer and proceed to Step 3."

**Approval notes to honour (no plan changes):**
- **Note 1 — implementation + report.** The "Verify chain" UI copy states explicitly that it verifies the **whole audit ledger**, not just the current run (reinforcing D4's global semantics). Carried into the audit-viewer copy and the report.
- **Note 2 — report + Phase 7 docs.** The report and the Phase 7 documentation call out that the human-review panel assembles its evidence from `GET /api/audit?correlation_id=` because `ValidatorVerdict.cited_chunks` carries chunk IDs without the chunk text — the clause content lives only in the validator's `coverage_check` audit payload.

All decisions (D1–D9) approved as written.

---

**Approved by:** Dermot Copps
**Approved at:** 2026-06-14T21:16:53Z
