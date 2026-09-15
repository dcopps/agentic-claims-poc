# Backlog

This file is the authoritative list of pending and future work on the agentic-claims-poc. Completed work lives in [`docs/build-log.md`](build-log.md); the current session's state is in the *Current Status* section of [`CLAUDE.md`](../CLAUDE.md). This file captures everything else — surveyed but not-yet-actioned items, queued future phases, and open questions.

Ordered by priority: pending verifications first, then the next architectural phase, then future work, then working notes.

---

## Pending verifications (carried over from previous phases)

### Deployed verification of Phase 8.6 (Validator + Adjuster on Claude Haiku) — discharges the Phase 8.4 / 8.5.2 check

Phase 8.6 moved the Validator and Adjuster defaults to Claude Haiku (the Mistral tier decision, option 3, chosen 14 September 2026). One verification sequence closes Phase 8.6 **and** the Phase 8.4 (audit-write fix) / Phase 8.5.2 (model pin) seven-entry check that could not run while Mistral refused every call. Full field list in [`docs/prompts/17-phase-8.6-validator-adjuster-on-claude-haiku-plan.md`](prompts/17-phase-8.6-validator-adjuster-on-claude-haiku-plan.md) §5 and §10.

0. Dermot confirms on Render: no `LLM__*` env vars (in particular no `LLM__VALIDATOR_PROVIDER` / `LLM__ADJUSTER_PROVIDER`); `MISTRAL_API_KEY` stays set so `v1_mistral` is reachable.
1. `/health` → `version = 0.8.6`.
2. Reset Neon: hostname gate (`.neon.tech`), then `uv run python -m backend.data.seed_claims --allow-truncate` → 9 claims at `received`, `audit_log` empty, `policy_chunks` (12) untouched. Do **not** re-run `index_policy`.
3. Process the three seeded scenario claims from the Claims page. Each: expected terminal status (`settled` / `awaiting_human` / `awaiting_human`) and fired rule (none / `settlement_over_ceiling` / `guardrail_failed`); four agent panels filled, no *Audit entry not found*; **seven** audit entries (the orchestrator always writes `escalation_decision` + a terminal step); chain verified; `coverage_check` and `settlement_estimate` `llm_call.provider = "anthropic"`, `requested_model` = `model` = `claude-haiku-4-5-20251001` (guardrail scenario: `settlement_estimate` has `demo_fixture: true` and no `prompt` / `requested_model`). **A wrong terminal state halts the phase — no prompt or token retuning.**
4. Mistral-variant proof on a non-scenario seeded claim: run it on `default`, then `POST /api/pipeline/replay/{claim_id}?variant=v1_mistral` (the *Re-process* button is hardcoded to `v2_strict_validator`). Expect `aborted` at the Validator, `403 tier_not_allowed`, `coverage_check.llm_call.provider = "mistral"`, `requested_model = "mistral-large-2512"`.
5. One live `v2_strict_validator` replay of the auto-approve claim, **after** the scenario table is recorded — evidences that the UI's *Re-process* works on the Haiku default.
6. Record in the Phase 8.6 build-log entry and report; clear *Demo status* in `CLAUDE.md`; remove this item.

**Attempted 15 September 2026 — halted at step 3.**
- Steps 1–2 passed. Threshold and guardrail scenarios landed correctly, with full audit evidence.
- **Auto-approve failed:** run `8bff04e2-…` ended `awaiting_human` / `guardrail_failed`. The cause is a rule-engine false positive: `_CITATION_CANDIDATE_RE` with `re.IGNORECASE` matched Haiku's ordinary prose "section with inventory…".
- Steps 4–5 were not run. The deployed DB is left as evidence; reset again before the re-run.
- **Blocked on:** *Guardrail citation-regex false positive* below.

### Guardrail citation-regex false positive — **blocks the Phase 8.6 verification**

