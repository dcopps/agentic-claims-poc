# Prompt 32 — The Audit page and the record viewer

## Why this prompt exists

The audit trail is the system's central claim: every decision can be explained from the record alone. The Audit page is where a visitor goes to see that record, and it is the one page on the claim's path that still shows what the database stores. Dermot read it on the Azure frontend on 10 and 13 November and found:

- The page asks for a "Correlation id". A visitor does not know the term; every other page now says *run*.
- Nothing on the page says which claim the run belongs to. A run id alone tells a visitor nothing.
- Opened from the menu, the page is an empty box asking for an id, with no way to find one.
- Each row shows a time of day with no date, the agent and step as stored (`doc_parser`, `doc_extract`, `pipeline_awaiting_human`), and twelve characters of a hash with no explanation.
- Opening a row shows the stored record as one dark block of raw JSON. Long values (the instructions sent to the model, the Adjuster's reasoning) do not wrap and run off the right edge of the page. This is the backlog's oldest open UI item.
- Dermot asked on 13 November whether the JSON could be shown formatted in a popup, as a JSON formatter website would show it. Records are never to be pasted into an outside website; the page must do it itself. A mock-up was agreed that day; its design is Part 2 below.

This prompt fixes the Audit page and builds the record viewer. It is the fifth small iteration of the UI phase the backlog calls Phase 8.7. The Agents and Integrations pages follow as their own prompts. Do not start those here, and do not put the viewer on any other page yet: it is built to be reused, and the run page's cards and the Agents page take it up in later prompts.

Presentation first. If the plan finds that something below needs a change to an API response, say so, state exactly what, and ask; do not add an endpoint or a field without the acknowledgement.

## Part 1 — The page

- **Words.** "Correlation id" becomes "Run id" everywhere a visitor reads it. The address may keep its `correlation_id` parameter so that existing links work.
- **Which claim.** Once a run is loaded, the page names it as the run page does: the claimant as a link to the claim page, the claim type, the amount, the claim number; then the kind of run, when it started, and its outcome in the run page's words (including *Approved* / *Rejected* after a person's decision), with a link to the run page.
- **Finding a run.** A visitor who opens *Audit* from the menu should not face an empty box. Say in the plan what the existing endpoints allow: a list of recent runs with the claimant and claim number to pick from is the aim. The box accepts a full run id and, if it can be done, the short eight-character id the other pages show. If either needs a backend change, state it and ask.
- **The rows.** One row per record, in order:
  - the date and time, with seconds, in the reader's locale;
  - who wrote it, in words (Doc-Parser, Validator, Adjuster, Guardrail, Orchestrator, a person);
  - what happened, as a sentence in the run page's words where one exists ("Covered (92% confident)", "Recommends $82,500 (85% confident)", "Rejected by Dermot Copps"), drafted in the plan for every step the trail can hold, including the abort, the escalation decision with its fired rules, and the demo-fixture Adjuster;
  - the record's number in the ledger and the short hash, with one ⓘ on the column heading explaining in plain words what the hash is and why it matters.
- **Verify chain.** The button and its result in sentences: what was checked, how many records, that it covers the whole ledger and not only this run, and, on a break, which record and what kind of break in words.
- **States.** An unknown id, a run with no records, a failed load: each in plain words. The waking notice stays.

## Part 2 — The record viewer

Pressing a row opens the record in a dialog over the page. The agreed design:

- **A header line in plain words**: who wrote the record, what it is, when, and its number in the ledger.
- **Two views**, chosen by tabs:
  - *Record* — the stored record as a tree: keys and values coloured by kind, each object and list collapsible, the top level open and deep levels closed to begin with, long text wrapped inside the dialog and never wider than it. A long text value can be opened in full.
  - *Instructions sent* — only for a record that holds a model call: the system instructions and the message the model received, as readable text with their line breaks, under two plain headings. A record with no model call (the Orchestrator's rows, a person's decision, the demo-fixture Adjuster) does not show the tab, and the demo-fixture record says in a sentence that no model was called.
- **Copy record** copies the record exactly as stored, so that what a visitor pastes elsewhere is the true record and not the page's rendering of it.
- **A dialog that behaves**: closes on Escape, on its close button and on a click outside; the keyboard stays inside it while it is open and returns to the row on closing; the page behind does not scroll; it fits a laptop screen and scrolls inside itself.
- **No outside library and no outside website.** Built from the project's own components.
- **Reusable.** One component that takes a record and its header line, with nothing in it specific to the Audit page.

The old in-row dark block is removed from this page. Other pages that use `JsonBlock` are unchanged in this prompt.

## The Guide and the links in

Update any sentence in the Guide that describes the Audit page, with its tests. Check every link that opens the Audit page (*View audit log* on the run page, *Audit log* on the claim page's run lines) still lands on the run it names.

## Plan first

Produce `docs/prompts/32-audit-page-plan.md` covering:

1. Every step the audit trail can hold, from the code and from real rows on Azure (read-only): a settled run, a run sent to a person on the ceiling rule, the Guardrail-failure scenario with the demo fixture, an aborted run, a run a person approved, a run a person rejected. For each, the sentence the row will show.
2. What the existing endpoints allow for naming the claim, listing recent runs and accepting a short id; anything that needs a backend change, stated in full as an interface-stability acknowledgement, with a recommendation.
3. The record viewer: its parts, how the tree decides what starts open, how long text is handled, how *Instructions sent* finds the model call in each agent's record, and the keyboard behaviour.
4. Every sentence, label, heading and tooltip, drafted for approval.
5. Files touched; tests added or changed in the existing style, including the dialog's keyboard behaviour, *Copy record* giving the stored form, and a record with no model call; a mutation proof for one of them.
6. The version, and why.
7. Deployed verification with Dermot present, on the Azure frontend, on runs named by claimant and claim number: Harborline `CLM-2026-7E98B025` (run `f23ea4dc`, settled 15 November); Northwood `CLM-2026-5855FB8E` (run `2bd08a61`, rejected by Dermot 15 November); Northwood `CLM-2026-2FFB0434` (run `67bdf225`, approved 14 November); Coral Bay `CLM-2026-167527A2` (run `e9566e92`, the demo fixture); Background Claimant 01 `CLM-2026-1001` (run `b3e7dc6c`, aborted at the Adjuster). Also, on a new Northwood claim run live, the fix of 15 November: *Why it went to a person* appears when the run finishes, without a reload.
8. Anything in the record that contradicts this prompt.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`, including the commit-protocol rule: a gating check is never piped through `head`, `tail` or `grep`.
- No change to the agents, the audit chain, any audit payload or any SSE event. No new dependency.
- Use and extend the existing copy modules and the run page's sentences; no new wording inline in components, and no second wording for something the run page already says.
- Voice: plain and direct, British English, no superlatives, no scare quotes; "the system", not "the prototype".
- Name the claim wherever a run is named.
- Azure is running and stays running; the repository's About link points at it.

## Close-out

Report; build-log entry *Prompt 32*; build-story entry 32 with TL;DR and Technologies; signposts; the regeneration script; the backlog's Audit-page items marked done; a decision-register entry for any halt, deviation, incident or gate decision; `CLAUDE.md` status and any interface record, with *What's next* reading the run page's cards and the Agents page taking up the record viewer, then the Integrations page; commit and push.

## Archive

Pre-saved at `docs/prompts/32-audit-page.md`; plan and report alongside.
