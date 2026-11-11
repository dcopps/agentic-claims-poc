> *Plain-language summary of this phase: see [the build story](README.md#entry-29), entry 29.*

# Prompt 29 — The run page

## Why this prompt exists

The run page is where the system shows its work, and on 10 November Dermot found it failing at exactly that. Opened while a run is happening it behaves; opened afterwards it does not:

- A **finished run** opened from the claim page shows its outcome in the header (*settled*), then "Awaiting pipeline_started…" and all four agent cards as *queued*. Seen on run `f368c2c5-3ac1-4fa2-a37d-4097a8fc7b0a`.
- An **aborted run** opened afterwards shows *aborted* in the header, every card *queued*, and no reason at all, because the red error banner exists only while the run is live. Seen on run `0aca331d-a148-4a70-93c8-5cd37f725995`.
- A run that **aborts while being watched** leaves the failing agent's card at *running* with its progress bar moving, and the later agents *queued*, beneath a banner that says the run aborted. Seen on run `8c537109-58b4-4021-9957-b6189480c86e` (claim type `hail`), and first recorded in the backlog on 14 September.

The cards also show the agents' results as raw data (`{"covered":true}`, `{"recommended_settlement":"82500.00"}`), durations in milliseconds, and a refused objection's reason as its code (`quote_not_a_provision`).

Separately, *Process* can be pressed on the same claim as often as one likes, including on a claim a person has already approved or rejected.

This prompt fixes the run page and the *Process* rules. It is the second small iteration of the UI phase the backlog calls Phase 8.7; the Claims page was the first (Prompt 28). The claim page, the Audit page, and the Agents and Integrations pages follow as their own prompts. Do not start those here.

## Part 1 — A run reads the same live and afterwards

The page already loads the reconstructed run (`GET /api/runs/{correlation_id}`) and its audit entries; both come from the audit trail. The cards take their state only from the live event stream. Change the page so that the audit trail is the source of each card's state whenever it has the answer, and the live stream fills in only what the audit trail does not yet hold.

- **Finished run, any outcome:** each agent that wrote its audit row shows as complete, with its summary and duration taken from that row. "Awaiting pipeline_started…" is not shown for a run that has audit rows.
- **Aborted run:** the agent that failed shows *Failed* with the reason in plain words and the exception's own message beneath it; every later agent shows *Not run*. The reason comes from the audit trail (`pipeline_aborted`), so it is there whether the run is watched or opened a week later. State in the plan exactly what that row holds and whether it is enough; if the abort reason is not recorded in the audit trail today, say so and stop, because recording it would be an audit-payload change that needs its own acknowledgement.
- **Guardrail failure that sends the claim to a person:** shown as the outcome it is, not as an abort.
- **Watching a run live:** unchanged in behaviour, except that an abort now moves the failing card to *Failed* and the later cards to *Not run* at once.
- A run that does not exist still shows a plain "run not found".

## Part 2 — The cards in plain words

- **Summaries.** Replace the raw data on each card's top line with a sentence: Doc-Parser "Summarised the claim (Water damage)"; Validator "Covered" or "Not covered", with its confidence; Adjuster "Recommends $82,500", with its confidence; Guardrail "Passed" or "Failed: …" naming what it found. Draft the exact wording for every case in the plan, including the demo-fixture Adjuster, whose card should say its answer came from the fixed demonstration file. The raw request and response stay available when the card is opened, as now.
- **Durations** in seconds to one decimal place ("3.4 s").
- **Refused objections.** Keep the model's quoted words; replace the reason code with plain words: `no_quote` → "the model gave no quotation", `quote_not_in_reasoning` → "those words are not in the Adjuster's reasoning", `quote_not_a_provision` → "those words do not name a policy provision". The codes stay in the audit trail.
- **The header.** The outcome badge uses the plain-words status labels; "variant: default" becomes a sentence a visitor can read ("Standard run" / "Strict Validator run"), with the variant's stored name kept beside it in small type; the fired escalation rules, when there are any, are listed under the header in plain words with the observed value ("Settlement over the $250,000 ceiling: $820,000").

Use the labels and formatting modules written for the Claims page (`copy/labels.ts`, `copy/format.ts`); extend them where needed. All new text lives in the copy modules.

## Part 3 — When a claim may be run again

Today the only check is that no run is active on the claim. Agreed with Dermot on 10 November:

- On the Claims page the primary button reads **Process** for a claim that has never been run, and **Run again** once it has a finished run.
- Running a **settled** claim again asks for one confirmation in the page: "This claim has already settled. Run it again?"
- A claim that **a person has approved or rejected** cannot be run again, by *Process*, by *Strict re-run*, or by any other route. Both buttons are disabled with the reason in their tooltips, and the backend refuses the request.

The last point is a behaviour change in the API: `POST /api/pipeline/run/{claim_id}` and `POST /api/pipeline/replay/{claim_id}` gain a refusal (409, with a plain message) where there was none. That is an interface-stability event; acknowledge it in the plan, say how a human decision is detected (the audit trail's `human_approval` / `human_rejection` rows, or the claim's state, and why), say what happens to the MCP `run_scenario` tool when it is given such a claim, and add it to the record in `CLAUDE.md` at close-out. No database change is expected; if one seems necessary, stop and say so.

If the plan finds that Part 3 is better as its own prompt, say so and give the reason; Dermot prefers small iterations and will decide.

## The Guide

The Guide's "Try it" section names the buttons and describes the run page. Update its wording to match (the *Run again* label, "each card says what the agent concluded"), with its tests.

## Plan first

Produce `docs/prompts/29-run-page-plan.md` covering:

1. What `GET /api/runs/{correlation_id}` and the audit entries hold for a settled run, an escalated run, a Guardrail-failure run and an aborted run, taken from real rows, and therefore exactly what each card can show after the event.
2. The rule for combining the audit trail with the live stream, stated in two or three sentences, and the states a card can be in.
3. Every sentence the cards and the header can show, drafted for approval.
4. Part 3: the detection of a human decision, the refusal's shape and message, the tests, the effect on `run_scenario`, and the interface-stability acknowledgement.
5. Files touched; tests added or changed in the existing style, including: a finished run rendered with no live events; an aborted run rendered with no live events showing the failed agent and the reason; a live abort moving the cards; the refusal after a human decision, with a mutation proof.
6. The version, and why.
7. Deployed verification with Dermot present, on the Azure frontend: the three runs named at the top of this prompt opened and read; one scenario run live to a settlement; one background claim of an unsupported type run live to an abort; a claim approved in the human review panel and then shown to be closed to re-running.
8. Anything in the record that contradicts this prompt.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`, including the commit-protocol rule added on 10 November: a gating check is never piped through `head`, `tail` or `grep`.
- No change to the agents, the audit chain, any audit payload, or any existing HTTP or SSE shape, other than the refusal in Part 3.
- No new dependency.
- Voice: plain and direct, British English, no superlatives, no scare quotes; "the system", not "the prototype".
- Azure is running and stays running; the repository's About link points at it.

## Close-out

Report; build-log entry *Prompt 29*; build-story entry 29 with TL;DR and Technologies; signposts; the regeneration script; the backlog's run-page items marked done; a decision-register entry for any halt, deviation or incident; `CLAUDE.md` status and, for Part 3, the interface record; commit and push.

## Archive

Pre-saved at `docs/prompts/29-run-page.md`; plan and report alongside.
