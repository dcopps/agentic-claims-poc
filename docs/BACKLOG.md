# Backlog

This file is the authoritative list of pending and future work on the agentic-claims-poc. Completed work lives in [`docs/build-log.md`](build-log.md); the current session's state is in the *Current Status* section of [`CLAUDE.md`](../CLAUDE.md). This file captures everything else — surveyed but not-yet-actioned items, queued future phases, and open questions.

Ordered by priority: pending verifications first, then the next architectural phase, then future work, then working notes.

---

## Pending verifications (carried over from previous phases)

### Deployed verification of Phase 8.5.3 (`requested_model` audit key) — with DB reset

Narrower than the full seven-entry run below, and **expected to abort at the Validator** — the Mistral tier decision is still open. Its purpose is to prove from the audit row alone which model the runtime requests. Run as one operational sequence, after `0.8.5.3` is deployed:

1. `/health` → `0.8.5.3`.
2. **DB reset (Part B)** — pending. Hostname-only check that the resolved `DATABASE_URL` ends in `.neon.tech`; then `uv run python -m backend.data.seed_claims --allow-truncate`; confirm `SELECT COUNT(*) FROM claims` = 9 and the three scenario tags present with status `received`. `TRUNCATE … CASCADE` also clears `audit_log`, including runs `26a9bf4e-…` and `11f97ae8-…` cited in the Phase 8.5.2 build-log entry — a conscious choice; the build log keeps the finding. `policy_chunks` is untouched; do **not** re-run `index_policy`.
3. Process the seeded `threshold_escalation` claim; it aborts at the Validator (`403 tier_not_allowed`).
4. Audit log for that run: `coverage_check` `llm_call.requested_model = "mistral-large-2512"` (no `model` key); `doc_extract` `llm_call.requested_model` and `llm_call.model` both `claude-haiku-4-5-20251001`.
5. Record the outcome in the Phase 8.5.3 build-log entry and report, and replace the elimination argument in the Phase 8.5.2 entry with the definitive statement.

### Deployed verification of Phase 8.4 (audit-write transaction fix) and Phase 8.5.2 (Mistral model pin)

Deploy `0.8.5.2` to Render and confirm both the audit-write fix and the Mistral pin survive end-to-end in production. One run covers both. Steps:

0. Before or alongside the redeploy, Dermot confirms no `LLM__MISTRAL__*` environment variable is set on Render — one would outrank the pinned default and the pin would silently not take effect.
1. `curl https://agentic-claims-poc-backend.onrender.com/health` — expect `{"status":"ok","version":"0.8.5.2"}`. If it reports an earlier version, Render has not redeployed; check the dashboard.
2. Submit a **fresh** threshold-escalation claim from the deployed frontend using the form's *Threshold escalation ($850k fire)* template button, then *Process* it. Do not reuse the seeded Northwood row — it was already touched by the failed 14 September run (`26a9bf4e-44ce-49c9-bc99-aeaed33c9f8f`).
3. Confirm the Validator completes (no 403), the pipeline reaches `awaiting_human`, and all four agent expand panels show filled prompts and JSON responses with **no** "Audit entry not found" red banners and **no** yellow "pre-dates the audit-prompt-capture change" fallback banners.
4. Open the audit log for the run's correlation_id. Confirm **seven** entries: `pipeline_started`, `doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`, `escalation_decision`, `pipeline_awaiting_human`. Confirm the *Verify chain (whole ledger)* badge reports the chain verified.
5. Confirm **both** `coverage_check` and `settlement_estimate` read `llm_call.model = "mistral-large-2512"`. The threshold scenario calls the Adjuster live; the $1.4M guardrail scenario cannot prove the Adjuster pin because its Adjuster output is a demo fixture.

This closes the last item carried over from Phase 8.4 and the deployed half of Phase 8.5.2.

**Attempted 14 September 2026 — failed, now blocked.** Step 0 cleared (Render env has only `ANTHROPIC_API_KEY`, `CORS_ALLOWED_ORIGINS`, `DATABASE_URL`, `MISTRAL_API_KEY`). Step 1 cleared (`/health` = `0.8.5.2`). Step 2 failed: run `11f97ae8-7dc6-4b41-9b8e-16c85d4bd073` aborted at the Validator with the identical `403 tier_not_allowed`. By elimination (pinned default deployed, no `settings.yaml`, no CLI flags, no env override) the runtime was sending `mistral-large-2512`, so **2512 is gated on the Free tier too**. The Phase 8.5.2 premise — that the Limits page listing 2512 meant Free could call it — was wrong; see *Mistral tier decision* below for the corrected understanding. This verification is blocked until the Mistral tier decision (payment method vs Claude default) is made and deployed.

When re-run: before step 2, reset the deployed DB with `uv run python -m backend.data.seed_claims --allow-truncate` (against the Neon `DATABASE_URL` — safe; the Phase 8.5 guard is pytest-only). Today's failed submissions left four Northwood rows and several claims stuck in `extracted`.

---

## Next architectural phase — Phase 8.6: Demo UI polish