`backend/app/agents/guardrail_rules.py:_CITATION_CANDIDATE_RE` is compiled with `re.IGNORECASE`, which also makes the name group's leading `[A-Z]` case-insensitive. Any of `endorsement|sub-limit|clause|provision|section|exclusion` followed by any word is therefore treated as a policy citation and checked against the retrieved chunks.

Found live in run `8bff04e2-6ff7-4e74-aa5c-003008f21185`. The Haiku Adjuster wrote "one floor section with inventory and drying as primary components" and the rule engine flagged `hallucinated_citation`, escalating the auto-approve scenario. Latent since Phase 3.

**Recommended fix (point release 8.6.1, decision pending with Dermot):**
- Make only the keyword group case-insensitive (`(?i:…)`) and drop the global flag, so a candidate name must start with a capital.
- Add tests:
  - the exact Haiku sentence produces no flag;
  - `"Section 4.2"`-style and `"endorsement Coastal Surge Rider"` citations still flag;
  - the guardrail demo fixture still escalates.
- Re-run the Phase 8.6 verification from a fresh reset.

Not a prompt change.

---

## Next architectural phase — Phase 8.7: Demo UI polish

The demo is expected to be showable again once the Phase 8.6 deployed verification passes (see *Pending verifications*). Phase 8.7 exists to lift the demo from *showable* to *portfolio-quality* — the interviewer-visible surface should not leak internal enum values, raw decimals, or unlabelled inputs, and must survive a page refresh.

### Deployment — highest priority in this phase (found 14 September 2026)

- **SPA deep links 404 on hard load.** There is no `vercel.json`, so Vercel's edge has no rewrite sending non-root paths to `index.html`. Every deep URL — `/audit`, `/agents`, `/claims/:id/runs/:cid`, `/audit?correlation_id=…` — returns Vercel's own 404 (`NOT_FOUND`, `dub1::…` request id) on a hard load or refresh. Only `/` works. Client-side navigation (clicking links inside the app) works because it never touches the edge, which is why every deep link used in rehearsals so far appeared to work. **A page refresh mid-demo, or sharing a run URL with an interviewer, 404s.** Latent since Phase 6. Fix: add `frontend/vercel.json` with `{"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]}` (standard Vite + React Router on Vercel). One file. Verify by hard-loading `/audit?correlation_id=<any>` after deploy.

### Claims page (surveyed 3 August 2026)

Six items surfaced during the sweep of the `/claims` route. All are frontend-only:

- **Amount column formatting.** Currently renders as `850000.00`. Should be `$850,000` (currency-formatted, no trailing decimals for whole-dollar values). Use `Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })` or equivalent. Applies to both the Claims list and any other view showing amounts.
- **Form field labels.** Currently placeholder-only; labels disappear as soon as the field is populated. An interviewer looking at a populated form sees no context for each field. Add persistent labels above each input (Claimant name, Policy number, Loss date, Reported date, Jurisdiction, Reported amount, Claim type, Narrative).
- **Claim type — raw enum values.** Both the form dropdown and the Claims list Type column show raw enums (`water_damage`, `storm_complex`, `sprinkler_leakage`). Should be human-readable ("Water damage", "Storm — complex", "Sprinkler leakage"). Consider a small mapping module rather than mutating the DB values.
- **Status badge — raw enum values.** Column shows `awaiting_human`, `received`, `settled`, `aborted`. Should be "Awaiting human review", "Received", "Settled", "Aborted". Keep the existing colour coding.
- **`Re-process with v2` interaction.** Currently reads like a text input. Interaction is unclear — is it a button? Does clicking it trigger a replay? Verify the intended UX; if it is a button, style it as one; if it is a trigger for a variant selector, make the affordance discoverable.
- **No timestamp column.** Claims list shows no submitted-at or loss-date. For an interviewer asking "when did this happen?", the answer requires clicking through. Add a *Submitted* or *Loss date* column.
- **(i) info-icon tooltips.** Icons appear next to *Submit Claim*, *Process*, and *Re-process with v2*. Verify tooltips are actually wired to a hover handler, and that the copy is useful (not just "click to submit"). If unwired or unhelpful, fix or remove.

