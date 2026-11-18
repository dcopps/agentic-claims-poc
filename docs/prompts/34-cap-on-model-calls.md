# Prompt 34 — A cap on model calls

## Why this prompt exists

The site is public and has no sign-in. Every *Process*, every *Strict re-run*, every run on the Agents test bench and every `run_scenario` call causes paid calls to the model provider, and nothing in the system limits how many a visitor can cause. Prompt 33's assessment rates this *Not addressed* and names it the first fix, because it is the only finding that costs money while it stands.

On 18 November 2026 Dermot set a $20 monthly spend limit on the model provider's console, with an email notice at $10. That is the outer backstop and it is blunt: when it is reached, every model call fails until the limit is raised or the month turns. This prompt adds the two inner layers, so that the backstop is never the thing that stops an abuser.

This is the first of the security fixes. The assessment (`docs/security-assessment.md`) stays on its local branch and is not pushed until this fix, the prevention work and the two escalation rules are all deployed (Prompt 33, decision D4 as changed on 18 November). The prevention work comes next and its plan is reviewed by Dermot before anything is built; the two rules follow. Do not start any of them here.

## What to build

### 1. A limit per caller

A caller may start only so many model-calling actions in a period. With no sign-in, the caller is the network address the request came from. State in the plan how that address is obtained correctly behind each deployment's front door (Azure Container Apps ingress, Render's proxy), which headers are trusted and why, and what a caller could forge.

A network address is personal data. Do not store it as received. Propose how the count is kept without keeping the address: a keyed or salted hash that changes daily is the expected shape. Say what is stored, for how long, and how it is removed.

### 2. A daily ceiling across everyone

A total number of model-calling actions per day across all callers. When it is reached, further actions are refused until the next day.

### 3. What counts

Everything that causes a model call, counted where the call is caused and nowhere twice:

- `POST /api/pipeline/run/{claim_id}` and `POST /api/pipeline/replay/{claim_id}`;
- the Agents test bench endpoints;
- the MCP `run_scenario` tool;
- any other route the plan's survey finds.

A run that sends no call to a model (the demonstration fixture's Adjuster step still sits inside a run that calls the other agents; a run refused before it starts) is handled explicitly: say what each counts as. Reading pages, the audit trail, the policy and `verify_chain` are never limited.

### 4. The refusal

A plain refusal, the same sentence wherever it is met:

- from the API, HTTP 429 with a `Retry-After` header and a `detail` a person can read, for example "Today's limit for this demonstration has been reached. Please try again tomorrow." and "You have started several runs in a short time. Please wait a few minutes and try again.";
- from `run_scenario`, an error in the tool's `code: message` style, recorded in `mcp_tool_calls` like the other refusals;
- in the frontend, the sentence shown where the visitor pressed the button: the Claims page, the run page's banner and the Agents test bench. No raw error text.

A refused action writes no claim, no run and no audit row. The refusal comes before any model call, and before the checks that would start a run.

### 5. Where the counts live

The backend scales to zero when idle and may run more than one replica, so a count held in memory is lost on every restart and is wrong across replicas. Keep the counts in the database, updated atomically so that two requests arriving together cannot both pass a limit of one. A new table and a migration are expected; say so in the plan as an interface-stability event, and say why the audit trail or `mcp_tool_calls` cannot serve (the test bench writes neither).

### 6. Settings

Both limits, the period, and an on/off switch are settings, in `settings.py` and `settings.yaml.template`, overridable by environment variable in the usual way, with defaults that are safe when nothing is set. On Azure the values go through the Bicep parameters like the others; on Render through the dashboard, recorded in the report. Propose the numbers from the measured cost of a run (Prompt 33 measured 223 calls at under one US dollar) so that the daily ceiling, held for a whole month, stays under the $20 provider limit.

### 7. When the counter cannot be read

Decide and justify what happens when the count cannot be read or written (the database is slow or down). The project's standard is to fail closed and say why; if you propose otherwise, give the reason.

### 8. The owner's demonstration

A daily ceiling means a stranger could use it up on a day Dermot needs the site. Propose how he runs his own demonstration regardless: raising the setting for the day is the simplest; a route for a caller who holds the MCP token is another. Give the options and recommend one. Nothing that adds a secret to the frontend.

## Plan first

Produce `docs/prompts/34-cap-on-model-calls-plan.md` covering:

1. Every route that causes a model call, from the code, and where each is counted.
2. How the caller's address is obtained on Azure and on Render, what is trusted, and what is stored.
3. The table, the migration, the atomic update, and the clean-up of old rows.
4. The settings, their defaults and the proposed numbers with the arithmetic.
5. The refusal in full: status, header, sentences, the tool error, and the frontend's handling on each page, with every sentence drafted for approval.
6. The interface-stability acknowledgement: the new 429 on each endpoint, the new tool error, the new table, the new settings.
7. Failure behaviour (section 7 above) and the owner's route (section 8).
8. Files touched; tests added in the existing style, including two requests racing a limit of one, the limit holding across a simulated restart, each counted route, each uncounted route staying open, and the refusal writing nothing; a mutation proof for the per-caller limit and one for the daily ceiling.
9. The version, and why.
10. Deployed verification with Dermot present on the Azure frontend, designed so that it costs cents and does not leave the site refusing runs afterwards: say how the limits are exercised (a temporarily low setting, or the per-caller limit met on the Agents test bench) and how they are restored.
11. How this work on `main` sits beside the unpushed branch `prompt-33-security-assessment`: which branch each commit goes on, how the build-story entries 33 and 34 and the regenerated table stay consistent while 33's entry is unpublished, and what is rebased when the assessment is finally pushed. Nothing on `main` may quote the assessment's findings or attack results beyond what this prompt says.
12. Anything in the record that contradicts this prompt.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`, including the commit-protocol rule: a gating check is never piped through `head`, `tail` or `grep`.
- No change to the agents, the audit chain, any audit payload or any SSE event. No new dependency unless the plan shows the existing stack cannot do it and Dermot agrees.
- No network address, and nothing that can be turned back into one, in the database, the logs, the audit trail or the repository.
- Nothing written to a deployed database except through the migration and the application itself.
- The local `.env` points `DATABASE_URL` at a deployed database. Every local command names its database explicitly; say in the plan how.
- Voice for every sentence a visitor reads: plain and direct, British English, no superlatives, no scare quotes; "the system", not "the prototype".
- Azure is running and stays running.

## Close-out

Report; build-log entry *Prompt 34*; build-story entry 34 with TL;DR and Technologies; signposts; the regeneration script; a decision-register entry for the gate decisions and any halt or deviation; the new interface records under *Locked interface extensions*; `CLAUDE.md` status, with *What's next* reading the prevention prompt (plan to be reviewed by Dermot before anything is built), then the two escalation rules, then publication of the assessment; commit and push. The assessment's own section on this finding is updated on its local branch to say *found 18 November, fixed* with the date, and is not pushed.

## Archive

Pre-saved at `docs/prompts/34-cap-on-model-calls.md`; plan and report alongside.
