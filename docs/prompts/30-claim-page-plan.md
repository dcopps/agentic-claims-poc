# Prompt 30 — Plan: the claim page and the human review panel

**Prompt:** `30-claim-page.md`. **Scope:** the claim page (Parts 1 and 2), the human review panel (Part 3) and the Guide's sentences about them. Presentation only. **Written:** 13 November 2026. **Status:** approved 14 November 2026 (see *Approval*).

## 0. What the survey found

- **The claim card prints the record.** `pages/ClaimDetailPage.tsx` renders five fields through one `Field` component that sets the monospace face on every value, so the type reads `fire`, the amount `850000.00`, the jurisdiction `United States — New York`; the status badge shows the stored value because the page never passes `statusLabel`. Policy number, loss date, reported date and the submission time are in the record and not on the page. The description is an unlabelled paragraph.
- **The runs list is three stored values per line.** Each run is the variant's stored name as the link, the status badge with the stored value, the short id. No time, no "latest", no audit link. The tick boxes are unexplained (`aria-label="pick {id}"`) and *Compare selected* exists only once two are ticked, so a visitor who has ticked none never learns what the boxes do. The empty state reads "No runs yet — process this claim." with nothing to press. There is no link back to the Claims list.
- **The human review panel** (`components/HumanReviewPanel.tsx`) loads the latest run's audit rows itself (`useAuditEntries(runs[0])`) and shows, in this order: *Recommended settlement* as `820000.00` in monospace with the Adjuster's reasoning under it; *Retrieved policy passages* (linked, cited ones badged — Prompt 27); *Guardrail* as "passed — No additional issues found beyond the rule-engine pre-scan." or "flagged — Guardrail flagged 1 issue(s): hallucinated_citation."; then an unlabelled name box (placeholder "Your name"), an unlabelled comment box, *Approve* and *Reject*, with nothing saying what either does. The fired rules, the reason the reviewer is looking at the claim, appear nowhere on the page. Survey detail in §2.
- **After a decision the panel vanishes.** The page mounts the panel only while `status === 'awaiting_human'`; the audit rows are read by nobody else, so the `human_approval` / `human_rejection` row is invisible except on the Audit page.
- **The frontend's `ClaimStatus` type is behind the backend.** `api/types.ts` lists seven statuses; the backend's `ClaimStatus` has had `aborted` since Phase 6 (a rejected claim), and the Azure database holds one such claim. The page renders it (the label map and badge colour both know `aborted`), but the type lies. A type-only correction, below.
- **What a run summary holds.** `GET /api/claims/{id}/runs` returns `{correlation_id, variant, status, started_at, completed_at, escalate}` per run, newest first by `started_at` (`runs/repository.py`). No settlement figure, no failing agent, no fired rules: those live only in the audit rows (§1). A human decision does not change the run's summary status, which stays `awaiting_human`; the claim's status changes.
- **An aborted run leaves the claim's status where the run got to.** `orchestrator/pipeline.py` `_finalise_abort` writes the `pipeline_aborted` row and the event but no claim status, so an Adjuster abort leaves the claim at `coverage_verified` (Azure: Background Claimants 04 and 05). This is the whole of the part-way case in Part 1, and the latest run's rows say which agent (`failing_agent`).
- **What a human decision writes.** `api/human.py`: one audit row (`agent='human'`, step `human_approval` or `human_rejection`, payload `{decision, decided_by, comment, decided_at}`) under the latest run's correlation id, then the claim's status to `settled` (approved) or `aborted` (rejected). No figure is written anywhere: the settlement a claim is approved at is the Adjuster's recommendation in that run's rows, and nothing else records it. The prompt's draft "Approve settles the claim at the recommended figure" is therefore right in effect and slightly ahead of the record; the wording in §3 says what is written.
- **Copy, helpers and tests in place.** `copy/labels.ts` (`claimTypeLabel`, `statusLabel`, `variantLabel`), `copy/format.ts` (`formatUsd`, `formatDateTime`, `formatPercent`), `copy/run.ts` (`runCopy.adjuster`, `ruleLine`, the Guardrail sentences), `pages/runDerivation.ts` (`deriveCards`, `deriveAbort`, `deriveFiredRules`), `components/Tooltip.tsx` with the disabled-reason convention from the Claims page. `ClaimDetailPage` has **no test file**; `HumanReviewPanel.test.tsx` has four tests; `test/runFixtures.ts` has hand-built rows for the five outcomes and a `CLAIM` record.
- **`formatDateTime` is wrong for a date-only value.** `loss_date` and `reported_date` are `YYYY-MM-DD`; `new Date('2026-02-10')` is midnight UTC, which `formatDateTime` would print as "9 Feb 2026, 19:00" in New York. A date-only formatter that formats in UTC is needed (§4).
- **The Guide** mentions this page in two *Try it* sentences only (`tryMore[0]` decide an escalated claim; `tryMore[1]` tick the two runs and press *Compare selected*); *Reading a run page* does not describe it. Two sentence changes and one addition (§3).