### Audit page

- **JSON viewer overflows page width.** Expanding an audit-log entry shows the payload in a dark code block. Long string values — filled prompts, narrative text, multi-line user prompts — do not wrap; they extend horizontally past the right edge of the viewport, breaking the page layout and forcing horizontal scroll. Fix in the JSON viewer component: constrain container `max-width: 100%` with `overflow-x: auto` for internal scroll, or use `white-space: pre-wrap` / `word-break: break-word` for wrapping. Wrapping is more readable for prose-heavy fields like prompts and narratives.

### Run Detail page (partially observed 14 September 2026 — abort path only)

- **Agent card stuck at "running" after a pipeline abort.** When the Validator raised the Mistral 403, the run header correctly showed `aborted` and the `ErrorBanner` carried the exception — but the Validator card stayed at *"running"* with the Phase 8 progress bar animating (*"Retrieving policy clauses… ~9s"*), and Adjuster/Guardrail stayed `queued`. The two surfaces disagree: run says aborted, card says running. Phase 8's `ErrorBanner` design (D6) covered the run-level surface and left per-card state untouched. Fix: on `pipeline_aborted`, transition the aborting agent's card to a failed state (name the exception type) and the downstream cards to a skipped/cancelled state. Verify with any forced-abort path (the agent test bench, or a deliberately bad model id).
- **Pipeline abort leaves the claim in `extracted`.** The orchestrator sets `claims.status = 'extracted'` after `doc_extract` succeeds; when a later agent aborts, the claim stays there. Truthful (extraction did happen) but it is a visible intermediate state in the Claims list with no explanation, and it is distinct from `aborted` (Phase 6 — a *human* rejection, terminal). Decision needed: should a *system* abort return the claim to `received` so it can be re-processed cleanly, or should there be a distinct non-terminal `failed` status? Either way the Claims list needs to explain it. Note the `claims.status` CHECK is a locked interface — adding a value is an interface-stability event.

### Routes still un-surveyed

The Phase 6 SPA has six routes. Only *Claims* has been swept, and *Run Detail* only on its abort path. Five remain:

- **Run Detail** (`/claims/:id/runs/:correlationId`) — the four-agent live pipeline visualisation
- **Audit** (`/audit`) — the audit-log browser (has the known JSON-overflow item above; may have others)
- **Agents** (`/agents`) — the agent test bench
- **Human Review** (`/human-review` or similar) — the escalation approval/reject panel; critical for the demo's headline story
- Sixth route (need to confirm from Phase 6 report)

Each should be visited before Phase 8.7 lands, and any items found folded into the phase's scope. Human Review is the highest-priority of these because it is the visible surface for the escalation demo — if it is polish-deficient, it undermines the whole tamper-evident-audit + human-in-the-loop narrative.

### Phase 8.7 scoping notes

- Bundle **everything** in this section into one phase pass. Fixing three items now and three items later burns Claude Code's phase overhead twice.
- Include a *walk through all six routes and flag any additional polish items before the phase closes* step in the QA section. Any new items surface during rehearsal and are folded into the plan before code lands.
- Interface stability: none expected. All items are presentation-layer only. No JSON schema, HTTP shape, SSE event, or DB column changes.
- Version bump: `0.8.6 → 0.9.0` (minor bump appropriate for a polish pass that touches every route).

---

## Future work (queued, not next)

### Re-enable Mistral as default

*Replaces the resolved "Mistral tier decision" (option 3 chosen 14 September 2026, built in Phase 8.6; the decision and its reasoning live in the Phase 8.6 build-log entry).*

