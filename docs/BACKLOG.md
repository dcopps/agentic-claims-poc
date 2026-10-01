# Backlog

This file is the authoritative list of pending and future work on the agentic-claims-poc. Completed work lives in [`docs/build-log.md`](build-log.md); the current session's state is in the *Current Status* section of [`CLAUDE.md`](../CLAUDE.md). This file captures everything else — surveyed but not-yet-actioned items, queued future phases, and open questions.

Ordered by priority: pending verifications first, then unscheduled findings, then the next architectural phase, then future work, then working notes.

---

## Pending verifications (carried over from previous phases)

*None outstanding.* The Phase 8.6 deployed verification — which also discharged the Phase 8.4 / 8.5.2 seven-entry check carried since June — passed on the `0.8.6.1` build on 21 September 2026. See the *Deployed verification outcome* amendment to the Phase 8.6 entry in [`build-log.md`](build-log.md).

---

## Findings from the 21 September 2026 verification (not yet scheduled)

None was caused by Phase 8.6 or 8.6.1, and none affects the three scripted scenarios. The first two are demo-visible.

### Pipeline has no path for Validator `covered = false`

**The orchestrator should short-circuit to human review with a coverage-not-established reason instead of running the Adjuster.**

Found in run `74513bca-2fc7-497e-9fff-b574d1d6c210` (Background Claimant 03, `v2_strict_validator` replay). The Validator returned `covered: false` (0.35); the orchestrator ran the Adjuster anyway; Haiku reasoned correctly — *"coverage has been denied, no settlement payment is warranted"* — and returned `recommended_settlement = 0.00`; `AdjusterOutput` requires `> 0`, so the run **aborted** instead of reaching a human. On the default run of the same claim (`683cc79a-…`) the pipeline reached `awaiting_human` only because the model happened to propose $45,000 despite the denial — the outcome currently depends on whether the Adjuster is *wrong* in a schema-compatible way.

Scope notes for whoever picks this up:
- A denial is a decision a human must see, not an error: it belongs in `awaiting_human` with a fired rule (a new hard rule such as `coverage_not_established` in `escalation/policy.yaml`), not in `aborted`.
- **Status naming.** The aborted claim was left at `coverage_verified` although the verdict was *not covered* — the status asserts the opposite of the audit row. Decide whether the status means "the coverage check ran" (rename it) or "coverage was confirmed" (do not set it on a denial).
- **Interface-stability event:** a run that skips the Adjuster and Guardrail writes fewer than seven audit entries, a new fired-rule name appears in `escalation_decision`, and the agent panels need an "agent not run" state. Needs explicit acknowledgement in its plan.
- Do **not** fix this by relaxing `AdjusterOutput` to accept `0.00` — that converts a visible abort into a silent $0 settlement recommendation.

### Five of the six seeded background claims abort at the Adjuster

Found in run `765f1ad2-0871-41eb-bbab-1e12a0bb17bd` (Background Claimant 01): `MarketDataTable.lookup: unknown claim_type 'sprinkler_leakage'`. `seed_claims.py` generates background claim types — `sprinkler_leakage`, `vandalism`, `smoke_damage`, `hail`, `windstorm` — that `market_data.yaml` does not list (supported: `fire`, `flood`, `storm_complex`, `theft`, `water_damage`, `wind`). Only Background Claimant 03 (`theft`) can complete. In a demo, pressing *Process* on most background claims aborts.

The abort itself is correct behaviour (no silent fallback to a guessed range). The fix is data: either add market ranges for the five types, or constrain the seed generator to supported types — and add a test asserting that every seeded `claim_type` resolves in `MarketDataTable`, so the two files cannot drift again. Natural ride-along for Phase 8.7.

### Retrieval misses *Named Perils Covered* for a theft narrative

Both Background Claimant 03 runs retrieved *Exclusions*, *Business Interruption* and *Duties After Loss* (similarity 0.52–0.55) and never *Named Perils Covered*, which is what drove `covered: false`. Similarities that low and that flat suggest the narrative's vocabulary ("forced entry", "display safes", "CCTV") is simply far from the policy's peril wording. Worth a look at `top_k` (currently 3), at whether *Named Perils Covered* should always be included for a coverage decision, or at query construction from `claim_type` as well as the narrative. Retrieval quality only — the embedding model is a one-way door and is not in question.

---

## Phase 9 — Azure deployment (in progress; 9.1 deployed and verified 1 October 2026)

Phase 9 deploys the prototype to Azure in three sub-phases (prompts 19–21): **9.1** foundation (Bicep, Flexible Server, Container Apps, Key Vault, managed identity — **complete**: deployed, bootstrapped and verified on 1 October 2026, see the Phase 9.1 entry in [`build-log.md`](build-log.md)), **9.2** frontend on Static Web Apps + OIDC deploy workflow + Application Insights, **9.3** Azure AI Foundry as a third LLM provider. Render / Vercel / Neon stay up throughout and remain canonical for demos until Azure has passed the three-scenario verification twice (one pass recorded so far).