## 1. What the record holds, by case (real rows, Azure, 13 November 2026, read-only)

The page has three sources: the claim record (`GET /api/claims/{id}`), the run summaries (`GET /api/claims/{id}/runs`) and, new in this prompt, the **latest run's audit rows** (`GET /api/audit?correlation_id=`), which the review panel already fetches for an escalated claim and which the page will fetch once for any claim with a run and pass down. One request more than today for a claim that is not awaiting a person; none for a claim never run.

| Case | Claim record | Run summaries | Latest run's rows | What the page can therefore show |
|---|---|---|---|---|
| **Never run** — `2288d578` (Harborline, `received`, 1 October), also the four Background Claimants with no run | every Part 1 field: `claim_number`, `policy_number`, `loss_date` "2026-02-10"-style, `reported_date`, `created_at`, `jurisdiction`, `narrative`, `claim_type`, `reported_amount`, `status` | `[]` | not fetched | Part 1 in full; the empty-state sentence with its link |
| **Settled, three runs** — `9bb57a86` (Harborline; runs `f8d3cc84` 17:24, `432cbc91` 17:19, `f368c2c5` 16:20 on 10 November, all `default`, all `settled`, `escalate: false`) and **`7e98b025`** (Dermot's claim of 12 November: `cc2f08e3` Standard run settled $82,500; `239cb045` **Strict Validator run** of 13 November, 13:24Z, settled **$78,000**, 78% confident) | as above, `status: settled` | variant, status, `started_at`, `completed_at`, `escalate` per run | `pipeline_settled {settlement: "82500.00", fired_rule_names: []}`, the four agent rows, `escalation_decision {fired_rules: []}` | every run: its time, kind and outcome word; **the latest run only**: "Settled at $82,500"; the status line "Settled by the latest run at $82,500" is possible but redundant beside the badge, so not proposed |
| **Aborted** — `56af95ec` (Background Claimant 04, smoke damage, `coverage_verified`; run `0aca331d` `aborted`, `escalate: null`) and `3da0940f` (hail, `8c537109`) | `status: coverage_verified`, `updated_at` = the abort time | one run, `status: aborted` | `pipeline_aborted {failing_agent: "adjuster", error_type: "ValueError", error_message: "MarketDataTable.lookup: unknown claim_type 'smoke_damage' …"}`; no `settlement_estimate`, no `escalation_decision` | Part 1's line "The latest run stopped at the Adjuster." linking to `0aca331d`; the run line "Aborted at the Adjuster" |
| **Awaiting a person** — `2ffb0434` (Northwood, `67bdf225`) and `167527a2` (Coral Bay, `e9566e92`); also `a05bddc2` (Harborline wind, $185,000, two runs, Adjuster confidence 45%) | `status: awaiting_human` | one run `awaiting_human`, `escalate: true` | `settlement_estimate {output{recommended_settlement "820000.00", confidence 0.85, reasoning}, demo_fixture}`; `output_check {output{passed, flags[{kind, detail, source}], summary}, llm_flags_discarded}`; `coverage_check {retrieval.chunks, verdict.cited_chunks}`; `escalation_decision {fired_rules[{name, rule_type, description, observed_value}]}`; `pipeline_awaiting_human {settlement, fired_rule_names}` | the whole of Part 3: the rules through `ruleLine`, "Recommends $820,000 (85% confident)", the Guardrail in the run page's words with the flag's detail beneath, the reasoning, the passages |
| **Approved by a person** — **none on Azure.** No claim carries a `human_approval` row (every run's rows read, 29 claims, 31 runs) | by code (`api/human.py`): `status: settled` | the latest run's summary stays `awaiting_human` | `human_approval {decision: "approved", decided_by, comment, decided_at}` as the last row | the Decision card; §6 creates the first such claim during verification |
| **Rejected by a person** — `75afb337` (Harborline, 26 October; run `8590b47e`) | `status: aborted` | one run, summary `awaiting_human`, `escalate: true` | the escalated run's rows, then `human_rejection {decision: "rejected", decided_by: "Dermot", comment: "Test rejection", decided_at: "2026-11-10T18:50:06Z"}` | the Decision card: "Rejected by Dermot on 10 Nov 2026, 18:50 · Test rejection"; the badge reads *Aborted* (D4) |

**What the prompt asks for that the record cannot give without an API change — none for the page as drafted, with one limit.** "Settled at $82,500" / "Aborted at the Adjuster" needs that run's rows, and only the latest run's are loaded, so the richer phrase is on the latest line alone; every other line carries the outcome word (`statusLabel`: *Settled*, *Awaiting human review*, *Aborted*, *Running*). Saying it on every line would cost one request per run, which the prompt rules out (D2). The fail-closed case (the Guardrail itself threw; test fixture `guardrailThrewRows`) has no `escalation_decision` row: the awaiting row's `fired_rule_names: ['guardrail_failed']` and `reason: 'guardrail_threw'` give the panel its one line (§3).

## 2. The human review panel as it renders (Azure, 13 November 2026)

Screenshots: `/var/folders/s5/9ndcsrjj19nf1hq30slcw0bh0000gn/T/claude-chrome-screenshots-qG2LgM/screenshot-1794584643687-5.jpg` (Northwood, the top of the page) and the rendered text of both pages, read with the browser.

**Northwood** (`2ffb0434`, over the ceiling). Claim card: *Northwood Manufacturing Inc* · Claim number `CLM-2026-2FFB0434` · Type `fire` · Amount `850000.00` · Jurisdiction `United States — New York` · Status `awaiting_human` (all monospace) · the narrative. Panel *Human review*: *Recommended settlement* `820000.00`, then the reasoning (five sentences, readable); *Retrieved policy passages*: Named Perils Covered *cited*, Business Interruption, Exclusions *cited*, each with its excerpt "…(truncated, full length=1493)"; *Guardrail*: "passed — No additional issues found beyond the rule-engine pre-scan."; the name box, the comment box, *Approve* (blue, disabled) and *Reject* (red, disabled). Nothing says the settlement is over the $250,000 ceiling. Runs: `default` · `awaiting_human` · `67bdf225`.

**Coral Bay** (`167527a2`, Guardrail failure and over the ceiling). The same shape: *Recommended settlement* `1400000.00` with the fixture's reasoning naming the Coastal Surge Rider; passages Business Interruption *cited*, Named Perils Covered *cited*, Sub-Limits; *Guardrail*: "flagged — Guardrail flagged 1 issue(s): hallucinated_citation." The flag's detail ("endorsement 'Coastal Surge Rider' not in retrieved chunks") is in the row and not shown; nor that the Adjuster's answer came from the fixed demonstration file; nor the two rules.

**Findings, in the prompt's order.** (1) The settlement is a raw string, no confidence. (2) No fired rules anywhere on the page. (3) The Guardrail verdict is the stored boolean and the model's summary line. (4) The reasoning is already prose, but sits as a definition under the monospace figure with no label. (5) The passages are as Prompt 27 left them and stay. (6) No visible labels; nothing says what *Approve* and *Reject* do; both are disabled until a name is typed and nothing says so. (7) After a decision the panel is gone and the page shows only the new badge; the 26 October rejection is invisible on `75afb337`'s page except as *Aborted*. Two more: the panel invalidates `['claim', id]` after a decision, which refreshes the claim and (by prefix) the runs, but not the audit rows, so a Decision card read from the rows would not appear until a reload; and the page re-requests the rows on every mount because the panel owns the query.

## 3. Every sentence and label the page can show (for approval)

New module `frontend/src/copy/claim.ts` (`claimCopy`), in the style of `copy/run.ts`. Tooltip texts in `copy/tooltips.ts`. The two Guide sentences in `copy/guide.ts`.

**Part 1 — the claim card** (title: the claimant's name; two-column list, labels as the form's `FIELD_LABELS` where the form has the field)

| Label | Value, as shown | Source and form |
|---|---|---|
| *Claim number* | `CLM-2026-1004` | monospace (an identifier) |
| *Policy number* | `CP-2026-8004` | monospace |
| *Claim type* | Smoke damage | `claimTypeLabel` |
| *Reported amount* | $29,925 | `formatUsd` |
| *Jurisdiction* | Bermuda | as stored (words) |
| *Loss date* | 10 Feb 2026 | new `formatDate` (date-only, UTC) |
| *Reported date* | 12 Feb 2026 | `formatDate` |
| *Submitted* | 1 Oct 2026, 18:14 | `formatDateTime(created_at)`, the reader's zone, as the Claims page's *Submitted* column |
| *Status* | the badge through `statusLabel` ("Coverage checked"), then the status line when there is one | see below |
| *Description* | the narrative | ordinary text face |

The status line, beside the badge, in one of these forms:

- "The latest run stopped at the Adjuster." — the claim's status is one of `extracted`, `coverage_verified`, `estimated`, `guardrail_checked` and the latest run's rows hold `pipeline_aborted`; "the latest run" links to that run. (`claimCopy.stoppedAt(agentLabel)`)
- "A run is in progress." — the latest run's summary is `running`; linked. (`claimCopy.runInProgress`)
- Nothing otherwise: `received`, `settled`, `awaiting_human` and `aborted` say their own thing, and the Decision card speaks for a person's decision.

Above the card: *← Claims list* (`claimCopy.backToClaims`, a `Link` to `/`).

**Part 2 — the runs**

- Card title *Runs*. Above the list, only when there are two or more runs: "Tick two runs to compare them side by side." (`claimCopy.compareHint`) with the *Compare selected* button (secondary) on the same line, always rendered with two or more runs, disabled until exactly two are ticked.
- Tooltip on *Compare selected*, in the Claims page's convention (the disabled reason leads): `tooltips.disabledCompareNeedsTwo` "Not yet available: tick exactly two runs. " + `tooltips.compareSelected` "Opens the two runs side by side: the settlement, whether each went to a person, the Guardrail's verdict and the rules that differed. In production the same comparison would be run before a model is promoted."
- Each run, one line, newest first as the API orders them: the tick box (`aria-label` "Select the run of 10 Nov 2026, 17:24"), **the start time as the link** to the run page ("10 Nov 2026, 17:24", `formatDateTime(started_at)`), a *latest* badge on the first line (`claimCopy.latest`), the kind of run (`variantLabel`: "Standard run", "Strict Validator run"), the outcome, the short id in small monospace, and *Audit log* (`claimCopy.auditLog`, a `Link` to `/audit?correlation_id=…`, the run page's own link).
- The outcome: for the latest run, from its rows (`claimCopy.runOutcome`): "Settled at $82,500" · "Aborted at the Adjuster" · "Awaiting human review" (no figure: the panel below says it) · "Running"; for every other run, `statusLabel(status)`. A run with no terminal row and no `agent_started` is "Running" in both.
- Empty state: "No runs yet. Go back to the Claims list and press Process on this claim." with *Claims list* linked (`claimCopy.noRuns`, segments like the Guide's so the link is a `Link`).

**Part 3 — the human review panel** (card title *Human review*), in this order:

1. *Why this claim is here* — one line per fired rule through `ruleLine` ("Settlement over the $250,000 ceiling: $820,000"; "Guardrail check did not pass"), from the `escalation_decision` row; when the Guardrail itself threw, the one line "Guardrail check itself failed, so the claim went to a person" from the awaiting row. (`claimCopy.whyHeading`)
2. *Recommended settlement* — "Recommends $820,000 (85% confident)" through `runCopy.adjuster`, so the fixture reads "Recommends $1,400,000 from the fixed demonstration file, no model call (82% confident)" here too.
3. *The Adjuster's reasoning* — the reasoning as a paragraph in the ordinary face.
4. *Guardrail* — the run page's sentence from `deriveCards(rows, []).guardrail` ("Passed", "Passed; 1 objection refused", "Failed: cited policy wording the policy does not contain") with the flag's detail beneath in small type ("endorsement 'Coastal Surge Rider' not in retrieved chunks"), as the card shows it.
5. *Retrieved policy passages* — unchanged.
6. The form: visible labels *Your name* and *Comment (optional)*; under the buttons, one sentence each (`claimCopy.approveDoes`, `claimCopy.rejectDoes`), checked against `api/human.py`:
   - "Approve marks the claim Settled; the Adjuster's recommendation above stands as the settlement." (nothing writes a figure: the recommendation in the run's record is the settlement)
   - "Reject marks the claim Aborted; no settlement is made."
   - and one line for both: "Your name, your comment and the time are written to the audit trail under this run." (`claimCopy.decisionRecorded`)
   - while no name is typed, the buttons stay disabled and a small line says "Enter your name to decide." (`claimCopy.nameRequired`) — one sentence beyond the prompt's list, so a disabled button is explained as the Claims page's is; say no and it goes.
7. On failure the backend's detail as now ("claim … is not awaiting human review (status=settled)").

**The Decision card** (title *Decision*), in the panel's place once the claim is no longer awaiting a person and the latest run's rows hold a human row:

- "Approved by A. Reviewer on 13 Nov 2026, 15:02." / "Rejected by Dermot on 10 Nov 2026, 18:50." (`claimCopy.decided(decision, by, when)`)
- the comment as a quoted line beneath, or "No comment was left." (`claimCopy.noComment`)
- "The decision is recorded in the audit trail under the run it was made on." with *the run* linking to that run (`claimCopy.decisionInAudit`).

**The Guide** (`copy/guide.ts`, tests in `guide.test.ts` and `GuidePage.test.tsx`):

- `tryMore[0]`: "To decide an escalated claim, open it from the Claims list by the claimant's name, read why it is there, and use *Approve* or *Reject* in the Human review panel; the claim page then records who decided and when."
- `tryMore[1]`: "…then open the claim, tick the two runs in its Runs list and press *Compare selected*."
- `runPage`, one sentence added at the end: "The claimant's name under the header opens the claim page, which lists every run of the claim by the time it started, with its outcome."

## 4. Files touched and tests

| File | Change |
|---|---|
| `frontend/src/copy/claim.ts` (new) | every sentence and label in §3 for the page, the panel and the Decision card |
| `frontend/src/copy/format.ts` | `formatDate(isoDate, options)` — a date-only value in UTC, "10 Feb 2026"; unparseable input returned as is, like the others |
| `frontend/src/copy/tooltips.ts` | `compareSelected`, `disabledCompareNeedsTwo` |
| `frontend/src/copy/guide.ts` | the three sentences in §3 |
| `frontend/src/api/types.ts` | `ClaimStatus` gains `'aborted'` (type only; the API has returned it since Phase 6) |
| `frontend/src/hooks/queries.ts` | `useAuditEntries(correlationId, enabled = true)`, the `useClaim` pattern, so the page fetches nothing for a claim with no run |
| `frontend/src/pages/claimDerivation.ts` (new, pure) | `latestRun(runs)`; `deriveRunOutcome(summary, rows)` → the outcome phrase's inputs; `deriveStoppedAt(status, rows)`; `deriveDecision(rows)` → `{decision, decidedBy, comment, decidedAt, correlationId} \| null`; `deriveWhyHere(rows)` → `FiredRule[]` or the fail-closed marker; reuses `deriveAbort`, `deriveFiredRules`, `deriveCards`, `agentLabel` from `runDerivation.ts` |
| `frontend/src/pages/ClaimDetailPage.tsx` | rewritten: the page loads the claim, the runs and the latest run's rows; components `ClaimCard` (fields and the status line), `RunsList` / `RunLine` (the hint, the always-present button, the tick boxes, the audit link), `NoRuns`; mounts `HumanReviewPanel` with the rows, or `DecisionCard`; every function under 50 lines |
| `frontend/src/components/DecisionCard.tsx` (new) | the card in §3 |
| `frontend/src/components/HumanReviewPanel.tsx` | takes `rows` (and `correlationId`) from the page instead of fetching; the sections in §3's order; labelled inputs; the sentences under the buttons; after a decision invalidates `['claim', id]` **and** `['audit', correlationId]` so the Decision card appears without a reload |
| `frontend/src/test/runFixtures.ts` | `RUN_SUMMARIES` (three settled runs, newest first), `decisionRows(decision)` appending the human row to `ceilingRows()`, `RUNNING_SUMMARY` |
| `frontend/src/pages/ClaimDetailPage.test.tsx` (new) | the claim card in words (type, amount, dates, status label, labelled description); the part-way status line linking to the aborted run; the runs list (time as the link, *latest* on the first, kind, outcome, short id, audit link); the latest line's "Settled at $82,500" against the second line's "Settled"; the hint and *Compare selected* present with two runs, disabled with none and one ticked, enabled with two, the tooltip leading with the reason; absent with one run; the empty state's link; the Decision card for a rejected and an approved claim and its absence while awaiting a person; the back link |
| `frontend/src/pages/claimDerivation.test.ts` (new) | each function from hand-built rows and summaries, including the fail-closed case and a human row with a null comment |
| `frontend/src/copy/claim.test.ts` (new) | every sentence verbatim; `runOutcome` for the four outcomes |
| `frontend/src/copy/format.test.ts` | `formatDate` in a fixed locale, and that "2026-02-10" is 10 February in a western zone |
| `frontend/src/components/HumanReviewPanel.test.tsx` | the four tests rewritten to pass rows; new: the rule lines first, the settlement sentence, the Guardrail sentence with its detail for Coral Bay, the labelled inputs, the sentences under the buttons, the audit invalidation after a decision |
| `frontend/src/copy/tooltips.test.ts`, `guide.test.ts`, `pages/GuidePage.test.tsx` | the new texts; `tryMore[1]`'s labels unchanged |

**Mutation proof** (applied, observed, reverted): `deriveDecision` made to ignore the human row — the Decision-card tests in `ClaimDetailPage.test.tsx` and `claimDerivation.test.ts` fail; restored, green. Expected count: 148 → about 185.

**Function size.** The current `RunsList` is 40 lines; with the hint, the button and the richer line it is split into `RunsList` and `RunLine`. `Evidence` in the panel becomes four small sections.

**Not touched.** Nothing under `backend/`; no HTTP or SSE shape, stored value, column or setting; no dependency. `useClaim`, `useClaimRuns`, the Claims page, the run page, the compare page and the Audit page are unchanged (the compare page's own raw values are a later prompt).

## 5. Version

`0.10.1.2 → 0.10.1.3` in `pyproject.toml`, a point release, presentation only — the same mechanism as Prompts 28 and 29: the bump is a backend-path change, so `deploy-backend.yml` builds a new image and the Container App's `/health` reports the version the frontend was built with.

## 6. Deployed verification, Dermot present, on the Azure frontend

1. **Background Claimant 04** (`56af95ec`): "Smoke damage · $29,925", *Coverage checked* with "The latest run stopped at the Adjuster." linking to `0aca331d`; the run line "10 Nov 2026, 15:30 · latest · Standard run · Aborted at the Adjuster · 0aca331d · Audit log"; no compare hint (one run).
2. **Harborline, three runs** (`9bb57a86`): three lines by time, *latest* on 17:24, "Settled at $82,500" on it and *Settled* on the others; the hint; *Compare selected* disabled, then enabled on the second tick, opening the comparison. Also **`7e98b025`** for "Strict Validator run" beside "Standard run" and a comparison that differs ($78,000 against $82,500).
3. **Northwood awaiting a person** (`2ffb0434`): the panel in §3's order, "Settlement over the $250,000 ceiling: $820,000" first; **Coral Bay** (`167527a2`) for the two rules, the fixture sentence and the Guardrail's failure with its detail.
4. **A claim approved in the session:** a new Northwood claim submitted from the Claims page and processed (not a run the register or the build log names), approved in the panel with a name and a comment; the page shows the Decision card at once; reopened from the Claims list it shows the card again, with the badge *Settled*.
5. **The rejected claim** (`75afb337`, read-only): the Decision card "Rejected by Dermot on 10 Nov 2026, 18:50 · Test rejection", the badge *Aborted*.
6. **A claim never run** (`2288d578`): the empty state with its link; the back link.
7. The Guide's three sentences on the deployed page.

## 7. Contradictions and loose ends in the record

- **The date of run `0eb6b1cc`.** Dermot's message of 13 November, and the addendum written from it in the Prompt 29 report, the build log and `CLAUDE.md`, say the live Harborline run was on 12 November. The audit trail says the run started **2026-11-11T10:27:51Z** on claim `3a735ef1` (created 11 November 10:26); it is the only run settled at $82,500 with one refused objection. A second Harborline claim, `7e98b025`, was created on 12 November at 22:08Z and run at once (`cc2f08e3`, settled $82,500, no refused objection), then re-run strictly today. The addendum stands on Dermot's word; say which date is right and it is corrected in the three places.
- **No approved claim on Azure.** The prompt's §1 lists one; the shape is read from `api/human.py` and from the rejection row, and §6 step 4 creates the first.
- **`ClaimStatus` in `api/types.ts` omits `aborted`**, which the API returns for a rejected claim. Corrected here as a type; no runtime change.
- **The walkthrough** (`docs/walkthrough.md`, *Human review* scene) says "status flips to `settled`"; with the Decision card it could add one line. Not in the prompt; listed as O1.
- **`docs/test-evidence.md`'s frontend table** still carries the Phase 10 counts (noted in the Prompt 29 report); unchanged by this prompt.
- **The Claims page's `REPLAYABLE` set** and the backend's replay rule still differ (Prompt 29 report, suggestions); Prompt 31 decides the rule.

## 8. Risks

- **Dates in the reader's zone.** The loss and reported dates are calendar dates and must not shift with the zone; `formatDate` formats in UTC and the test pins a western zone. Times (`started_at`, `created_at`, `decided_at`) stay in the reader's zone, as the Claims page shows them.
- **"Latest" is the first summary.** The API orders by `started_at` descending and `api/human.py` decides on the same first run, so the page and the backend agree on which run a decision lands on; the page does not re-sort.
- **The rows request for every claim with a run.** One more request on a settled claim's page than today; it is the request the panel already made for an escalated claim, moved up to the page, and the waking notice already covers it.
- **The panel's tests** change shape (rows as a prop); the four existing assertions are kept in the rewritten tests.

## 9. Decisions requested

- **D1 The richer outcome phrase on the latest run only** ("Settled at $82,500", "Aborted at the Adjuster"), the outcome word on the others; no request per run. *Recommended: yes.*
- **D2 The page owns the latest run's rows** (one `useAuditEntries` on the page, passed to the status line, the runs list, the panel and the Decision card) rather than the panel fetching its own. *Recommended: yes.*
- **D3 The sentences in §3** as drafted, including the two under the buttons as corrected against the backend. *Recommended: yes, with any wording changes.*
- **D4 A rejected claim's badge stays *Aborted*** (the stored value's label, as on the Claims list), with the Decision card saying a person rejected it; the alternative is a claim-page-only label *Rejected*, which would differ from the list. *Recommended: keep Aborted.*
- **D5 "Enter your name to decide."** under the disabled buttons (one sentence beyond the list). *Recommended: yes.*
- **D6 `ClaimStatus` gains `aborted`** as a type-only correction in this prompt. *Recommended: yes.*
- **D7 The date of run `0eb6b1cc`** in the three addendum places: leave 12 November as stated, or correct to 11 November as recorded. *Recommended: correct to the recorded date.*

**Optional, clearly beyond the spec:** O1 one line in `docs/walkthrough.md`'s *Human review* scene naming the Decision card. *Recommended: yes, one line.*

## Approval

**Approved by Dermot, 14 November 2026.** D1, D2, D3, D5 and D6 as recommended. **D7: correct to the recorded date, 11 November**, in the Prompt 29 report, the build log and `CLAUDE.md`. **D4 changed:** a claim's stored status `aborted` only ever comes from a person's rejection, so it is labelled **Rejected** wherever a *claim's* status is shown (the Claims list and the claim page), while a *run's* status `aborted` keeps **Aborted**; `statusLabel` served both today, so it is split into a claim-status label and a run-status label; the sentence under the button reads "Reject marks the claim Rejected; no settlement is made." O1 as recommended (one line in the walkthrough).
