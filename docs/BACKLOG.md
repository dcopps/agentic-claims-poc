# Backlog

This file is the authoritative list of pending and future work on the agentic-claims-poc. Completed work lives in [`docs/build-log.md`](build-log.md); the current session's state is in the *Current Status* section of [`CLAUDE.md`](../CLAUDE.md). This file captures everything else — surveyed but not-yet-actioned items, queued future phases, and open questions.

Ordered by priority: pending verifications first, then the next architectural phase, then future work, then working notes.

---

## Pending verifications (carried over from previous phases)

### Deployed verification of Phase 8.4 (audit-write transaction fix)

Deploy `0.8.5.1` to Render and confirm the audit-write fix survives end-to-end in production. Steps:

1. `curl https://agentic-claims-poc-backend.onrender.com/health` — expect `{"status":"ok","version":"0.8.5.1"}`. If it reports an earlier version, Render has not redeployed; check the dashboard.
2. Re-run the threshold-escalation scenario from the deployed frontend. Click *Process* on the seeded Northwood row (or a re-seeded equivalent if the deployed DB has drifted).
3. Confirm all four agent expand panels show filled prompts and JSON responses with **no** "Audit entry not found" red banners and **no** yellow "pre-dates the audit-prompt-capture change" fallback banners.
4. Open the audit log for the run's correlation_id. Confirm **seven** entries: `pipeline_started`, `doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`, `escalation_decision`, `pipeline_awaiting_human`. Confirm the *Verify chain (whole ledger)* badge reports the chain verified.

This closes the last item carried over from Phase 8.4. Cheap; only blocked by triggering a Render deploy.

---

## Next architectural phase — Phase 8.6: Demo UI polish

The demo is showable as of `0.8.5.1`. Phase 8.6 exists to lift it from *showable* to *portfolio-quality* — the interviewer-visible surface should not leak internal enum values, raw decimals, or unlabelled inputs.

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

### Routes still un-surveyed

The Phase 6 SPA has six routes. Only *Claims* has been swept. Five remain:

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
- Version bump: `0.8.5.1 → 0.9.0` (minor bump appropriate for a polish pass that touches every route).

---

## Future work (queued, not next)

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
