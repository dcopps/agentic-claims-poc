> *Plain-language summary of this phase: see [the build story](README.md#entry-25), entry 25.*

# Prompt 25 — Test evidence: one document that shows how the system was tested

## Why this prompt exists

The system has been tested throughout, but the proof is spread across the record: a *Testing strategy* section in each phase plan, a pass count in each report and build-log entry, 65 backend test files, 14 frontend test files, mutation proofs described in prose, a replay corpus, and the GitHub Actions history. A reader who asks "how do I know this was tested?" has to know where to look. A reviewer from a regulated environment expects a single document that traces what was planned, what was built to test it, and what the result was.

This prompt produces that document. It is documentation only: no code changes, no version change, no change to any test. The standard is the one set by `docs/decision-register.md`: plain language first, the engineer's detail below, nothing claimed that the record does not support.

## What to produce

`docs/test-evidence.md`, with these parts.

### 1. How testing works here, in plain language

One page for a reader who is not an engineer. Cover: what an automated test is and why there are hundreds of them; the difference between the backend tests, the frontend tests, the replay corpus and the deployed verification passes; what a mutation proof is (the guard is removed and the tests are shown to fail, so the test is known to catch the fault); what CI is and why a deployment only happens after a green run; what is **not** tested automatically, stated plainly. Use the glossary terms from the decision register where they fit; add to that glossary only if a term is missing.

### 2. The test suites as they stand

For the backend and the frontend separately: the framework, how to run it, the current count (passed, failed, skipped), what the skipped tests are and why they are skipped, and a table of every test file with a one-line statement of what it guards. The counts are taken from a fresh run made for this prompt, not copied from the last report; record the command and the date.

### 3. Traceability: plan → tests → result, phase by phase

One table row per phase, from Phase 0 to Phase 10, with: the plan file and its *Testing strategy* section (link to the heading); the test files that phase added or changed; the count the plan predicted; the count the report recorded; the mutation proof, if the phase had one, with the sentence from the report that describes it; and the build-log entry. Where a phase had no testing section, or the record is silent on a count, the row says so. Do not reconstruct a number the record does not contain.

### 4. Model behaviour: the replay corpus and the deployed verification passes

Describe the Guardrail replay corpus (`backend/tests/fixtures/`, `test_guardrail_replay.py`, `scripts/extract-guardrail-replay-fixture.py`): why it exists (the October drift incident, R-entries in the decision register), what each of the seven fixtures is, how it is run (`RUN_LLM_E2E_TESTS=1`), its result before and after Phase 9.2.2, and the rule that it is run before every demo. Then the deployed verification passes: each dated three-scenario pass recorded in the build log (Render by script, Azure by script and through the frontend, Vercel through the frontend, the Claude Desktop connector on 4 November), with what was checked and the result. State plainly that this is a regression harness, not a scored evaluation, and point to the backlog entry on a rule-engine corpus from more than one model.

### 5. What the user interface's tests do and do not cover

Say what the 14 frontend test files exercise (components and pages rendered with the API mocked; the catalogue test that checks every backend-reported tool renders; the copy-module tests) and say plainly that there is no browser-driven end-to-end test: the path through the real screens is covered by the manual verification passes in part 4 and by `scripts/verify-demo-scenarios.py`, which drives the API, not the browser. Record this as a gap in `docs/BACKLOG.md` with a one-paragraph proposal (a Playwright run of the three scenarios against a deployed frontend, gated like the replay corpus), without building it.

### 6. CI as independent evidence

Describe the three workflows in `.github/workflows/`: what `ci.yml` runs, what the two deploy workflows gate on, and where a reader finds the run history. Include the link to the Actions page. Note the period during which CI on `main` was red (15 June to 26 October 2026, the frontend lockfile, per the build log) and what it did and did not mean for the backend tests during that time, because a reader who finds those red runs should find the explanation here first.

## Method

- Read the record before writing: every `*-plan.md` *Testing strategy* section, every `*-report.md`, `docs/build-log.md`, `docs/decision-register.md`, `docs/BACKLOG.md`.
- Run both suites and record the counts, the command and the date.
- Verify every link and anchor by script, as prompt 23 did.
- Anonymisation scan.
- Voice: plain, direct, British English; no superlatives, no self-assessment ("robust", "comprehensive", "rigorous"); state the fact and let the reader judge.

## Close-out

Signpost at the top of this file and of the plan; register entry only if a halt or deviation occurs; build-log entry *Prompt 25*; build-story entry 25 in `docs/prompts/README.md` with TL;DR and Technologies; `uv run python scripts/regenerate-build-story.py`; `README.md` gains one line under *Not an engineer? Start here* pointing at the new document; `CLAUDE.md` status updated; commit and push. No version change.

Plan first: write `docs/prompts/25-test-evidence-plan.md` covering the document's outline, the sources for each part, the fresh-run commands, and anything in the record that is missing or contradictory, then wait for confirmation before writing the document.

## Archive

Pre-saved at `docs/prompts/25-test-evidence.md`; plan and report alongside.
