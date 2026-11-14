# Prompt 31 — Plan: when a claim may be run again

**Prompt:** `31-when-a-claim-may-be-run-again.md`. **Scope:** the rules for running a claim again — the backend refuses a decided claim on every route, the Claims page says *Process* or *Run again* and asks once before re-running a settled claim, the other pages say when a claim is closed. One backend change, the first since Prompt 27. **Written:** 14 November 2026. **Status:** awaiting approval.

## 0. The design of 11 November, checked line by line against the code today

Prompt 29's plan §4 is the design; this section says what holds, what has moved and what is no longer right.

| §4 said | Today | Holds? |
|---|---|---|
| Detect a human decision from the audit rows (`agent = 'human'`, step `human_approval` / `human_rejection`), not from the claim's status, because `settled` is written by the pipeline and by approval alike | `api/human.py` is unchanged: one human row under the latest run, then `settled` or `aborted` on the claim. Nothing else writes those steps (`mcp/explain.py` only reads them, `_HUMAN_STEPS`). The frontend's `claimDerivation.deriveDecision` already reads the same row (Prompt 30) | **Holds.** The backend gains the same reading |
| `RunsRepository.human_decision(conn, claim_id)` — one claim, one query, on `audit_log_claim_id_idx` | The index exists (migration 0001). The Claims page needs the answer for fifty claims at once, so a per-claim query would be fifty queries | **Moved:** one grouped query over a list of claim ids (§1), the single-claim case a list of one. It lives in `AuditRepository`, not `RunsRepository`: it is a question about the trail, and the audit module imports nothing from `claims` or `runs`, so both can call it without a cycle |
| `require_open_claim(settings, claim_id)` in `api/pipeline.py`, 409 for `run` and `replay`, checked after the claim exists and before the active-run check | `run_pipeline` checks claim → variant → active; `replay_pipeline` checks claim → variant → prior terminal run → active. `execute_run` is public there for the MCP tool | **Holds.** The new check goes third in both, before the prior-run and active-run checks (D8) |
| Message: `claim {id} was approved by a person and is closed to further runs` / `… rejected …`; the client already shows `detail` in the run page's banner | `api/client.ts` surfaces `detail`; `ClaimsPage.trigger` writes a failed POST to `['runError', cid]`; `RunDetailPage` shows "Could not start the run: {detail}" | **Holds.** §4 below drafts the sentence; §3 of Part 3 checks the banner and the way back |
| `run_scenario`: `_prepare_scenario_claim` gains the check through a shared `ClaimClosedError` raised by a repository helper; `ToolError("claim_closed: …")` in the existing `code: message` style; recorded in `mcp_tool_calls` like other failures | `_prepare_scenario_claim` checks the tag then `is_run_active`; `instrument.run_logged` records a `ToolError` as `outcome: error` already (`not_found`, `run_in_flight`, `not_a_scripted_claim` go this way) | **Holds in effect, simplified:** no new exception class. The repository answers `approved` / `rejected` / `None`; one function in `api/pipeline.py` turns the answer into the sentence; the API raises it as 409, the tool as `ToolError("claim_closed: " + sentence)`. One sentence, two wrappers |
| `docs/demo-mcp.md`'s line about running a scenario twice on the same claim gains "unless a person has decided it" | Line 20 still reads "or run the scenario twice on the same claim with `run_scenario(name, claim_id)`" | **Holds.** Also the tool's own description ("Pass claim_id to re-run an existing claim …") gains the same clause; no test asserts that text |
| Claims page: *Process* for `received`, *Run again* otherwise; a settled claim asks once, inline in the actions cell, "This claim has already settled. Run it again?" with *Run again* and *Cancel*, no browser dialog | `ClaimsPage.tsx` (Prompt 28/30): one `Process` button and a `Strict re-run` button in a `whitespace-nowrap` cell, measured 942 px for the table on Azure | **Holds, with one sizing decision (D2):** the question is wider than the two buttons it would replace, so an in-cell swap would widen the column or wrap the row. §2 of Part 2 below |
| For a decided claim both buttons disabled, the reason leading the tooltip | The disabled-reason convention exists (`tooltips.disabledNoFinishedRun`, `disabledCompareNeedsTwo`) | **Holds** |
| The page needs to know a person decided: (a) `ClaimRecord` gains `human_decision`, filled by `list_claims` and `get` in one grouped query (recommended); (b) fifty extra requests | Nothing on the claim record or the run summary says so; the Claims page would have to fetch every claim's audit rows | **Holds: (a), D7 of that plan.** §1 names every endpoint that carries it, including the MCP listing, which §4 did not mention (D1) |
| Interface acknowledgement: the two 409s, the additive field, the tool error; no audit payload, SSE event, table or setting changes; no database change | Unchanged | **Holds**, written in full in §3 |
| Tests and mutation proof as listed; frontend: *Process* / *Run again*, the confirmation, the disabled buttons, the 409 in the banner | The test files exist with the fixtures the tests need (`_StubOrchestrator`, `insert_harborline_claim`, `seed_fixture_run`, `AuditWriter`) | **Holds**, §5 |
| Version `0.10.2` if Part 3 were built | Prompts 28–30 were point releases `0.10.1.x`, presentation only | **Holds:** `0.10.2`, §6 |