The locked production target is still Mistral Large for the Validator and Adjuster. Once a Mistral payment method exists (Mistral Large is not callable on the Free tier — alias or dated release), restoring the two-vendor default is configuration, not code:

- **Without a code change:** set `LLM__VALIDATOR_PROVIDER=mistral` and `LLM__ADJUSTER_PROVIDER=mistral` on Render (two env vars; Render restarts the service). The model ids come from the pinned `llm.mistral.validator_model` / `adjuster_model` defaults (`mistral-large-2512`) — no model env var needed. `MISTRAL_API_KEY` must be set.
- **As the committed default:** flip the two selector defaults in `backend/settings.py` and `settings.yaml.template` to `mistral`, and update the `v1_mistral` variant (it would then equal the default — retire it or invert it into a Haiku variant). Revert the Phase 8.6 prototype-default notes in `CLAUDE.md` *Models*, `README.md`, `docs/design-decisions.md` §3, `docs/dora-third-party-register.md`, `docs/architecture-stack-reference.md`, `diagrams/README.md` and `docs/walkthrough.md`.
- **Verify first:** replay one claim with `v1_mistral` and confirm the Validator completes (no 403) before flipping the default. Check the pin is still a current dated release; move it forward deliberately if not (never back to `-latest`).

Doc-Parser or Guardrail on Mistral is structurally possible via the same selectors but was never verified — out of scope for this item.

### Startup model-access probe

At application startup, call each provider's models-list endpoint and confirm every configured model identifier (`llm.anthropic.*_model`, `llm.mistral.*_model`) is accessible to the account. A missing model fails startup — or at minimum turns `/health` unhealthy — with a config error naming the model, the agent role that uses it, and the provider.

**Motivating incident.** On 14 September 2026 (run `26a9bf4e-44ce-49c9-bc99-aeaed33c9f8f`) the Validator aborted a production pipeline mid-run with `403 tier_not_allowed`: Mistral had re-pointed the `mistral-large-latest` alias at a paid-tier release. Nothing in the deployment had changed, so nothing surfaced the problem until a claim was already being processed. A startup probe would have reported it as a configuration error at deploy time, before any claim reached the pipeline. Phase 8.5.2 fixed the instance by pinning to `mistral-large-2512`; the probe is the long-term answer to the class, including the day the pin itself ages out (see *Re-enable Mistral as default*). The probe would check the model each agent's selector resolves to (`LLMSettings.model_for`), not every configured id.

**Design questions to settle when scoped:** fail startup vs degrade `/health` (a hard failure on Render means a crash loop rather than a visible error page); whether the probe's own API calls need audit or api-call logging; timeout and retry behaviour so a provider blip doesn't block a deploy; and whether variant-override models in `variants.yaml` are probed too.

Suggested during Phase 8.5.2 planning by Claude Code; logged, deliberately not built.

### Split the oversized audit-payload builders

`Validator._build_audit_payload` (~67 lines), `Adjuster._build_audit_payload` (~72) and `Guardrail._build_audit_payload` (~74) are over the 50-line hard limit in `CLAUDE.md`, and `Adjuster.evaluate` is ~63 including its docstring. All pre-date Phase 8.5.3, which deliberately added no lines to any of them (the `CapturedRequest` design was chosen partly for that reason).

**Change:** extract per-block helpers — `_input_block`, `_output_block`, `_error_block` — so each builder reads as a flat assembly of named parts and sits under 50 lines. The `error` block is **byte-identical across all four agents** (`{"type": type(error).__name__, "message": str(error)}` or `None`), so it belongs in `_shared.py` as `error_block(error)` rather than four private copies. Pure refactor: no payload key, value or ordering changes; the existing audit-payload tests are the regression net, and the canonical-JSON hash of a payload built before and after should be identical for the same inputs. A good small point release, or ride-along with any backend phase.

Suggested in the Phase 8.5.3 plan by Claude Code; logged, not built.

### Record `requested_model` in `ProbeMetadata` (agent test bench)

