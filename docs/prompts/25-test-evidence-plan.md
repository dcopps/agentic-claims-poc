> *Plain-language summary of this phase: see [the build story](README.md#entry-25), entry 25.*

# Prompt 25 — Plan: test evidence, one document that shows how the system was tested

**Prompt:** `25-test-evidence.md`. **Scope:** documentation only — no code, no test, no version change. **Output:** `docs/test-evidence.md` in six parts, a backlog entry, one README line, the four close-out appends. **Standard:** the decision register's — plain language first, the engineer's detail below, nothing claimed that the record does not support.

This plan was written after reading every `*-plan.md` testing section, every `*-report.md`, `docs/build-log.md`, `docs/decision-register.md`, `docs/BACKLOG.md`, the test tree and the three workflows. Section 0 lists what that reading found, including the places where the record is thin or disagrees with the prompt; sections 1–7 say what the document will contain and where each statement comes from; section 10 lists the decisions the gate needs.

## 0. What the record holds, and where it is thin or contradictory

| # | Finding | What the document will do |
|---|---|---|
| F1 | The prompt says *65 backend test files*. The tree holds **59** `test_*.py` modules; `backend/tests/` has 63 `.py` files in all, the other four being `conftest.py`, `__init__.py` and the two shared fixture modules `guardrail_replay_fixture.py` and `mcp_fixture.py`. The frontend count of 14 is right. | State 59, say how it was counted, and list the four non-test modules separately. |
| F2 | **Phase 8.5.1 has no plan file** (a point release run from the prompt alone; the archive holds `14-…` prompt and report only). | Its traceability row says "no plan". |
| F3 | **Four plans have no testing section:** Phase 0 (nearest heading is *CI (`.github/workflows/`)*), Phase 9.1 (§7 *Verification* is the deployment check, not tests), Phase 9.2 (none; the report records 382 / 7 and the frontend's 36), Prompt 23 (documentation only; §6 *Verifying every pointer* is a link check). | Those rows say "no testing section" and link the nearest heading, named as such. |
| F4 | **Predicted counts are uneven.** Stated as a total: Phases 1 (~46–50 new), 3 (38 new + 3 gated, 122 → 160), 4 (~40–48), 5 (~45–55 + ~12 frontend), 6 (~30–40 backend, ~25–35 frontend), 7 (~6–8), 8 (~13), 8.2 (~8–10), 8.3 (~10 new, ~4 modified), 8.4 (331 → 335), 8.5 (335 → 338), 8.5.2 (338 unchanged), 8.5.3 (9 new → 347), 8.6 (347 + 16 ≈ 363), 8.6.1 (+6 → 372), 10 (~45 backend, ~14 frontend). Listed per module without a total: Phase 2. No count at all: Phases 0, 9.1, 9.2, 9.2.1, 9.2.2, Prompt 23. | Quote the plan's figure verbatim (ranges stay ranges); write "listed, not totalled" or "no count stated" where that is the case. No reconstruction. |
| F5 | **Mutation proofs in the record:** 8.4 (the four tests run against three connection states; the true bug reproduces 3 fail / 1 pass), 8.5.1 (the old form of the test reinstated, fails), 8.5.3 (nine tests fail with the recording line removed), 8.6.1 (M1–M3, with the finding that the planned sixth test passed with the defect reinstated, so a seventh was added), 9.2.1 (recorded as *what has been observed so far*), 9.2.2 (verifier neutered → 18 fail; old prompt restored → golden-shape test fails), Phase 10 (two: guard comparison → one test fails, eight pass; mount condition → two fail). **Nothing before 8.4.** The word *mutation* in the Phase 6 prompt and plan is TanStack Query's `useMutation`, not a proof. | Rows before 8.4 say "none recorded"; each proof row quotes the report's own sentence. |
| F6 | The build log's Phase 10 heading still reads *"(2 November 2026; deployed verification pending)"* although the entry's body was closed on 4 November (commit `86fa8bf`). The traceability table links to that heading, and no other document links to its anchor yet. | **D1:** correct the heading to *"(2 to 4 November 2026)"* in this prompt's close-out, recorded in the build-log entry as a correction, not a register entry. |
| F7 | **The 18 skipped tests decompose exactly:** 1 embedding end-to-end (`RUN_EMBEDDING_TESTS=1`); 6 single live-model tests gated on `RUN_LLM_E2E_TESTS=1` (Validator, Doc-Parser, Adjuster, Guardrail, pipeline, agent test bench); 8 replay cases (seven fixtures + Coral Bay without the rule engine); 3 MCP end-to-end (`RUN_MCP_E2E_TESTS=1`). **Two of the six live tests (Validator, Adjuster) still require `MISTRAL_API_KEY`:** they exercise the retained Mistral path, which the free tier refuses since R-06, so they cannot pass today even with the keys set. | Part 2 states the decomposition and that fact plainly. No code change. |
| F8 | **Deployed verification history in the build log** (the prompt names the passes; the record also holds the failures and the halt): 14 September 2026 (8.5.2 failed on the Mistral refusal; 8.5.3 passed the audit check), 15 September (8.6 halted at the auto-approve scenario, R-07), 21 September (8.6.1 passed on Render), 1 October (Azure by script, 9.1), 26 October (Azure through the frontend, passed with the R-16 exception), 29 October (Azure frontend passed; Render by script 1 of 3 failed), 30 October (Vercel addendum; then all three surfaces on 9.2.2), 4 November (the connector on Azure, and Render by script). Phase 7 (June 2026) created `scripts/verify-demo-scenarios.py` and holds `docs/verification/phase-7/scenarios.md`. | **D3:** list the passes as asked and, in the same table, the halt and the failed passes with their register entries, because a reader who finds R-04 or R-07 should find them here too. |
| F9 | The two glossaries (decision register and build story) are identical in their fourteen terms except that the build story's *Prompt* carries one extra sentence about the archive sense of the word — a deliberate difference from prompt 23. | New terms go into both, in the same words. |
| F10 | Prompt 23's link checker lived in the scratchpad and was not committed; its counts were reported (207 links, 44 anchors, 41 build-log references). | The same: a scratchpad script, counts in the report. **O2** offers to commit it. |
| F11 | The README's *Azure deployment* paragraph already lists the pass dates and agrees with the build log; the README's *Before a demo* note is the "run before every demo" rule part 4 must cite. | Cite both; do not restate the rule in different words. |
| F12 | `docs/verification/phase-7/scenarios.md` (15 June 2026, 98 lines) is the one earlier evidence file; the README's index links it. | Part 4 points to it as the Phase 7 record. |

## 1. The document, part by part, with its sources

**Front matter.** Title; one paragraph on what the document is and is not (a trace of the record, not an assessment); the date of the fresh run; links to the register, the build story and the build log.

**Part 1 — How testing works here, in plain language** (one page, no code). What an automated test is and why there are several hundred (each guard clause has a test that triggers it; a change that breaks a promise fails a test before it is committed). The four kinds of evidence, each in two or three sentences: the backend tests (against a local database the harness refuses to point at a live host — R-02), the frontend tests (the pages rendered with the service replaced by recorded answers), the replay corpus (recorded model inputs re-sent to the live model, gated, costs money), the deployed verification passes (the three scripted scenarios run on the live installations by a person or a script). A mutation proof, in one paragraph: the guard is deliberately removed, the tests are run and shown to fail, the guard is put back — so the test is known to catch the fault, not merely to pass. CI, in one paragraph: the shared build server runs every check on every push, and since Phase 9.2 a deployment happens only after a green run. **What is not tested automatically, stated plainly:** the model's behaviour outside the gated replay; the path through the real screens in a browser; the shell scripts (syntax-checked only; `shellcheck` is not installed); the Bicep templates (compiled and linted; what-if is run by hand); the two deploy workflows (exercised only by real pushes); the prompts' wording beyond golden-shape tests; the cost of running the live suites. Terms from the glossary used as defined; three terms added (**D2**).

**Part 2 — The test suites as they stand.** Backend: pytest under `uv`, the command, the fresh count, the 18 skipped tests decomposed as in F7, and a table of the 59 modules with one line each (taken from each module's docstring or, where there is none, from its test names — written, not generated). Frontend: Vitest with Testing Library, the command, the fresh count, no skipped tests, and the 14 files with one line each. Both tables name the phase that introduced the file where the record says.

**Part 3 — Traceability, phase by phase.** One row per phase from Phase 0 to Phase 10, including the point releases and Prompt 23 (24 rows), columns exactly as the prompt lists them. The draft table, to be checked cell by cell against the files when the document is written:

| Phase | Plan testing section (anchor) | Count predicted | Count recorded (report) | Mutation proof | Build-log entry |
|---|---|---|---|---|---|
| 0 | none — nearest: *CI (`.github/workflows/`)* | none stated | 7 backend + 2 frontend | none recorded | *2026-05-08 — Phase 0* |
| 1 | *Test surface and pass-rate expectations* | ~46–50 new | 65 / 1 skipped; 2 frontend | none recorded | *Phase 1* |
| 2 | *Testing strategy — concrete recommendation* | listed per module, not totalled | 122 / 2; 2 frontend | none recorded | *Phase 2* |
| 3 | *4. Testing strategy* | 38 new + 3 gated (122 → 160) | 178 / 5; 2 frontend | none recorded | *Phase 3* |
| 4 | *11. Testing strategy (target ~40–48 new tests)* | ~40–48 | 225 / 6 (47 new + 1 gated); 2 frontend | none recorded | *Phase 4* |
| 5 | *9. Testing strategy (target ~45–55 …)* | ~45–55 backend + ~12 frontend | 277 / 6; 13 frontend | none recorded | *Phase 5* |
| 6 | *5. Testing strategy (~30–40 backend, ~25–35 frontend)* | as stated | 311 / 7; 22 frontend | none recorded (F5) | *Phase 6* |
| 7 | *5. Testing / CI / deps* | ~6–8 new | 326 / 7; 22 frontend | none recorded | *Phase 7* |
| 8 | *3. Testing strategy (~13 new/updated)* | ~13 | 330 / 7; 30 frontend | none recorded | *Phase 8* |
| 8.2 | *Testing strategy (~8–10 changed/new)* | ~8–10 | 327 / 7; 30 frontend | none recorded | *Phase 8.2* |
| 8.3 | *Tests (~10 new, ~4 modified)* | as stated | 331 / 7; 36 frontend | none recorded | *Phase 8.3* |
| 8.4 | *6. Test design* and *Test pass-rate target* | 331 → 335 | 335 / 7 | yes — three connection states | *Phase 8.4* |
| 8.5 | *8. Discriminator tests* and *Test pass-rate target* | 335 → 338 | 338 (confirmed in 8.5.1) | none recorded (the guard's refusal was observed, not mutated) | *Phase 8.5* |
| 8.5.1 | no plan file (F2) | — | 338 / 0 / 7 | yes — old form reinstated | *Phase 8.5.1* |
| 8.5.2 | *5. Test strategy* | 338 unchanged | 338 / 7 | none recorded | *Phase 8.5.2* |
| 8.5.3 | *4. Test design* | 9 new → 347 | per the report (to confirm) | yes — nine tests fail | *Phase 8.5.3* |
| 8.6 | *8. Tests* | 347 + 16 ≈ 363 | 366 / 7 | none recorded | *Phase 8.6* |
| 8.6.1 | *5. Part B — tests* | +6 → 372 | 373 / 7 (seven, not six) | yes — M1–M3 | *Phase 8.6.1* |
| 9.1 | none — nearest: *7. Verification* | none stated | 375 / 7 | none recorded | *Phase 9.1* |
| 9.2 | none (F3) | none stated | 382 / 7; 36 frontend | none recorded | *Phase 9.2* |
| 9.2.1 | *Test module — `test_guardrail_replay.py`* | no count stated | 391 / 14 | partial — "what has been observed so far" | *Phase 9.2.1* |
| 9.2.2 | *4. Tests* | no count stated | 429 / 15 | yes — 18 fail; golden-shape | *Phase 9.2.2* |
| 23 | none — documentation only (*6. Verifying every pointer*) | n/a | 429 / 15 unchanged | n/a | *Prompt 23* |
| 10 | *7. Tests (backend)* and *6e. Frontend tests* | ~45 backend, ~14 frontend | 521 / 18; 54 frontend | yes — two | *Phase 10* |

Point releases 0.10.0.1 and 0.10.0.2 are covered inside the Phase 10 row (the report records them), not as rows of their own.

**Part 4 — Model behaviour.** The replay corpus: why it exists (R-16, the 26 October finding; R-17 to R-19 the response), the seven fixtures in a table (run id, where and when recorded, expected verdict — from the fixture files themselves), `scripts/extract-guardrail-replay-fixture.py` as the way a fixture is made, the command (`RUN_LLM_E2E_TESTS=1 uv run pytest backend/tests/test_guardrail_replay.py`), the results before and after 9.2.2 (7 passed / 1 failed → 8 passed, from the 9.2.2 report), the rule that it runs before every demo (the README's *Before a demo*). The deployed verification passes as in F8 with what was checked (the three terminal states, seven audit rows per run, the chain, the recorded provider and model) and the result; the Claude Desktop connector pass of 4 November with its table from the Phase 10 report. The closing paragraph says in plain words that this is a regression harness — it detects a change from recorded behaviour on a small fixed set — not a scored evaluation, and points to the backlog's *Guardrail rule-engine test corpus from more than one model*.

**Part 5 — The user interface's tests.** The 14 files grouped: pages (Claims, Run Detail, Audit, Integrations, Guide), components (ClaimForm, AgentCard, HumanReviewPanel, AgentTestPanel, ui), hooks (useMcpActivity), copy modules (tooltips, guide), App. All render with `fetch` stubbed (Phase 6's D9: no `msw`) and, since Phase 10, with a mock `EventSource`. Named: the Integrations test *renders every tool the backend reports, with its kind*; the copy-module tests. Then the statement that there is no browser-driven end-to-end test, that the real screens are covered by the manual passes in part 4, and that `scripts/verify-demo-scenarios.py` drives the API, not the browser. The backlog entry (section 5 below) is linked.

**Part 6 — CI as independent evidence.** `ci.yml`: trigger (pull requests and pushes to `main`); the backend job's steps in order (Postgres 17 with pgvector as a service, `uv sync`, migrations to head, `ruff`, `mypy backend`, `pytest`, advisory `pip-audit`); the frontend job's (Node 20, `npm ci`, lint, typecheck, `vitest --run`, advisory `npm audit`). The two deploy workflows: `workflow_run` on *CI* completed on `main`, so a red CI skips both; the backend deploys only when the backend paths differ from the deployed image's commit, the frontend always. The Actions page: `https://github.com/dcopps/agentic-claims-poc/actions`. The red period: 15 June to 26 October 2026, the frontend lockfile (R-11, the Phase 9.2 build-log entry); during it the backend job passed on every run and the frontend job failed at `npm ci` before any test ran, so the red runs say nothing about the tests on either side — the frontend tests of that period were run locally and their counts are in the reports; what a red CI did mean is that nothing could have deployed from it, which is why 9.2 fixed it first.

## 2. The fresh run — commands, recorded with the date

Both suites are run once, on the day the document is written, and the tail of each output is pasted into part 2 and the report:

```
uv run pytest -q                      # backend, against agentic_claims_test via .env.test
cd frontend && npm test -- --run      # frontend
```

Local Postgres is accepting connections and `.env.test` is present. The harness's refusal of deployed hosts (R-02) stands; nothing is run against Neon or Azure. No gated suite is run: no `RUN_LLM_E2E_TESTS`, `RUN_EMBEDDING_TESTS` or `RUN_MCP_E2E_TESTS`, so the run costs nothing and the skipped count is the full 18 (**D4**). If either count differs from the Phase 10 report (521 / 0 / 18; 54), the document records the fresh figure and the report explains the difference.

## 3. Verification by script

As prompt 23 did: a scratchpad script that extracts every Markdown link and `#anchor` from `docs/test-evidence.md`, the new backlog entry, the README line and build-story entry 25, resolves relative paths against the repository, and checks each anchor against the GitHub slug of a heading in the target file (lower-case, punctuation dropped, spaces to hyphens — the rule prompt 23 used; headings such as *11. Testing strategy (target ~40–48 new tests)* are the hard cases). Its counts go in the report. Then the anonymisation test (`uv run pytest backend/tests/test_anonymisation.py`) and a grep of the new document for the client name's candidates. Then `uv run python scripts/regenerate-build-story.py` (exit 1 expected, the rewrite committed).

## 4. Glossary additions (D2)

Three terms the plain-language page needs that the fourteen-term glossary lacks, added to both copies in the same words:

- **Automated test.** A small program that runs part of the system with known input and fails if the result is not what was promised. The project has several hundred; they run on every change.
- **Mutation proof.** Showing that a test catches the fault it exists for: the guard is deliberately removed, the test is run and seen to fail, and the guard is put back. Recorded in the report of the phase that did it.
- **Continuous integration (CI).** A shared build server that runs every check — style, types, tests — on every change pushed to the repository. Since Phase 9.2 a deployment to Azure happens only after that run is green.

## 5. Backlog entry (draft)

Under *Future work*, after *Phase 10 follow-ons*:

> ### Browser-driven end-to-end test of the three scenarios
>
> **Gap, recorded by prompt 25 (5 November 2026).** The frontend's 14 test files render pages and components with the API mocked; nothing drives the real screens in a browser. The path a person takes — submit, run, watch the cards fill, open the audit — is covered only by the manual verification passes and by `scripts/verify-demo-scenarios.py`, which drives the API, not the browser.
>
> **Proposal.** A Playwright run of the three scripted scenarios against a deployed frontend: submit each claim through the form, press *Run*, wait for the four cards and the terminal state, open the audit page and confirm seven rows and a green chain. Gated like the replay corpus (`RUN_BROWSER_E2E_TESTS=1` with the frontend URL), never in CI, run before a demo alongside the replay. Adds Playwright as a dev dependency — flagged for the phase that takes it. Not built here.

## 6. README line (draft)

Under *Not an engineer? Start here*, after the sentence naming the two documents:

> A third document, [how the system was tested](docs/test-evidence.md), traces the plan, the tests and the result for every phase.

**O1** also adds `docs/test-evidence.md` to the README's *Documentation index*.

## 7. Close-out

1. Signposts at the top of `25-test-evidence.md`, this plan and the report.
2. `docs/build-log.md`: entry *Prompt 25 — Test evidence (5 November 2026)* — prompt, what was written, the fresh counts, the link-check counts, the glossary additions, the backlog entry, the F6 heading correction if approved; and the F6 correction itself (**D1**).
3. `docs/decision-register.md`: no entry expected (no halt, no deviation); the three glossary terms (**D2**).
4. `docs/prompts/README.md`: the glossary terms; entry 25 — *TL;DR:* "The proof that the system was tested had been spread across twenty-four plans, reports and the build log, each with its own count. This prompt gathered it into one document: what an automated test is, what the suites hold today, which tests each phase planned and delivered, how the model's behaviour is watched, and what is not tested — finished on [weekday, date]." *Technologies:* pytest and Vitest (the two test frameworks), the replay corpus, GitHub Actions. Body of two or three paragraphs; *Technical detail* line with the three files, the build-log entry and the completion source (the report's *Completed at*).
5. `uv run python scripts/regenerate-build-story.py` → table and `README_TLDR.md` rewritten.
6. `README.md` line (section 6).
7. `CLAUDE.md`: *Current Status* (date, Prompt 25 complete, the fresh counts, the backlog entry), the `docs/` tree gains `test-evidence.md`, the *Known debt* line stays.
8. Report `25-test-evidence-report.md`: *Completed at*, files, the fresh run output tails, the link-check counts, deviations, suggestions.
9. Commit and push. No version change.

## 8. Files created or modified

| File | Change |
|---|---|
| `docs/test-evidence.md` | **new** — the document |
| `docs/prompts/25-test-evidence-plan.md` | **new** — this plan |
| `docs/prompts/25-test-evidence-report.md` | **new** — at close-out |
| `docs/prompts/25-test-evidence.md` | signpost line |
| `docs/BACKLOG.md` | the browser end-to-end entry |
| `docs/decision-register.md`, `docs/prompts/README.md` | three glossary terms (D2); entry 25 and the regenerated table |
| `docs/prompts/README_TLDR.md` | regenerated |
| `docs/build-log.md` | entry *Prompt 25*; Phase 10 heading (D1) |
| `README.md` | one line (and the index line, O1) |
| `CLAUDE.md` | status, docs tree |

No source, test, settings, workflow or infrastructure file changes. No dependency. No interface change.

## 9. Risks

- **Counts drift.** A fresh run made today may not match tomorrow's; the document carries its date and command, which is the point.
- **Anchors to long headings.** GitHub's slug for a heading with punctuation and an en dash is easy to get wrong by hand; the script, not the eye, is the check.
- **Length.** Part 2's two tables are 73 rows and part 3 is 24; the plain-language page stays one page by keeping every table below it.
- **Reading cells from 24 reports** is where an error would hide; each traceability cell is read from its file when written, not copied from this plan's draft.

## 10. Decisions requested at the gate

- **D1 — Correct the build log's Phase 10 heading** from *"(2 November 2026; deployed verification pending)"* to *"(2 to 4 November 2026)"* in this close-out. Recommended: yes; no document links to the old anchor.
- **D2 — Add three glossary terms** (*Automated test*, *Mutation proof*, *Continuous integration (CI)*) to both glossaries. Recommended: yes, as drafted in section 4.
- **D3 — Part 4 lists the halt and the failed passes** (14 and 15 September, 29 October's Render failure) in the same table as the passes, each with its register entry. Recommended: yes.
- **D4 — Fresh run of the two suites only; no gated suite.** Part 4 reports the replay corpus's recorded results, not a new replay. Recommended: yes (the prompt asks for counts, and a replay would spend money to confirm a figure already in the 9.2.2 report).
- **D5 — Backlog placement:** the browser end-to-end entry under *Future work*, after *Phase 10 follow-ons*. Recommended: yes.

Optional, clearly beyond the prompt:

- **O1** — the README's *Documentation index* gains the same line.
- **O2** — commit the link checker as `scripts/check-doc-links.py` so prompt 23's and this prompt's verification can be re-run; a small script with the usual tests. Recommended: no for this prompt (documentation only); a backlog line instead.
- **O3** — part 2's backend table says, for each of the 18 gated tests, what it would need to run; already covered by F7 in the text, so recommended: no separate table.

## Approval

**Approved by Dermot, 5 November 2026 (2026-11-05T17:48Z).** D1 to D5 as recommended; O1 yes; O2 and O3 no. Verbatim: *"Approved: D1 to D5 as recommended, O1 yes, O2 and O3 no. Commit the prompt and plan, then write the document."*