### Phase 9 follow-ons (found while planning and deploying 9.1)

- **Entra authentication for Postgres.** Deferred from 9.1: the app connects with a static `DATABASE_URL`; Entra tokens expire hourly, so honouring them means a token-refreshing connection path in `backend/db/connection.py` plus `azure-identity`. Natural companion to 9.3, which brings `azure-identity` in for Foundry.
- **Hugging Face token for the image build — only if needed.** The `Dockerfile` downloads `bge-small-en-v1.5` anonymously inside `az acr build`; anonymous downloads are rate-limited per IP. If a build is ever refused, adding `HF_TOKEN` as a build secret is a flagged change, not a quiet fix.
- **what-if drift from `minReplicas`.** `scripts/azure-stop.sh` / `azure-start.sh` toggle `minReplicas` outside Bicep. Accepted for 9.1; a 9.2 option is to drive it through a parameter in the deploy workflow instead.
- **`azure-stop.sh`: wait for zero replicas before stopping Postgres (9.x).** Found on the first stop/start round trip (1 October 2026). `minReplicas = 0` only permits scale-to-zero; a replica that served recent traffic stays up for the 300 s cooldown, so it outlived the Postgres stop by about five minutes. It was idle and nothing failed, but a request arriving in that window reaches a live app with no database. The fix is a behaviour change, so it needs a plan: either poll `az containerapp replica list` until it is empty before stopping the server (bounded by a named timeout, aborting with a diagnostic if the replica never drains), or deactivate the revision to force the replica down at once (which `azure-start.sh` would then have to reverse). The script's header comment now describes the actual behaviour.
- **Retire Render / Neon?** Only after two full passes of the three-scenario verification on Azure. **One pass recorded** (1 October 2026, Phase 9.1). Until the second, two deployments.

## Next UI phase — Phase 8.7: Demo UI polish (queued after Phase 9)

The three scripted scenarios are showable again: the Phase 8.6 deployed verification passed on the `0.8.6.1` build (21 September 2026). Two findings from that run are demo-visible and sit naturally in this phase — see *Findings from the 21 September 2026 verification*. Phase 8.7 exists to lift the demo from *showable* to *portfolio-quality* — the interviewer-visible surface should not leak internal enum values, raw decimals, or unlabelled inputs, and must survive a page refresh.

### Deployment — highest priority in this phase (found 14 September 2026)

- **SPA deep links 404 on hard load.** There is no `vercel.json`, so Vercel's edge has no rewrite sending non-root paths to `index.html`. Every deep URL — `/audit`, `/agents`, `/claims/:id/runs/:cid`, `/audit?correlation_id=…` — returns Vercel's own 404 (`NOT_FOUND`, `dub1::…` request id) on a hard load or refresh. Only `/` works. Client-side navigation (clicking links inside the app) works because it never touches the edge, which is why every deep link used in rehearsals so far appeared to work. **A page refresh mid-demo, or sharing a run URL with an interviewer, 404s.** Latent since Phase 6. Fix: add `frontend/vercel.json` with `{"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]}` (standard Vite + React Router on Vercel). One file. Verify by hard-loading `/audit?correlation_id=<any>` after deploy. **Phase 9.2 resolves this for the Azure frontend** via Static Web Apps' `navigationFallback`; the `vercel.json` fix is still needed for as long as the Vercel deployment is the demo surface.

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
- Version bump: `0.8.6.1 → 0.9.0` (minor bump appropriate for a polish pass that touches every route).

---

## Future work (queued, not next)

### Guardrail rule-engine test corpus from more than one model

*Raised by Phase 8.6.1 — the lesson from the citation-regex false positive.*

The rule engine's tests are hand-written sentences in one model's idiom. That is precisely the blind spot a provider swap exposes: the `re.IGNORECASE` defect sat latent from Phase 3 to Phase 8.6 because Mistral never happened to put a citation keyword in front of a lowercase word, and Claude Haiku did so in its first deployed auto-approve run.

**Proposal.** Keep a small corpus of *real* Adjuster reasoning paragraphs — one file per model the prototype has run on (Mistral Large, Claude Haiku), pulled from `audit_log` `settlement_estimate` rows, which are already synthetic and anonymised — and run `GuardrailRuleEngine.scan` over every paragraph as a no-false-positive suite. Paragraphs known to contain a planted hallucination (the demo fixture) go in a matching must-flag corpus. Adding a provider then means adding a corpus file, and an overfit heuristic fails in CI rather than in a deployed demo run.

Phase 8.6.1 did this informally and by hand: all three deployed Haiku paragraphs were run through the old and new patterns before the fix was written. Three paragraphs from one model is not a corpus. **Not built.**

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

Suggested in the Phase 8.5.2 report by Claude Code; logged, not built. Considered again at the Phase 9.1 approval gate (1 October 2026) and kept here: Phase 9.1 forbids changes on Render, and the Azure side now documents the same four-variable contract in `infra/bicep/modules/containerapps.bicep`.

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