The agent test bench (`POST /agents/test`, Phase 6) returns `ProbeMetadata` — the *responding* `model`, latency and token counts — built from the provider response. On a probe failure there is no response, so the bench has the same blind spot the audit log had before Phase 8.5.3: it cannot say which model was asked for. The probe paths already hold the `CapturedRequest` (discarded as `_request` in `parse` / `assess` / `estimate` / `check`), so the value is one field away.

**Change:** add `requested_model: str` to `ProbeMetadata` and surface it in the bench's error and success responses. This is an **additive HTTP response-shape change** for `/agents/test`, so it needs its own interface-stability acknowledgement in the plan (and a frontend type update if the bench UI is to show it).

Suggested in the Phase 8.5.3 plan by Claude Code; logged, not built.

### Render environment-variable inventory in `render.yaml`

Risk 1 of the Phase 8.5.2 plan (*"is there an `LLM__MISTRAL__*` override on Render?"*) needed a dashboard visit to answer. Render's Blueprint format supports an `envVars` block where `sync: false` declares a variable's *name* without its value, so the inventory of what the deployed backend expects (`ANTHROPIC_API_KEY`, `CORS_ALLOWED_ORIGINS`, `DATABASE_URL`, `MISTRAL_API_KEY`, and any future `LLM__*` overrides) can live in the repo with no secrets. Turns the check into a file read and documents the deployment contract. Would also have shortened the July CORS diagnosis.

Suggested in the Phase 8.5.2 report by Claude Code; logged, not built.

### In-UI "How it works" info page

A new SPA route (`/about` or `/how-it-works`) inside the deployed demo that hosts the architectural narrative. Contents:

- Prose explanation of what the demo does and the four-agent architecture
- Embedded architecture diagrams (the four Mermaid `.mmd` files rendered inline, plus the stack-comparison diagram once one is finalised)
- Tiered model strategy explanation
- DORA Article 28 provider substitutability rationale
- Audit-as-trusted-record explanation
- Links to the GitHub repo, this demo URL, and CLAUDE.md for the curious

**Currently blocked on:** the stack-comparison diagram. Three iterations attempted (inline SVG, Claude Design, ChatGPT); none landed. Parked deliberately until the diagram deliverable is settled — no useful info page without the diagram to anchor it.

The natural home for the four existing Mermaid sequence diagrams (`diagrams/1-headline-agent-flow.mmd` through `diagrams/4-production-architecture.mmd`) once the page exists.

### Local `agentic_claims_dev` bootstrap

The local dev database (`agentic_claims_dev`) is empty — no tables, no `alembic_version` — because the app has been running against Neon rather than local dev. This is inconsistent with the two-database model documented in CLAUDE.md.

Bring the local dev DB to parity:

1. `DEV_DB_NAME=agentic_claims_dev ./scripts/setup-dev-db.sh` (probably already done historically)
2. `alembic upgrade head` against the dev DB
3. `python -m backend.data.index_policy` against the dev DB
4. `python -m backend.data.seed_claims --allow-truncate` against the dev DB

Low urgency. Only needed for offline development or a Neon outage during interview prep. Surfaced during Phase 8.5.1 diagnostics.

### Clone-and-run verification (former task #9)

Full clone-and-run validation of the repo on a fresh machine: `git clone`, `./scripts/setup-dev-db.sh`, `uv sync`, `.env` setup, `alembic upgrade head`, index the policy, seed the claims, `uv run pytest`, `uv run uvicorn`, exercise the three demo scenarios.

Explicitly deprioritised — treated as code-loss insurance. Only worth running if the repo is being handed to someone else or after a large refactor.

### Session-scoped `pg_constraint` snapshot fixture (Phase 8.5.1 follow-on)

Generalise the protection Phase 8.5.1 added for one specific test. Add a session-scoped pytest fixture that snapshots `pg_constraint` (and optionally other schema-DDL views) at session start, and asserts no diff at session teardown. Fails loud with a diagnostic naming which constraints appeared or disappeared unexpectedly.

