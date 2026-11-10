> *Plain-language summary of this phase: see [the build story](README.md#entry-26), entry 26.*

# Prompt 26 — Report: Guide page rewrite

**Prompt:** `26-guide-page-rewrite.md`. **Plan:** `26-guide-page-rewrite-plan.md` (approved 10 November 2026: D1–D7 as recommended, O1 and O2 no). **Version:** `0.10.0.2 → 0.10.0.3`, live on both stacks. **Completed at:** 2026-11-10T13:10Z. **Status:** complete; the Guide read on the Azure frontend by Dermot and confirmed as intended.

## What was built

Frontend text and layout only. `frontend/src/copy/guide.ts` was rewritten around the prompt's wording: *What this is* as an introduction, a list of the four agents, the rules-and-audit sentences and the one paragraph about scope; a new *How it works* in five parts (preparing the policy, finding the relevant wording, deciding, recording, asking it questions); a new *Try it* with five one-sentence steps and two further sentences, each written as segments of plain text and interface labels so the page renders the labels in `<em>` and the tests can compare them as a list; the Coral Bay scenario's sentence on the planted citation; *refused objections* in place of *refused claims* on the Guide and on the Guardrail card (`AgentCard.tsx`, test id `refused-objections`); five links, adding *How the system was tested* and describing the diagram as four views; and `dataNotice`, rendered on the Claims page above the form. `GuidePage.tsx` renders six cards. The glossary entry *The system* in `docs/decision-register.md` and `docs/prompts/README.md` now reads as the Guide's first and last paragraphs (D1), and the comment in `guide.ts` says so.

## The fact checks (plan §0)

All seven stand as the plan recorded them. The chunker produces 12 passages from the sample policy (2,388 tokens; run on 10 November with the bge-small tokeniser); `top_k` is 3 with no deployed override; the rules named match `policy.yaml`, and the three hard rules the prompt's paragraph left out are now named in one sentence (D3); the Validator *names* its passages rather than quoting them, and the text says so (D2).

## Tests

Frontend **57 passed** (54 before: the one-screen budget test removed under D4; the copy tests split and extended to seven; one Claims-page test added). ESLint, `tsc -b`, Prettier and `vite build` clean. Backend **521 passed, 0 failed, 18 skipped** on 10 November 2026 at about 12:36Z, `ruff` clean; nothing under `backend/` changed, the run confirms the version bump and the anonymisation guard over the edited documents.

**Mutation proof (applied, observed, reverted).** (1) The *Submit Claim* label in `guide.ts` changed to *Submit claim*: `gives five one-sentence steps that use the interface’s own labels` fails (`expected [ 'Submit claim' ] to deeply equal [ 'Submit Claim' ]`) and the `GuidePage` render test fails with it; six pass. (2) The first demo-button label shortened to *Auto-approve ($85k water)*: the same copy test fails against the labels imported from `fixtures/demoClaims.ts`; six pass. Both labels restored; the full suite 57 passed again.

## Deployed verification, 10 November 2026, Dermot present

Commit `af7716e`: CI run 42817021984 green; *Deploy backend (Azure)* 42817261607 and *Deploy frontend (Azure Static Web Apps)* 42817261597 both green. The backend rolled because `pyproject.toml` and `uv.lock` are backend paths (plan D5); Azure `/health` returned `{"status":"ok","version":"0.10.0.3"}`. The deployed bundles were fetched from the Static Web App (`index-DNoTlwCO.js`) and from Vercel (`index-BohtHaaN.js`): each contains *Try it*, *How the system was tested*, *twelve short passages*, the data notice, *demo_fixture: true* and *Refused objections* once, and *refused claims* not at all. Dermot read the Guide at `https://delightful-beach-009db650f.5.azurestaticapps.net/guide` and the Claims page and confirmed: *"The Guide reads as intended."*

Azure was **not** parked at the close: Dermot's instruction, because Prompt 27 follows directly. State at the start of the day, read-only: no replicas, `minReplicas` 0, Postgres `Ready`.

## Findings and deviations from the plan

- None from the plan as approved. The "Try it" steps were stored as segment arrays rather than the `before` / `labels` / `after` shape the plan implied; the test and render contract (one sentence, labels in order) is the same.
- Prettier re-wrapped five of the edited files before the commit; ESLint had passed before and after.
- The first background watch of CI returned before the run had registered with GitHub and reported nothing; the second watch, by run id, saw CI and both deploys to completion.

## Interface-stability events

None. No HTTP or SSE shape, audit key, setting, agent prompt or database column changed. `llm_flags_discarded` is still what the Guardrail card reads; only its label changed.

## Suggestions (not in scope)

- O1 from the plan: a backend test pinning the sample policy to 12 chunks, so the Guide's "twelve" has a guard (one line for the backlog).
- Phase 8.7 should re-read *Try it* after any label change; only the three demo-button labels are guarded by import, the others by string.
- The glossary match is still enforced only by a comment (O2 declined).
