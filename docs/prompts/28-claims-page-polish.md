> *Plain-language summary of this phase: see [the build story](README.md#entry-28), entry 28.*

# Prompt 28 — Claims page polish

## Why this prompt exists

The repository's About link sends a first-time visitor to the Claims page. What they see there is internal: amounts as `850000.00`, claim types and statuses as the database stores them (`water_damage`, `awaiting_human`), a form whose fields lose their only label as soon as they are filled, no date on any row, and a second action whose name ("Re-process with v2") says nothing about what it does. Dermot met several of these on his own walkthrough on 4 November, including two date fields he could not tell apart.

This prompt fixes the Claims page and only the Claims page. It is the first of several small iterations that together make up the UI phase the backlog calls Phase 8.7; the run page, the claim page and human review panel, the Audit page, and the Agents and Integrations pages each follow as their own prompt. Do not start those here.

Presentation only: no change to the backend, the agents, the audit chain, the database, or any HTTP or SSE shape. Values sent to and stored by the API stay exactly as they are; only what the page shows changes.

## What changes

### 1. Amounts

Show monetary amounts as currency: `$850,000`, with cents only when they are not zero. One formatting helper, used wherever the Claims page shows an amount. The form's amount field keeps accepting a plain number.

### 2. Claim types and statuses in plain words

A small mapping module in the frontend's `copy/` folder turns stored values into labels, with the stored value never altered:

- Claim types: `water_damage` → "Water damage", `storm_complex` → "Storm (complex)", and so on for every type the form offers and every type the seed generator can produce. An unmapped value is shown in a readable fallback form (underscores to spaces, first letter capitalised), never hidden and never an error.
- Statuses: `received` → "Received", `extracted` → "Summarised", `coverage_verified` → "Coverage checked", `estimated` → "Settlement estimated", `guardrail_checked` → "Guardrail checked", `settled` → "Settled", `awaiting_human` → "Awaiting human review", `aborted` → "Aborted". Propose better words in the plan where these are wrong for what the status means; the backlog notes that `coverage_verified` is set even when the verdict is *not covered*, so "Coverage checked" is chosen to be true either way.

Keep the status badge's colours. The form's claim-type dropdown shows the labels and submits the stored values.

The mapping is used by the Claims page in this prompt. Write it so the later iterations can use the same module on the other pages; do not change those pages now.

### 3. Form labels

Every field in the claim form gets a visible label above it that stays when the field is filled: Claimant name, Policy number, Loss date, Reported date, Jurisdiction, Reported amount (USD), Claim type, Description. The labels are real `<label>` elements tied to their inputs, replacing the `aria-label`-only arrangement, so the existing tests that find fields by label keep working or are updated to the visible label.

The three scenario buttons above the form keep their labels exactly; the Guide's "Try it" section and a test depend on them.

### 4. A date on every row, newest first

Add a *Submitted* column showing when the claim was created (`created_at`, already in the API response), as a date and time in the reader's locale, in a short form such as "4 Nov 2026, 11:08". Confirm the list's order in the plan: it should be newest first; if the API already returns that order, say so and change nothing.

### 5. The second action

"Re-process with v2" runs the claim again under the `v2_strict_validator` variant, which gives the Validator a stricter instruction, so the two runs can be compared. Rename the button so it says that; recommended: "Re-run with strict Validator". When it is disabled (the claim has no finished run yet), a visitor should be able to tell why: say so in its tooltip or beside it.

The Guide's "Try it" section names this button. Update the Guide's text and its tests in the same change, and say in the plan every place the old label appears.

### 6. The information icons

Three small icons sit beside *Submit Claim*, *Process* and the second action, each with a tooltip that says what the production equivalent would be (an Azure Service Bus event, Durable Functions, a pipeline event). Check that each tooltip appears on hover and on keyboard focus. Then rewrite the three texts in plain words so that each says first what the button does here and then, in one clause, what would trigger it in production. Draft them in the plan for approval.

## Plan first

Produce `docs/prompts/28-claims-page-polish-plan.md` covering:

1. The label tables for claim types and statuses, complete, with any wording you would change and why.
2. The drafted tooltip texts and the drafted disabled-state wording.
3. Every file touched, and every place the old button label and the raw status or type strings appear in the frontend, its tests and the Guide.
4. The list order as the API returns it today.
5. Tests added or changed, in the existing style, including one that an unmapped claim type falls back readably and one that the form still submits stored values, not labels.
6. The version: a point release is expected; say which.
7. Confirmation that nothing outside the frontend changes, and anything in the record that contradicts this prompt.

Also commit, with the prompt and plan, the uncommitted edit to `docs/BACKLOG.md` made on 10 November (the addition under *Five of the six seeded background claims abort at the Adjuster*); it is Dermot's decision of that day and needs no change.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`: plan first, text in the copy modules, tests in the existing style, British English, no client name anywhere.
- Voice: plain and direct; no superlatives, no scare quotes.
- No new dependency. No backend change. No change to any stored value, HTTP or SSE shape.
- Azure is running and is to stay running: the repository's About link points at it. Do not run `azure-stop.sh`.
- Deployed verification with Dermot present: the Claims page read on the Azure frontend after the push deploys it; one scenario submitted and processed to confirm the form still works.

## Close-out

Report; build-log entry *Prompt 28*; build-story entry 28 with TL;DR and Technologies; signposts on this file, the plan and the report; the regeneration script; in `docs/BACKLOG.md`, mark the Claims-page items under *Phase 8.7* as done and leave the rest; a decision-register entry for any halt or deviation; `CLAUDE.md` status; commit and push.

## Archive

Pre-saved at `docs/prompts/28-claims-page-polish.md`; plan and report alongside.