The demo is **not currently showable** — the Validator 403s on every scenario until the Mistral tier decision lands (see *Pending verifications*). Once that is resolved, Phase 8.6 exists to lift the demo from *showable* to *portfolio-quality* — the interviewer-visible surface should not leak internal enum values, raw decimals, or unlabelled inputs, and must survive a page refresh.

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

Each should be visited before Phase 8.6 lands, and any items found folded into the phase's scope. Human Review is the highest-priority of these because it is the visible surface for the escalation demo — if it is polish-deficient, it undermines the whole tamper-evident-audit + human-in-the-loop narrative.

### Phase 8.6 scoping notes

- Bundle **everything** in this section into one phase pass. Fixing three items now and three items later burns Claude Code's phase overhead twice.
- Include a *walk through all six routes and flag any additional polish items before the phase closes* step in the QA section. Any new items surface during rehearsal and are folded into the plan before code lands.
- Interface stability: none expected. All items are presentation-layer only. No JSON schema, HTTP shape, SSE event, or DB column changes.
- Version bump: `0.8.5.2 → 0.9.0` (minor bump appropriate for a polish pass that touches every route).

---

## Future work (queued, not next)

### Mistral tier decision — **now immediate, blocks the demo**

*Originally logged at close of Phase 8.5.2 as "Mistral tier upgrade path", a future decision for when the 2512 pin aged out. Superseded the same day.*

**Corrected understanding (14 September 2026).** The Phase 8.5.2 pin to `mistral-large-2512` also returns `403 tier_not_allowed` in production (run `11f97ae8-7dc6-4b41-9b8e-16c85d4bd073`). The plan's premise was that the Mistral admin *Limits* page (`admin.mistral.ai/limits`) listing 2512 with a 250k TPM rate limit meant the Free tier could call it. **It does not.** The Limits page is a rate-limit table for models the organisation is configured for; it is not a catalogue of what the current tier can invoke. Mistral has withdrawn Mistral Large from the Free tier entirely — alias and dated releases alike. Do not re-run the pin-to-another-version experiment against that page.

The pin itself stays (dated release, not alias — the pin-by-policy comment in `settings.py` remains correct). What changes is the tier.

**Options, decision pending with Dermot:**

- **(1) Add a payment method on Mistral.** Keep the 2512 pin (paid tiers do not gate it). Restores the exact locked architecture — *"Mistral Large (Validator, Adjuster)"* — and keeps the two-vendor DORA Article 28 story live in the demo. Pay-as-you-go Mistral Large is roughly €2–6 per million tokens; a demo run is a few thousand tokens, so a few euros of credit covers months of rehearsals. Recommended.
- **(3) Default Validator + Adjuster to Claude Haiku** via the LLM Gateway. Zero cost; the `v2_haiku_validator` variant from Phase 5 already does this for the Validator. But all four agents on one vendor hollows out `design-decisions.md` §3, and the *"Re-process with v2"* substitution demo cannot run either without a working Mistral. The substitution *capability* stays in the code; the *live proof* leaves the demo. If chosen, CLAUDE.md's locked *Models* decision needs an explicit note, and the demo script should say it out loud rather than hope nobody asks.
- ~~(2) Pin to a smaller Free-tier Mistral model~~ — another guess against the same misleading Limits page, not "Mistral Large", and Small may not reliably return the structured coverage JSON. Not recommended.

**Whichever is chosen:** append the deployed-verification outcome (failed — 2512 gated) and this corrected understanding to the Phase 8.5.2 build-log entry and report.

### Startup model-access probe

At application startup, call each provider's models-list endpoint and confirm every configured model identifier (`llm.anthropic.*_model`, `llm.mistral.*_model`) is accessible to the account. A missing model fails startup — or at minimum turns `/health` unhealthy — with a config error naming the model, the agent role that uses it, and the provider.

**Motivating incident.** On 14 September 2026 (run `26a9bf4e-44ce-49c9-bc99-aeaed33c9f8f`) the Validator aborted a production pipeline mid-run with `403 tier_not_allowed`: Mistral had re-pointed the `mistral-large-latest` alias at a paid-tier release. Nothing in the deployment had changed, so nothing surfaced the problem until a claim was already being processed. A startup probe would have reported it as a configuration error at deploy time, before any claim reached the pipeline. Phase 8.5.2 fixed the instance by pinning to `mistral-large-2512`; the probe is the long-term answer to the class, including the day the pin itself ages out (see *Mistral tier decision*).

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

Rough rule of thumb: point-release for a single-file hotfix; sub-phase for a focused multi-file change; minor-phase for a scope that touches multiple routes or modules. Phase 8.6 (UI polish) fits *minor phase* on this scale.

---

## How this file is maintained

- Updated by Claude (in Cowork or Claude Code) before every phase scope is drafted and after every phase report closes.
- Items move from *Pending verifications* → *Next architectural phase* → *Future work* as they age.
- Items move from this file into `docs/build-log.md` when completed. Once in build-log they do not return here; refer to build-log for what was done.
- Deprioritised items stay in *Future work* rather than being deleted, so the historical scope of considered work is preserved.
