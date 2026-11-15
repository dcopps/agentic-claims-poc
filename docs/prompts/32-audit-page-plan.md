# Prompt 32 — Plan: the Audit page and the record viewer

**Prompt:** `32-audit-page.md`. **Scope:** the Audit page in words — the run named by its claim, a way to find a run, one sentence per record, the chain check in sentences — and a reusable record viewer in a dialog, built from the project's own components. **Written:** 15 November 2026, from the code and a read-only reading of the five named runs on Azure. **Status:** awaiting approval (see *Decisions requested*).

## 1. Every step the audit trail can hold, and the sentence its row will show

Read from `backend/app/orchestrator/pipeline.py`, `backend/app/api/human.py`, the four agents' payload builders, and the rows of the five runs the prompt names, fetched from the Azure backend on 15 November (read-only): Harborline `f23ea4dc` (settled, 7 rows, audit ids 208–214), Northwood `2bd08a61` (ceiling rule, rejected, 8 rows, 200–207), Coral Bay `e9566e92` (demo fixture, Guardrail failure, 7 rows, 106–112), Northwood `67bdf225` (ceiling rule, approved, 8 rows, 99–105 and 185), Background Claimant 01 `b3e7dc6c` (aborted at the Adjuster, 4 rows, 215–218). The fail-closed path (the Guardrail itself threw) has no row on Azure; its payload is read from `_finalise_guardrail_throw`.

Every sentence below is an existing one from `copy/run.ts`, `copy/claim.ts` or `copy/labels.ts`, or a new one in a new `copy/audit.ts`. Nothing is worded twice.