Three things §4 could not know: the frontend's `REPLAYABLE` set (`settled`, `awaiting_human`, `aborted`) now has an unreachable member, because a claim is `aborted` only by a rejection, which this prompt closes to re-runs (§2 of Part 2); the Claims page component is 75 lines and is split here (Part 2); and `claimDerivation.deriveDecision` on the frontend and the new backend reading must agree on "the last human row wins" — they do, and a claim has at most one such row because `api/human.py` refuses a second decision.

## 1. Every route by which a run can start

| Route | How a run starts | Covered for a decided claim by |
|---|---|---|
| `POST /api/pipeline/run/{claim_id}` | the Claims page's *Process*; `scripts/verify-demo-scenarios.py` (on a claim it has just created, so never decided); any direct call | the new 409, third check, before the active-run check |
| `POST /api/pipeline/replay/{claim_id}` | the Claims page's *Strict re-run*; any direct call | the same 409, third check, before the prior-run and active-run checks |
| MCP `run_scenario(name, claim_id)` | Claude's connector or any MCP client, on an existing scripted claim | `ToolError("claim_closed: …")` from `_prepare_scenario_claim`, after the tag check and before the in-flight check; recorded in `mcp_tool_calls` as an error like the other refusals, so it appears on the Integrations page's live feed |
| MCP `run_scenario(name)` without a claim id | inserts a fresh claim, which has no decision | nothing to refuse; unchanged |
| The Agents test bench (`/api/agents/...`, `api/agents_test.py`) | **cannot start a run:** it probes one agent's prompt → model → parse path and writes an API-logger record only; no audit row, no pipeline | not a route |
| The orchestrator called directly (`PipelineOrchestrator.run`) | tests and the two endpoints only; no HTTP surface | not a route; the check stays at the edge, in the API and the tool, as the active-run check does today |
| `POST /api/claims/{id}/human-decision` | not a run, but the other write on a decided claim | already refuses a second decision (409 "not awaiting human review"); unchanged, so a decision stays final |

**The reading, in one place.** `AuditRepository.human_decisions(conn, claim_ids: Sequence[UUID]) -> dict[UUID, HumanDecisionKind]`:

```sql
SELECT DISTINCT ON (claim_id) claim_id, step FROM audit_log
WHERE agent = 'human' AND step IN ('human_approval', 'human_rejection') AND claim_id = ANY(%s)
ORDER BY claim_id, created_at DESC, audit_id DESC
```

mapped to `approved` / `rejected`; claims with no row are absent and callers read `None`; an empty input returns `{}` without a query, as `count_runs_by_claim` does. One query for a page of fifty, the same query for one claim. `HumanDecisionKind = Literal["approved", "rejected"]` lives in `claims/models.py` beside `ClaimStatus`.

**Where the field is filled.** `ClaimsRepository.get` and `list_claims` call the function after their own SELECT and set `human_decision` on each record; `insert` sets `None` (a new claim has no row). So every `ClaimRecord` the backend hands out carries it: `POST /api/claims` (null), `GET /api/claims`, `GET /api/claims/{id}`, `POST /api/claims/{id}/human-decision` (the decision just written, read back from the row), and the MCP `get_claim` (`ClaimView.claim` is a `ClaimRecord`). The MCP `list_claims` returns its own `ClaimListItem`, not a `ClaimRecord`; D1 asks whether it carries the field too.

**The refusal.** In `api/pipeline.py`: `closed_claim_detail(claim_id, decision) -> str` (the sentence in §4) and `async def _require_open_claim(settings, claim_id)` (reads the one claim through the function above; 409 with the sentence when a decision exists). `run_pipeline`: claim → variant → **open** → active. `replay_pipeline`: claim → variant → **open** → prior terminal run → active. `mcp/tools._prepare_scenario_claim`: not found → tag → **open** (`ToolError("claim_closed: " + closed_claim_detail(...))`) → in flight. Order is D8: a closed claim is refused as closed whatever else is true of it.

