> *Plain-language summary of this phase: see [the build story](README.md#entry-30), entry 30.*

# Prompt 30 — The claim page and the human review panel

## Why this prompt exists

The claim page sits between the Claims list and the run page, and it is the one screen on that path still showing what the database stores. On 10 and 11 November Dermot read it on the Azure frontend and found:

- the claim's type as `smoke_damage`, its amount as `29925.00`, its status as `coverage_verified`;
- each run listed as "default · aborted · 0aca331d": the link is the variant's stored name, which tells a visitor nothing, and there is no time, so three runs of one claim cannot be told apart;
- no way to tell which run is the latest, and nothing saying what the tick boxes are for.

The Claims page (Prompt 28) and the run page (Prompt 29) now speak in plain words; this page sits between them and contradicts both. The human review panel on the same page is where the escalation story ends, and it has never been reviewed for polish: it shows the recommended settlement as a raw number and the Guardrail's verdict as "passed" or "flagged".

This prompt fixes the claim page and the review panel. It is the third small iteration of the UI phase the backlog calls Phase 8.7. The rules for when a claim may be run again (Part 3 of Prompt 29, deferred) follow as Prompt 31; the Audit page and the Agents and Integrations pages after that. Do not start those here.

Presentation only: no change to the backend, the agents, the audit chain, or any HTTP or SSE shape. If something below cannot be shown without a change to an API response, say so in the plan and leave it out; do not add an endpoint or a field in this prompt.

## Part 1 — The claim's details

- Type, amount and status through the labels and formatting modules written for the Claims page (`copy/labels.ts`, `copy/format.ts`): "Smoke damage", "$29,925", "Coverage checked".
- Add what the page omits and the record holds: policy number, loss date, reported date, and when the claim was submitted, with dates in the reader's locale.
- The description under a visible "Description" label, matching the form.
- Values that are words or dates in the ordinary text face; the monospace face only for identifiers (claim number, policy number).
- A status the pipeline left part-way (`extracted`, `coverage_verified`, `estimated`, `guardrail_checked`) means the latest run stopped before finishing. Say so in one line beside the status, in plain words, linking to that run: for example "The latest run stopped at the Adjuster." Take it from the run list and the latest run's audit rows the page already loads; if those do not hold enough, say what is missing.

## Part 2 — The runs

- Each run on one line, newest first as now, with the **start time as the link** (date and time in the reader's locale), then the kind of run in words (`variantLabel`: "Standard run", "Strict Validator run"), the outcome in plain words through `statusLabel`, and the short id in small monospace.
- Mark the most recent run "latest".
- Where the page can say more about the outcome without a new request per run, do: "Settled at $82,500", "Aborted at the Adjuster". State in the plan what the run summaries and the already-loaded audit rows allow; do not fetch every run's audit trail to build the list.
- A link on each line straight to that run's audit log.
- **Comparing runs.** One line above the list says what the tick boxes are for ("Tick two runs to compare them side by side"), shown only when the claim has two or more runs. The *Compare selected* button is always visible when there are two or more runs, disabled until exactly two are ticked, with the reason in its tooltip.
- A claim with no runs says so and tells the visitor what to do: go back to the Claims list and press *Process*, with a link.
- A link back to the Claims list at the top of the page.

## Part 3 — The human review panel

Survey the panel as it renders for the two escalated scenarios on Azure (Northwood, over the ceiling; Coral Bay, Guardrail failure and over the ceiling) and list what you find in the plan. Expected at least:

- The recommended settlement as currency with its confidence as a percentage, the same form the run page uses.
- **Why the claim is here**: the fired escalation rules in plain words, using the run page's `ruleLine`, as the first thing the reviewer reads.
- The Guardrail's finding in the run page's words, not "passed" / "flagged".
- The Adjuster's reasoning readable as prose.
- The retrieved passages as they are now (linked, with the cited ones marked).
- The form: visible labels for the reviewer's name and the comment, and what each button will do stated beside it ("Approve settles the claim at the recommended figure", "Reject closes the claim without settlement"; check these against what the backend does and correct them).
- **After a decision**, the claim page shows who decided, what, when, and their comment, read from the audit trail's `human_approval` / `human_rejection` row. Today the panel simply disappears once the claim is no longer awaiting a person; a visitor who opens the claim later cannot see that a person decided it. Show it as a short "Decision" card in the panel's place.

## The Guide

Update any sentence in the Guide's "Try it" and "Reading a run page" sections that describes this page (opening a claim, ticking two runs, *Compare selected*, the review panel), with its tests.

## Plan first

Produce `docs/prompts/30-claim-page-plan.md` covering:

1. What the claim record, the run summaries and the latest run's audit rows hold for: a claim never run; a settled claim with three runs; an aborted claim; a claim awaiting a person; a claim a person has approved; a claim a person has rejected. From real rows on Azure, read-only. Therefore exactly what each part of the page can show without an API change, and anything asked for above that it cannot.
2. The survey of the human review panel, with screenshots or the rendered text.
3. Every sentence and label the page can show, drafted for approval.
4. Files touched; tests added or changed in the existing style, including the decided-claim card and the disabled *Compare selected* state; a mutation proof for one of them.
5. The version; a point release is expected.
6. Deployed verification with Dermot present, on the Azure frontend: Background Claimant 04 (aborted run `0aca331d`), the Harborline claim with three runs of 10 November, Northwood awaiting a person, and one claim approved in the panel during the session and then reopened to show the Decision card.
7. Anything in the record that contradicts this prompt.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`, including the commit-protocol rule: a gating check is never piped through `head`, `tail` or `grep`.
- No backend change, no new dependency, no change to any stored value or any HTTP or SSE shape.
- Use and extend the existing copy modules; no new wording inline in components.
- Voice: plain and direct, British English, no superlatives, no scare quotes.
- Azure is running and stays running; the repository's About link points at it.
- The deployed verification approves one claim. Choose a scenario claim created for the purpose in that session, not one of the runs the decision register or the build log names.

## Close-out

Report; build-log entry *Prompt 30*; build-story entry 30 with TL;DR and Technologies; signposts; the regeneration script; the backlog's claim-page items marked done; a decision-register entry for any halt, deviation or incident; `CLAUDE.md` status, with *What's next* reading Prompt 31 (when a claim may be run again), then the Audit page; commit and push.

## Archive

Pre-saved at `docs/prompts/30-claim-page.md`; plan and report alongside.