| Step (agent) | Row fields read | Sentence shown | Source |
|---|---|---|---|
| `pipeline_started` (orchestrator) | `variant` | "Run started: Standard run" / "Run started: Strict Validator run" | new `auditCopy.started(variantLabel)` |
| `doc_extract` (doc_parser) | `output.claim_type` | "Summarised the claim (Water damage)" | `runCopy.docParser` |
| `coverage_check` (validator) | `verdict.covered`, `verdict.confidence` | "Covered (92% confident)" / "Not covered (58% confident)" | `runCopy.validator` |
| `settlement_estimate` (adjuster) | `output.recommended_settlement`, `output.confidence`, `demo_fixture` | "Recommends $78,000 (85% confident)"; fixture: "Recommends $1,400,000 from the fixed demonstration file, no model call (82% confident)" | `runCopy.adjuster` |
| `output_check` (guardrail) | `output.passed`, `output.flags[].kind`, `llm_flags_discarded` | "Passed" / "Passed; 1 objection refused" / "Failed: cited policy wording the policy does not contain" | `runCopy.guardrailPassed` / `guardrailFailed` |
| any agent row with `error` set | `error.type`, `error.message` | "Failed: the model provider refused or failed the call" (the orchestrator's abort row follows and names the agent) | `runCopy.failed(failureReason(…))` |
| `escalation_decision` (orchestrator) | `escalate`, `fired_rules[]` | "No rule fired; the claim settles" / "Sent to a person: Settlement over the $250,000 ceiling: $950,000" (rules joined with "; ") | new `auditCopy.noRuleFired`, `auditCopy.sentToPerson(ruleLines)` over `ruleLine` |
| `pipeline_settled` (orchestrator) | `settlement` | "Settled at $78,000" | `claimCopy.runOutcome({kind: 'settled', settlement})` |
| `pipeline_awaiting_human` (orchestrator) | `reason` | "Awaiting human review"; fail-closed (`reason: guardrail_threw`): "Awaiting human review: Guardrail check itself failed, so the claim went to a person" | `runStatusLabel`; `ruleLine` of the synthetic rule |
| `pipeline_aborted` (orchestrator) | `failing_agent`, `error_type`, `error_message` | "Run aborted: the Adjuster has no market range for the claim type Sprinkler leakage" | `runCopy.aborted(failureReason(agentLabel(…), …))` |
| `human_approval` / `human_rejection` (human) | `decided_by` | "Approved by Dermot Copps" / "Rejected by Dermot Copps" (the row's own time column carries the date; the comment is in the record) | new `auditCopy.decided(decisionWord, name)` |
| any other step | — | the step in readable words | `readableFallback` |

**Who wrote it** (the second column): `agentLabel` for the four agents (Doc-Parser, Validator, Adjuster, Guardrail); "Orchestrator"; "A person" for `agent = 'human'` (new `auditCopy.who`). The sentence names the person.

**The record's name in the dialog header** (plain words for the step, new `auditCopy.stepName`): run started · narrative summary · coverage check · settlement estimate · output check · escalation decision · settled · sent to a person · run aborted · approval · rejection. Example header: "Validator · coverage check · 15 Nov 2026, 15:09:08 · record 210 in the ledger".

The sentences are built by a new pure module `pages/auditDerivation.ts` (`rowSentence(entry)`, `rowAuthor(entry)`, `recordHeader(entry)`, `extractPrompt(entry)`, `isDemoFixture(entry)`), in the manner of `runDerivation.ts`, so every row kind is testable from hand-built rows.

## 2. What the existing endpoints allow, and what needs a backend change

**Naming the claim and the run — no backend change.** The run's own `pipeline_started` row carries `claim_id` and `variant`; `GET /api/claims/{id}` gives the claimant, type, amount and number. The page therefore does what the run page does: `deriveClaimId(rows, [])` then `useClaim(claimId, claimId !== '')`, with `runCopy.claimDetails` for the second half of the line and the claimant as the link to the claim page. The kind of run is `deriveVariant`, the start is the first row's `created_at` (the `pipeline_started` payload's `started_at` where present), and the outcome is `claimCopy.runOutcome(deriveRunOutcome(status, rows))` — which already reads a person's decision from the human row ("Approved after human review"), the settled figure and the failing agent. A link "Open the run page" goes to `/claims/{claim_id}/runs/{cid}`.

**Finding a run — needs one new endpoint.** Nothing lists runs across claims: `GET /api/claims/{id}/runs` is per claim, `GET /api/runs/{cid}` is one run, and `GET /api/claims` (newest 50) carries no runs. Composing a list on the page would cost one request per claim (32 on Azure today) each time *Audit* is opened. Reading a short id has the same gap: `GET /api/audit?correlation_id=` takes a UUID and answers 422 to eight characters, and matching a prefix needs the database. One endpoint serves both:

**Interface-stability acknowledgement.** `GET /api/runs` (new; declared before `/compare/…` and `/{correlation_id}` so the literal path wins) with `limit` (1–100, default 20) and optional `prefix` (8–36 characters of `[0-9a-f-]`, lower-cased; anything else 422). Returns `RunListItem[]`, newest first by the `pipeline_started` row: `{correlation_id, claim_id, claim_number, claimant_name, variant, status, started_at, completed_at, escalate, human_decision}` — the existing `RunSummary` fields plus the four that name the claim and say whether a person has decided it. With `prefix`, only runs whose id begins with it (0, 1 or more). Additive: no existing endpoint, payload, table, column, setting or SSE event changes; the audit chain is untouched. Implemented as `RunsRepository.list_recent_runs(conn, limit, prefix)` — one query for the latest `pipeline_started` rows joined to `claims` (`correlation_id::text LIKE %s` for the prefix; the prefix is validated to hex and hyphens, so no LIKE metacharacters reach it), one query for those runs' rows summarised by the existing `_summarise`, and `AuditRepository.human_decisions` for their claims. No migration: `audit_log_correlation_id_idx` and the `claims` primary key serve it. *Recommendation: build it (D1).* The alternative, a recent-runs list composed on the page and a short id matched only against that list, leaves older runs unreachable by their short id and costs a request per claim.

**On the page.** Under the heading, a *Recent runs* list (the 20 latest) — one line each, the whole line a link: claimant, claim number, kind of run, start time, outcome word (through `runStatusLabel`, or *Approved* / *Rejected* from `human_decision`). The box accepts a full id (loaded as today) or a short one: the page calls `GET /api/runs?prefix=` and loads the run when exactly one matches; with none it says so; with several it says how many and asks for more of the id. The address keeps `?correlation_id=<full id>`, so every existing link lands as before.

## 3. The record viewer

**Three components, one of them generic.**

- **`components/Dialog.tsx`** — a modal that behaves: `role="dialog"`, `aria-modal`, labelled by its heading; opens with focus on its close button; Tab and Shift+Tab cycle among the focusable elements inside it and never leave; Escape, the close button and a click on the backdrop (a mousedown whose target is the backdrop itself, not the panel) close it; on close, focus returns to the element that had it when the dialog opened; `document.body` is given `overflow-hidden` while it is open and restored on close; the panel is `max-w-3xl max-h-[85vh] overflow-y-auto`, so it fits a laptop screen and scrolls inside itself. Why not the browser's own `<dialog>` with `showModal()`: it would give the focus trap for nothing, but jsdom 29.1.1 (checked this session) has no `showModal` or `close`, so none of the keyboard behaviour could be tested; the hand-rolled dialog is about sixty lines and every behaviour above gets a test (D2).
- **`components/RecordTree.tsx`** — the stored record as a tree. Each object and list is a node with a disclosure button (`aria-expanded`) that reads, when closed, "{5 keys}" or "[3 items]"; keys in slate, strings green, numbers blue, booleans purple, null grey italic (one small class map in the component, from the tokens' palette). **What starts open:** the record's own keys and the objects directly under them (depth 0 and 1) are open; everything deeper is closed, so the Validator's `verdict` and the Adjuster's `output` are readable at once and the retrieval chunks and the prompt are a click away (D3). **Long text:** a string longer than 240 characters is shown truncated with a *Show all* button that expands it in place (*Show less* to fold it); text wraps (`whitespace-pre-wrap break-words`) with its line breaks and is never wider than the dialog, which is `overflow-x: hidden`.
- **`components/RecordDialog.tsx`** — the viewer: takes `{entry, header, onClose}` and knows nothing of the Audit page. The header line (§1). Two tabs (`role="tablist"`, arrow keys move between them): *Record* — the `RecordTree` over `entry.payload`; *Instructions sent* — only when `extractPrompt(entry)` finds `llm_call.prompt.system` and `.user` (the same path in all four agents since Phase 8.3; the AgentCard's `extractPrompt` moves to `auditDerivation.ts` and the card imports it, D8), shown as two `whitespace-pre-wrap` blocks under the headings *System instructions* and *Message to the model*. A record with no model call shows no second tab; when `llm_call.provider === 'demo_fixture'` the Record tab opens with the sentence "No model was called for this record: the Adjuster's figure came from the fixed demonstration file." *Copy record* copies the whole row — `audit_id`, `agent`, `step`, `created_at`, `chain_hash`, `payload` — as the API served it, `JSON.stringify(entry, null, 2)`, so a paste elsewhere is the record and identifies itself, not the page's rendering (D4). *Close* at top right.

**On the Audit page** a row's sentence is a button ("Open record 210"); the whole row is clickable too. The dialog mounts in the page's tree (no portal is needed: the nav is `z-10`, the dialog `z-40`). The old in-row `JsonBlock` is removed from this page; `JsonBlock` itself and its other two users (`AgentCard`, `AgentTestPanel`) are unchanged.

## 4. Every sentence, label, heading and tooltip

All in new `copy/audit.ts` (`auditCopy`) unless named otherwise.

- Page heading: **Audit log** (unchanged). Field label: **Run id**. Hint under the box: "Paste a run id, or its first eight characters." Button: **Load**.
- Recent runs heading: **Recent runs**. Line: "Harborline Logistics Ltd · CLM-2026-7E98B025 · Standard run · 15 Nov 2026, 15:09 · Settled". Empty: "No runs recorded yet."
- Before an id is given: "Enter a run id, or choose a run above, to see its records."
- Short id: "No run starts with f23ea4d." / "3 runs start with f23e; give more of the id."
- Unknown id: "No run has this id." Failed load: "The records could not be loaded." Loading: "Loading records…" (with the waking notice).
- The run's header card: line 1 as the run page's claim line (`runCopy.claimDetails`, claimant linked); line 2 "Standard run · started 15 Nov 2026, 15:09:03 · Settled at $78,000 · " then the link **Open the run page**. A claim that cannot be loaded: `runCopy.claimUnavailable`.
- Table headings: **When** · **Who** · **What happened** · **Record**. The Record cell: "#210 · a1b2c3d4e5f6" (number, then the first twelve characters of the hash in monospace). ⓘ on the heading (`tooltips.chainHash`, new): "Each record is numbered in the order it was written. The code is the start of its hash: a fingerprint of this record and of the one before it, so changing any record changes every hash after it. Verify chain recomputes them all."
- The button: **Verify chain** (whole-ledger in the sentence, not the label — D5); its ⓘ keeps `tooltips.verifyChain` (the production note). Result, ok: "Checked all 218 records in the ledger, this run's included: every hash matches." Break: "A break at record 57: the record's own hash does not match its contents." (`row_hash_mismatch`) / "A break at record 57: the link to the record before it does not match." (`chain_hash_mismatch`); an unknown kind: "A break at record 57 ({kind})."
- Dialog: **Close**; tabs **Record**, **Instructions sent**; headings **System instructions**, **Message to the model**; **Copy record** / **Copied** (the `CopyButton`); "No model was called for this record: the Adjuster's figure came from the fixed demonstration file."; tree: **Show all**, **Show less**, "{n} keys", "{n} items", "empty".
- The Guide (`copy/guide.ts`): *Try it* step 5 reads "Press View audit log, then Verify chain, to check every recorded step against its hash." (label changed); *Reading a run page*: "“View audit log” opens every recorded step of the run as a sentence, with its place in the ledger; a step opens as the full record." `docs/walkthrough.md`'s Audit section: "open the Audit nav link, choose the run from Recent runs or paste its id, press Verify chain" and the screen line in the new sentence.

## 5. Files touched and tests

**Backend** (D1): `backend/app/runs/models.py` (`RunListItem`), `runs/repository.py` (`list_recent_runs`, under 50 lines with one helper), `runs/__init__.py`, `api/runs.py` (`GET /api/runs`). Tests in `test_api_claims_runs.py` or new `test_api_runs_list.py`: newest first across two claims; `limit` honoured; the claim fields and `human_decision` (null, approved); `prefix` matching one, several and none; a prefix with other characters → 422; an in-flight run listed as `running`. Expected: 540 → about 548.

**Frontend.** New: `copy/audit.ts`, `pages/auditDerivation.ts`, `components/Dialog.tsx`, `components/RecordTree.tsx`, `components/RecordDialog.tsx`, `hooks/queries.ts` (`useRecentRuns`, `useRunsByPrefix`), `api/client.ts` (`listRuns`), `api/types.ts` (`RunListItem`). Rewritten: `pages/AuditPage.tsx` as `AuditPage` (shell), `RunFinder` (box, hint, recent list, short-id resolution), `RunHeading` (claim line, run line), `RecordsTable` / `RecordRow`, `VerifyChain`; every function under 50 lines. Changed: `copy/tooltips.ts` (`chainHash`), `copy/guide.ts`, `components/AgentCard.tsx` (imports `extractPrompt`; no behaviour change), `docs/walkthrough.md`.

**Tests** (existing style; `renderWithProviders`, `stubFetch`, `runFixtures`). New `copy/audit.test.ts` (every sentence verbatim; the verify sentences for both break kinds); `pages/auditDerivation.test.ts` (one sentence per row kind over `runFixtures` and hand-built rows: settled, ceiling, fixture, Guardrail failure, abort, fail-closed, approval, rejection, an agent row with `error`, an unknown step; the header line; `extractPrompt` on a row with, without and with a malformed prompt); `components/Dialog.test.tsx` (focus lands on Close; Tab from the last element wraps to the first and Shift+Tab back; Escape, Close and a backdrop click each call `onClose` while a click inside does not; focus returns to the opener; body scroll locked while open and restored); `components/RecordTree.test.tsx` (depth 0 and 1 open, depth 2 closed with its summary; toggling; a long string truncated then *Show all*; kinds carry their classes); `components/RecordDialog.test.tsx` (both tabs for an agent row and the headings' text; no second tab for an orchestrator row and a human row; the fixture sentence; **Copy record writes `JSON.stringify(entry, null, 2)`**); `pages/AuditPage.test.tsx` rewritten (the label *Run id*; recent runs listed and one chosen loads it; a short id resolving to one run, to several, to none; the claim line and run line for a settled and a rejected run; the rows in words for the five fixtures; verify ok and both breaks in sentences; unknown id, failed load, empty; a row opens the dialog and Close returns focus to the row's button); `guide.test.ts` updated. Expected: 212 → about 250.

**Mutation proofs.** *Copy record* made to copy the payload alone → the RecordDialog test fails; restored, green. The Dialog's Tab handling removed → the wrap test fails; restored, green.

## 6. Version

`0.10.2 → 0.10.3` (D7): a minor release because the API gains an endpoint; the backend workflow builds a new image and `/health` reports it. Without D1 the change would be presentation only and take the fourth digit, `0.10.2.1`.

## 7. Deployed verification, Dermot present, on the Azure frontend

1. **Harborline `CLM-2026-7E98B025`, run `f23ea4dc`** (settled 15 November): opened from *Recent runs*; the header names the claim and "Standard run · started 15 Nov 2026, 15:09:03 · Settled at $78,000"; seven rows read "Run started: Standard run", "Summarised the claim (Water damage)", "Covered (92% confident)", "Recommends $78,000 (85% confident)", "Passed", "No rule fired; the claim settles", "Settled at $78,000"; the Validator's record opens with both tabs; *Verify chain* answers in a sentence with the ledger's count.
2. **Northwood `CLM-2026-5855FB8E`, run `2bd08a61`** (rejected): eight rows ending "Sent to a person: Settlement over the $250,000 ceiling: $950,000", "Awaiting human review", "Rejected by Dermot Copps"; the run line reads "Rejected after human review"; the human record has one tab and the comment in the tree.
3. **Northwood `CLM-2026-2FFB0434`, run `67bdf225`** (approved 14 November): "Approved by Dermot Copps" as the eighth row, dated 14 November under rows of 4 November.
4. **Coral Bay `CLM-2026-167527A2`, run `e9566e92`**: the Adjuster row's fixture sentence; its record has no *Instructions sent* tab and says no model was called; the Guardrail row "Failed: cited policy wording the policy does not contain"; the escalation row with two rules.
5. **Background Claimant 01 `CLM-2026-1001`, run `b3e7dc6c`**: four rows ending "Run aborted: the Adjuster has no market range for the claim type Sprinkler leakage".
6. **Short id:** `f23ea4dc` typed in the box loads run 1; `2bd0` (if it matches several) asks for more; `00000000` says no run starts with it.
7. **The dialog:** Escape, Close, a click outside; Tab stays inside; the page behind does not scroll; *Copy record* then a paste into a text editor shows the row.
8. **The 15 November fix, live:** a new Northwood claim submitted and processed, watched to *Awaiting human review*; *Why it went to a person* appears when the run finishes, without a reload. (This adds one claim and one run to the record.)
9. Also read: `/health` `0.10.3`; `GET /api/runs?limit=3` names three claims; the run page's *View audit log* and a claim page's *Audit log* land on the run they name. Azure stays running.

## 8. Anything in the record that contradicts this prompt

- **The prompt calls the Audit page "the one page on the claim's path that still shows what the database stores".** The compare page (`/compare`) also shows stored values (noted in the Prompt 30 report's suggestions); it is not on the claim's path and is not touched here.
- **The agreed mock-up of 13 November is not in the repository.** The plan follows Part 2's description; nothing else records the mock-up.
- **`docs/walkthrough.md`** says "paste/select the run's correlation_id" and names the button "Verify chain (whole ledger)"; `copy/guide.ts` and `guide.test.ts` assert the same label. Both change with D5.
- **The AgentCard's expanded panel** still shows the response as a `JsonBlock` and has its own prompt panel; the prompt says the run page's cards take up the viewer later, so only `extractPrompt` moves (D8).
- **`CLAUDE.md` says React 18+**; `package.json` has React 19.2 since an earlier upgrade. Not this prompt's to change; noted for the next `CLAUDE.md` tidy.
- **The backlog's *Routes still un-surveyed*** still lists *Run Detail* and *Audit*; marked at close-out.
- **`tooltips.verifyChain`** is a production note, not a description of the button; it stays as the ⓘ and the button's own words carry the description.
- **The Prompt 31 report** suggested `human_decision` on run summaries; `RunListItem` carries it, `RunSummary` is unchanged.

## 9. Risks

- Focus management in the hand-rolled dialog is the one piece with browser-specific behaviour; the tests cover the rules and step 7 checks them live.
- The tree over a Guardrail record with long chunk excerpts: the 240-character fold and the `overflow-x: hidden` panel are what keep it inside the dialog; step 4 reads it.
- `correlation_id::text LIKE` cannot use the UUID index; the scan is over `pipeline_started` rows only (one per run; 50-odd on Azure), so it is immaterial at this scale and noted for production.

## 10. Decisions requested

- **D1 One new endpoint, `GET /api/runs` with `limit` and `prefix`**, for the recent-runs list and the short id. *Recommended: yes.*
- **D2 A hand-rolled `Dialog` component** rather than the browser's `<dialog>`, because jsdom cannot exercise `showModal()`. *Recommended: yes.*
- **D3 The tree opens the record's keys and the level beneath them; deeper levels start closed.** *Recommended: yes.*
- **D4 *Copy record* copies the whole row** (number, agent, step, time, hash, payload), pretty-printed as the API served it. *Recommended: yes.* The alternative is the payload alone.
- **D5 The button reads *Verify chain*;** "whole ledger" moves into the result sentence; the Guide and the walkthrough follow. *Recommended: yes.*
- **D6 A person's row reads "Rejected by Dermot Copps"** without the date, which the row's time column carries. *Recommended: yes.*
- **D7 Version `0.10.3`.** *Recommended: yes* (with D1).
- **D8 `extractPrompt` moves to `auditDerivation.ts`** and `AgentCard` imports it, an import-only change to a file the prompt otherwise leaves alone. *Recommended: yes.*

**Optional, clearly beyond the spec:** **O1** a short *Reading the audit log* paragraph in the Guide, after *Reading a run page*, saying what a record is and that the hash chain is verified over the whole ledger. *Recommended: yes.* **O2** the recent-runs list on the Claims page too. *Recommended: no; the Audit page is the place a visitor looks for a run.*