## 2. Part 2 — the Claims page

- **The primary button** reads *Process* when `status === 'received'` and *Run again* otherwise. A claim whose status is mid-pipeline because a run is in flight also reads *Run again*, and pressing it meets the existing active-run 409 in the run page's banner, as *Process* does today; unchanged.
- **The settled confirmation (D2).** When *Run again* is pressed on a `settled` claim the row does not start a run; it shows "This claim has already settled. Run it again?" with *Run again* (primary, small) and *Cancel* (secondary, small). *Cancel* closes it; *Run again* closes it and triggers the run exactly as today. **Sizing:** the question is about 250 px at the table's small size, the two buttons another 150 px; the actions cell holds about 200 px today and the table is `w-full` at 942 px, so putting the question in the cell's flow would widen the column (the other columns would squeeze and the row could wrap) or add a line to the row. Recommended: the confirmation is rendered inside the cell but **anchored** (`relative` cell, `absolute right-0 top-full z-20`, white panel with a border and shadow, like the tooltip's box), so the row keeps its height and the table its width; it closes on *Cancel*, on *Run again*, and on Escape; the two buttons are ordinary buttons the keyboard reaches. Alternative: a second line inside the cell, which grows the row by one line while open. No browser dialog either way.
- **A decided claim** (`human_decision !== null`): both buttons disabled (`disabled` and `aria-disabled`), the reason leading each tooltip: "Closed: a person approved this claim; it cannot be run again. " / "Closed: a person rejected this claim; it cannot be run again. " followed by the button's own text. The label stays *Run again* (it has had a run); the tooltip says why it is off.
- **Strict re-run on a settled claim (D3).** Recommended: no confirmation. The button's label says it runs the claim again, it is only enabled once a run has finished, and its purpose is a second run to compare; the confirmation on *Run again* exists because that label alone does not tell a visitor the claim has already been handled. The alternative is one confirmation for both, with the same sentence.
- **`REPLAYABLE`.** `aborted` is removed from the set with a comment: a claim is stored `aborted` only by a rejection, and a rejected claim is now closed, so the member can never enable the button. The set otherwise stays (`settled`, `awaiting_human`); making it exact against the backend's "any finished run" rule would need the run summaries, which the list does not fetch.
- **The split.** `ClaimsPage.tsx` becomes: `ClaimsPage` (the two cards, under 30 lines), `useRunTrigger(claimId)` (the navigate-then-POST logic, as a hook, with its comment), `ClaimsTable` (the table and its header comment), `ClaimRow` (the cells), `RowActions` (the two buttons, their tooltips and the confirmation state), `ConfirmRerun` (the anchored question). Nothing rendered changes beyond the items above; the Prompt 28 and 30 tests pass unchanged except where they name the new label.
- **Words** in a new `copy/claims.ts` (`claimsCopy`): the two button labels (moved from inline, no change), *Run again*, the question, *Cancel*, the two existing messages ("Failed to load claims.", "No claims yet — submit one above.") moved in as they stand. Tooltips in `copy/tooltips.ts`.

## 3. Interface-stability acknowledgement

1. **`POST /api/pipeline/run/{claim_id}` and `POST /api/pipeline/replay/{claim_id}` gain a 409** where there was none: `{"detail": "claim <id> was approved by a person and is closed to further runs"}` (or `rejected`). Checked before the existing 409s (active run; nothing to replay), so a decided claim is always refused with this message. The 404s (unknown claim, unknown variant) stay first. No change to the 200 body, the SSE stream or any event.
2. **`ClaimRecord` gains `human_decision: "approved" | "rejected" | null`**, additive, every existing key unchanged; carried by `POST /api/claims` (always null), `GET /api/claims`, `GET /api/claims/{id}`, `POST /api/claims/{id}/human-decision`, and the MCP `get_claim` (`ClaimView.claim`). With D1, the MCP `list_claims` item (`ClaimListItem`) gains the same field. Rows written before this version need nothing: the value is computed from the audit rows on every read, never stored.
3. **MCP `run_scenario` gains the `claim_closed` error:** `claim_closed: claim <id> was approved by a person and is closed to further runs`, in the tool's `code: message` style; the call is recorded in `mcp_tool_calls` with `outcome: error` like the other refusals. The tool's description gains one clause. The nine-tool catalogue is unchanged.

No audit payload, no SSE event, no table, column or index, no setting, no dependency. **No database change:** the query runs on `audit_log_claim_id_idx`, which exists. If a migration were to prove necessary, the build stops and says so. Recorded under *Locked interface extensions* in `CLAUDE.md` at close-out.

## 4. Every sentence, label and tooltip

**Backend (one sentence, two wrappers).**
- 409 detail / `claim_closed` message: "claim 2ffb0434-bf3f-4019-ab76-69c0d289270a was approved by a person and is closed to further runs" · "… was rejected by a person and is closed to further runs". The claim is named by its id, as every other refusal from these endpoints names it.
- As a visitor reads it in the run page's banner: "Could not start the run: claim 2ffb0434-… was approved by a person and is closed to further runs". The header's first line names the claimant with the link back to the claim page (it comes from the address once the audit query has answered, Prompt 29), and the "Waiting for the run to begin…" hint is suppressed when a run error is present (`silent` is false), so the banner stands alone under the header. A test asserts both. The sentence is the backend's, so the banner's wording stays as it is; no frontend copy for it.

**Claims page (`copy/claims.ts`, `copy/tooltips.ts`).**
- Labels: *Process* (status `received`) · *Run again* (any other status) · *Strict re-run* (unchanged).
- The confirmation: "This claim has already settled. Run it again?" · *Run again* · *Cancel*.
- Tooltips, prefixed while disabled: "Closed: a person approved this claim; it cannot be run again. " · "Closed: a person rejected this claim; it cannot be run again. " — each followed by `tooltips.processClaim` or `tooltips.strictRerun` as today. `processClaim`'s text ("Runs the four agents on this claim now …") reads correctly under both *Process* and *Run again*; unchanged.

**Claim page (`copy/claim.ts`).**
- One line at the foot of the Decision card: "The claim is closed to further runs." (`claimCopy.closedToRuns`, test id `closed-to-runs`).
- Checked for sentences that now read wrongly: `noRuns` ("… press Process on this claim.") is right, a claim never run still shows *Process*; `approveDoes`, `rejectDoes` and `decisionRecorded` are true but silent on the closure — O1 below adds one sentence under the buttons rather than changing the approved three; `decisionInAudit`, `stoppedAt`, `runInProgress`, the run-line outcomes: unaffected.

**Guide (`copy/guide.ts`).** `tryMore[0]` ends "… the claim page then records who decided and when, and the claim is closed to further runs." (one sentence, as the test requires). `trySteps[2]` ("Press Process on its row …") is right for the new claim the steps describe; `tryMore[1]` (*Strict re-run*) unchanged. Nothing in *How it works* describes running a claim twice.

**MCP.** The `run_scenario` description: "Pass claim_id to re-run an existing claim that carries that scenario's tag instead of submitting a new one; a claim a person has approved or rejected is closed and refused." `docs/demo-mcp.md` line 20: "… or run the scenario twice on the same claim with `run_scenario(name, claim_id)`, unless a person has decided it."

**Optional (O1):** a fourth sentence under the review panel's buttons: "Either decision closes the claim to further runs." (`claimCopy.decisionCloses`). *Recommended: yes* — it is the one place a visitor is about to make the decision.

## 5. Files touched and tests

| File | Change |
|---|---|
| `backend/app/claims/models.py` | `HumanDecisionKind`; `ClaimRecord.human_decision: HumanDecisionKind \| None = None` (a default so every existing construction stands) |
| `backend/app/audit/repository.py` | `AuditRepository.human_decisions(conn, claim_ids)` — the grouped query above |
| `backend/app/claims/repository.py` | `get` and `list_claims` fill the field; `insert` sets `None`; `_row_to_record(row, decision)` |
| `backend/app/api/pipeline.py` | `closed_claim_detail`, `_require_open_claim`; the two endpoints call it third |
| `backend/app/mcp/tools.py` | `_prepare_scenario_claim` refuses a decided claim with `claim_closed`; description clause; with D1, `_read_claims` fills `ClaimListItem.human_decision` from the same grouped query |
| `backend/app/mcp/models.py` | with D1, `ClaimListItem.human_decision` |
| `docs/demo-mcp.md` | the clause |
| `pyproject.toml` | `0.10.2` |
| `frontend/src/api/types.ts` | `ClaimRecord.human_decision` |
| `frontend/src/copy/claims.ts` (new), `tooltips.ts`, `claim.ts`, `guide.ts` | §4 |
| `frontend/src/pages/ClaimsPage.tsx` | split as in Part 2; the label rule, the confirmation, the disabled state |
| `frontend/src/components/DecisionCard.tsx` | the closing line |
| `frontend/src/components/HumanReviewPanel.tsx` | O1's sentence |
| `frontend/src/test/runFixtures.ts`, `pages/ClaimsPage.test.tsx` | fixtures gain `human_decision: null` |

**Backend tests** (`test_api_pipeline.py`, `test_api_claims_runs.py`, `test_human_decision_api.py`, `test_audit_repository` or `test_runs_repository.py`, `test_mcp_tools.py`): `human_decisions` — none, approved, rejected, the later of two rows wins, two claims in one call, empty input makes no query; `run` 409 after an approval and after a rejection with the sentence asserted and the stub orchestrator never called; `replay` the same; **order (D8):** a decided claim that also has a run in flight is refused as closed, not as active; a decided claim with no active run is refused (the active check alone would have let it through); the field on list and get — null, approved, rejected — and on the human-decision response; `run_scenario` on a decided scripted claim → `claim_closed:` in the error text, the stub not run, the call recorded with `outcome = 'error'`; the Harborline scenario still runs; with D1, the listing item carries the field. **Mutation proof:** the `_require_open_claim` call removed from `run_pipeline` → the two run-refusal tests and the order test fail; restored, all pass. Expected: 527 → about 545.

**Frontend tests** (`ClaimsPage.test.tsx`, `DecisionCard` via `ClaimDetailPage.test.tsx`, `HumanReviewPanel.test.tsx`, `RunDetailPage.test.tsx`, `claim.test.ts`, `tooltips.test.ts`, `guide.test.ts`): *Process* for `received`, *Run again* for `settled`, `awaiting_human` and a mid-pipeline status; the confirmation appears on *Run again* for a settled claim and not for an awaiting one, *Cancel* closes it with no POST, *Run again* posts and navigates, Escape closes it, the table keeps six headers and the row one line; both buttons disabled with the reason leading the tooltip for `human_decision: 'approved'` and `'rejected'`, and *Strict re-run* no longer enabled for a rejected claim; the closed line in the Decision card and its absence while awaiting; O1's sentence; the 409 sentence in the run page's banner with the claimant link present and no waiting hint; the Guide sentence; every new string verbatim. **Mutation proof:** the disabled condition made to ignore `human_decision` → the two disabled-button tests fail; restored, green. Expected: 195 → about 210.

**Function size.** `ClaimsPage` split as above; every function under 50 lines, the page under 30. `_prepare_scenario_claim` gains four lines (about 25).

**Not touched.** The agents, the orchestrator, the audit chain and every payload, every SSE event, the run summaries, the compare and Audit pages, the Guide beyond one sentence, `settings.py`.

## 6. Version

`0.10.1.3 → 0.10.2`. A minor release, not a point release: the API refuses a request it accepted before and every claim response gains a field. Prompts 28–30 were presentation only and took the fourth digit. The bump is a backend-path change, so `deploy-backend.yml` builds a new image and `/health` reports `0.10.2`.

## 7. Deployed verification, Dermot present, on the Azure frontend

Claims as read from Azure on 14 November (31 claims):

1. **Northwood `CLM-2026-2FFB0434`** (approved 14 November): on the Claims list both buttons disabled, the tooltip leading "Closed: a person approved this claim; it cannot be run again."; the claim page's Decision card ends "The claim is closed to further runs."
2. **A fresh Northwood claim**, submitted from the form in the session and processed (it goes to a person on the ceiling rule), **rejected** in the panel with a name and a comment; the Decision card and the closed line appear at once; back on the Claims list the badge reads *Rejected* and both buttons are disabled with "Closed: a person rejected this claim …".
3. **A direct request:** `POST /api/pipeline/run/2ffb0434-…` from the shell → `409 {"detail": "claim 2ffb0434-… was approved by a person and is closed to further runs"}`; the same on `/replay`.
4. **`run_scenario` through the Claude connector:** `run_scenario(name="northwood", claim_id="2ffb0434-…")` → `claim_closed: claim 2ffb0434-… was approved by a person and is closed to further runs`; the call appears on the Integrations page's live feed as an error.
5. **A settled Harborline claim** (`9bb57a86`, three runs, or `7e98b025`): the button reads *Run again*; pressing it shows the confirmation; *Cancel* closes it with no run; *Run again* → confirmation → *Run again* opens the run page and a fourth run settles; the claim page lists it as *latest*.
6. **A claim never run:** `86797dc7` (Northwood, `received`, 13 November): the button reads *Process* and runs it (it goes to a person; it can serve as a second rejection candidate if step 2 is not wanted, but step 2's constraint asks for a claim created in the session).
7. **Prompt 29's open step 4:** *Process* on a background claim of an unsupported type never run — `c71bf1a5` (sprinkler leakage), `32891364` (vandalism) or `2469e15f` (windstorm) — watched live to its abort: the Adjuster card turns *Failed: the Adjuster has no market range for the claim type …*, the Guardrail *Not run*, the banner in the same words; the claim page then shows "The latest run stopped at the Adjuster." and the button *Run again*.

Also read: `/health` `0.10.2`; `GET /api/claims/2ffb0434-…` carries `"human_decision": "approved"`; a never-run claim carries `null`. Azure stays running.

## 8. Contradictions and loose ends in the record

- **"Every endpoint that returns a claim gains `human_decision`."** The MCP `list_claims` returns `ClaimListItem`, its own shape with `run_count`, not a `ClaimRecord`. Taken literally the field belongs there too, and Claude needs it to know a claim is closed before calling `run_scenario`; D1 asks.
- **Prompt 29's plan §4 named `RunsRepository.human_decision(conn, claim_id)`** (one claim) and a `ClaimClosedError`; this plan has one grouped function in `AuditRepository` and no new exception class (§0, §1). Same rule, fewer parts.
- **`REPLAYABLE` in `ClaimsPage.tsx`** lists `aborted`; after this prompt the member is unreachable (Part 2).
- **`run_scenario`'s description** says "Pass claim_id to re-run an existing claim" with no exception; corrected (§4). `docs/demo-mcp.md` line 20 likewise.
- **The human-decision endpoint** already makes a decision final (409 on a second decision); the prompt's constraint "no way to reopen a decided claim" holds today and nothing here adds one.
- **A run in flight reads *Run again*** on the Claims page under the agreed rule (`received` alone reads *Process*); pressing it meets the active-run 409 as *Process* does today. Noted, not changed.
- **The verification script** (`scripts/verify-demo-scenarios.py`) creates a claim then runs it, so it never meets the refusal; unchanged.
- **`docs/walkthrough.md`** says *Process* in three places, each on a claim just submitted; right as it stands.
- **`docs/test-evidence.md`'s frontend table** still carries the Phase 10 counts (noted in the Prompt 29 and 30 reports); unchanged here.
- **The backlog** item *Process can be pressed repeatedly on the same claim* describes exactly the three agreed points; marked done at close-out, with Prompt 29's step 4 if step 7 above is watched.

## 9. Risks

- **The field is computed on every read.** One grouped query per list or get, on an indexed column over a table of under two hundred rows on Azure; at production scale the human row would be joined or denormalised, which is a production-design note, not a change here.
- **Two readings of "decided", one rule.** The backend's `human_decisions` and the frontend's `deriveDecision` both take the last human row; a test on each pins it, and `api/human.py` prevents a second row.
- **The confirmation panel overlaps the next row** while open (D2 recommended); it closes on any of the three exits and only one can be open at a time, since the state is per row and opening one does not need another to close — if that reads badly on Azure, the alternative is the second line.
- **The 409's wording is the backend's** and reaches the banner unchanged; the id in it is long. The claim page link beside it is the way back.

## 10. Decisions requested

- **D1 The MCP `list_claims` item carries `human_decision` too**, so "every endpoint that returns a claim" includes the one that returns a listing of them. *Recommended: yes.*
- **D2 The settled confirmation is an anchored panel** in the actions cell (row height and table width unchanged) rather than a second line in the cell. *Recommended: the panel.*
- **D3 *Strict re-run* on a settled claim does not ask for the confirmation.** *Recommended: no confirmation.*
- **D4 The sentences in §4** as drafted, including the 409 message. *Recommended: yes, with any wording changes.*
- **D5 Version `0.10.2`.** *Recommended: yes.*
- **D6 The reading lives in `AuditRepository` as one grouped function**, departing from §4's per-claim `RunsRepository` function and its exception class. *Recommended: yes.*

**Optional, clearly beyond the spec:** O1 a fourth sentence under the review panel's buttons, "Either decision closes the claim to further runs." *Recommended: yes.*
