# Prompt 31 — When a claim may be run again

## Why this prompt exists

Today the only check before a run is that no other run is active on the claim. *Process* can be pressed on the same claim as often as one likes, including on a claim a person has already approved or rejected. Dermot found this on 10 November. It was Part 3 of Prompt 29, deferred at that prompt's gate (register R-23) so that it could have its own plan, its own interface record and its own verification.

The design was written then and is the starting point now: `docs/prompts/29-run-page-plan.md` §4, with decisions D7 and D8 in §10. Read it first. Much has changed since it was written (Prompts 29 and 30 are built), so the plan for this prompt checks every part of that design against the code as it stands and says what still holds and what does not.

Unlike the last five prompts, this one changes the backend. It is one small iteration: the rules for running a claim again, and nothing else. The Audit page follows as its own prompt, then the Agents and Integrations pages. Do not start those here.

## What was agreed (Dermot, 10 November)

1. On the Claims page the primary button reads **Process** for a claim that has never been run and **Run again** once it has had a run.
2. Running a **settled** claim again asks for one confirmation in the page, with no browser dialog: "This claim has already settled. Run it again?" with *Run again* and *Cancel*.
3. A claim that **a person has approved or rejected** cannot be run again, by *Process*, by *Strict re-run*, through the MCP `run_scenario` tool, or by any other route. The buttons are disabled with the reason leading their tooltips, and the backend refuses the request.

## Part 1 — The backend refuses

As designed in Prompt 29's plan §4, unless the plan for this prompt finds a reason to differ:

- A human decision is detected from the audit trail's `human_approval` / `human_rejection` rows, not from the claim's status.
- `POST /api/pipeline/run/{claim_id}` and `POST /api/pipeline/replay/{claim_id}` answer 409 with a plain message naming the claim and saying whether a person approved or rejected it. The closed-claim check comes before the active-run check (D8).
- The MCP `run_scenario` tool, given such a claim, fails with `claim_closed` in its existing `code: message` style, and the call is recorded in `mcp_tool_calls` like any other failure. `docs/demo-mcp.md` is corrected where it speaks of running a scenario twice on one claim.
- Every endpoint that returns a claim gains `human_decision: 'approved' | 'rejected' | null`, filled from the audit rows in one grouped query (D7). The frontend needs it to disable the buttons without a request per row.

Survey every route by which a run can start (the two endpoints, the MCP tool, the Agents test bench if it can start one, any script) and list them in the plan with whether each is covered.

## Part 2 — The Claims page

- *Process* for status `received`; *Run again* otherwise.
- The settled confirmation, inline in the row's actions cell, sized so that the row does not jump and the table keeps its width (942 px, measured in Prompt 28 and again in Prompt 30).
- For a claim a person has decided, both buttons disabled, with the reason leading the tooltip: "Closed: a person approved this claim; it cannot be run again." / "Closed: a person rejected this claim; it cannot be run again."
- *Strict re-run* on a settled claim: say in the plan whether it also asks for the confirmation, and recommend.
- The Claims page component is 75 lines, over the project's 50-line limit (noted in Prompt 30's report). This prompt touches it, so split it here, with no change to what it renders beyond the items above.

## Part 3 — The other pages

- **The claim page.** A claim a person has decided says, in one line near the Decision card, that it is closed to further runs. The empty state for a claim never run ("No runs yet. Go back to the Claims list and press Process on this claim.") is unchanged. Check whether any sentence in `copy/claim.ts` now reads wrongly and list it.
- **The run page.** A 409 from either endpoint already reaches the run page's error banner. Confirm the banner reads well with the new message and that the visitor has a way back to the claim.
- **The Guide.** Update *Try it* and any other sentence that names the *Process* button or describes running a claim twice, with its tests.
- **Tooltips.** All new wording in the copy modules; none inline in components.

## Plan first

Produce `docs/prompts/31-when-a-claim-may-be-run-again-plan.md` covering:

1. Prompt 29's plan §4 checked line by line against the code as it stands: what holds, what has moved, what is no longer right.
2. Every route by which a run can start, and how each is refused for a decided claim.
3. The interface-stability acknowledgement, in full: the two 409 refusals, the additive `human_decision` field and every endpoint that carries it, the `claim_closed` tool error. No database change is expected; if one seems necessary, stop and say so.
4. Every sentence, label and tooltip the pages can show, drafted for approval, including the 409 message as a visitor reads it.
5. Files touched; tests added or changed in the existing style, backend and frontend; a mutation proof for the refusal and one for the disabled buttons.
6. The version, and why.
7. Deployed verification with Dermot present, on the Azure frontend:
   - the Northwood claim `CLM-2026-2FFB0434`, approved on 14 November: both buttons disabled with the reason; the claim page says it is closed;
   - a fresh scenario claim created in the session, sent to a person, **rejected** in the panel, then shown closed in the same way;
   - a direct request to the run endpoint for a decided claim, showing the 409 and its message;
   - `run_scenario` through the Claude connector on a decided claim, showing `claim_closed`, and the call appearing on the Integrations page's live feed;
   - a settled Harborline claim: *Run again*, the confirmation, *Cancel*, then *Run again* through to a new run;
   - a claim never run: the button still reads *Process* and runs it;
   - the one check still open from Prompt 29's plan §7 (step 4): *Process* on a background claim of an unsupported type, watched live to its abort.
8. Anything in the record that contradicts this prompt.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`, including the commit-protocol rule: a gating check is never piped through `head`, `tail` or `grep`.
- No change to the agents, the audit chain, any audit payload, any SSE event, or any existing HTTP shape other than the three changes acknowledged in the plan.
- No database migration and no new dependency.
- A human decision is final in this prompt: there is no way to reopen a decided claim, and none is to be added.
- The verification rejects one claim. Use a scenario claim created for the purpose in that session, not one the decision register or the build log names.
- Voice: plain and direct, British English, no superlatives, no scare quotes; "the system", not "the prototype".
- Azure is running and stays running; the repository's About link points at it.

## Close-out

Report; build-log entry *Prompt 31*; build-story entry 31 with TL;DR and Technologies; signposts; the regeneration script; the backlog's *Process can be pressed repeatedly on the same claim* marked done, and Prompt 29's open step 4 marked done if it was watched; a decision-register entry for any halt, deviation, incident or gate decision; `CLAUDE.md` status and the three changes recorded under *Locked interface extensions*, with *What's next* reading the Audit page; commit and push.

## Archive

Pre-saved at `docs/prompts/31-when-a-claim-may-be-run-again.md`; plan and report alongside.