Would catch the entire class of *"test performed DDL and did not clean up"* regressions, not just the specific instance Phase 8.5.1 fixed. Currently deferred because the codebase has exactly one test doing DDL and it now has a self-checking post-assertion; adding session-level machinery for a class with a single instance is over-engineering. Revisit when a second DDL-mutating test appears (the memory of Phase 8.5.1 will make it obvious to add the fixture then), or if CI ever runs against a persistent test DB (which would create additional exposure).

Suggested at close of Phase 8.5.1 by Claude Code; deliberately deferred by Dermot.

### Debugger walkthrough of the audit-write bug (former task #17)

Write a ~30-line standalone Python script that reproduces Phase 8.4's silent-rollback mechanism in isolation:

- Open a psycopg connection with `autocommit=False`
- Run a SELECT to open an implicit transaction
- Wrap an INSERT into `audit_log` in a `conn.transaction()` block (becomes a SAVEPOINT)
- Exit without `conn.commit()`
- A separate connection confirms the row is missing
- Flip `autocommit=True` and re-run; row persists

Step through with `pdb` or a VS Code debugger, watching `conn.info.transaction_status` (0 = IDLE, 2 = INTRANS).

Purely pedagogical. Dermot wanted to see the bug mechanism directly rather than trust the diagnosis end-to-end. Not blocking anything. Parked until everything urgent is done.

---

## Working notes and open questions

### Diagram strategy

The stack-comparison diagram cycled through three iterations (Claude's inline SVG, three passes on Claude Design, one pass on ChatGPT plus a revision prompt) and did not land. Parked deliberately. When it is revisited, worth asking the deeper question first: is *"two stacks side by side"* the right visual metaphor, or does the narrative work better as a flow diagram, an annotated single stack, a table, or plain prose?

The production architecture diagram (`diagrams/4-production-architecture.mmd`) is currently a Mermaid *sequence* diagram. Unusual for a production topology — traditionally that would be a structural / component diagram (boxes containing boxes, VNets containing App Services). Reconsider when the info page is scoped: sequence works for showing request flow, structural works for showing topology; both may be useful, in which case one may need to be added rather than replaced.

### Phase-numbering convention (informal, worth codifying)

Recent phases have used two patterns:

- **Point releases** for narrow hotfixes: Phase 8.5.1 (test-migration autocommit fix). Bumps the fourth version segment (`0.8.5 → 0.8.5.1`).
- **Sub-phases** for scoped follow-ons: Phases 8.2, 8.3, 8.4, 8.5 (each addressing a distinct issue discovered during rehearsal of the previous phase). Bumps the third version segment (`0.8.0 → 0.8.5`).
- **Minor phases** for larger passes: Phase 8 (demo polish fixes pack). Would bump the second segment for a substantial polish pass (`0.8.5.1 → 0.9.0`).

Rough rule of thumb: point-release for a single-file hotfix; sub-phase for a focused multi-file change; minor-phase for a scope that touches multiple routes or modules. Phase 8.6 (Validator + Adjuster default to Claude Haiku — a locked-decision change across settings, wiring, variants and docs) was numbered a *sub-phase* (`0.8.5.3 → 0.8.6`) rather than an 8.5.x point release, because it is a design change, not an incident fix. Phase 8.7 (UI polish) fits *minor phase* on this scale.

---

## How this file is maintained

- Updated by Claude (in Cowork or Claude Code) before every phase scope is drafted and after every phase report closes.
- Items move from *Pending verifications* → *Next architectural phase* → *Future work* as they age.
- Items move from this file into `docs/build-log.md` when completed. Once in build-log they do not return here; refer to build-log for what was done.
- Deprioritised items stay in *Future work* rather than being deleted, so the historical scope of considered work is preserved.
