> *Plain-language summary of this phase: see [the build story](README.md#entry-26), entry 26.*

# Prompt 26 — Guide page rewrite

## Why this prompt exists

The repository's About link and the README now send a first-time visitor straight to the app on Azure, and the Guide is the page that tells them what they are looking at. Its opening paragraph describes the project before it says what the system is, it says nothing about the four agents or how a claim is processed, it gives no steps to follow, and its links predate the test evidence document and the fourth view of the architecture diagram.

This prompt rewrites the Guide's text and adds three sections. It is frontend text and layout only: no change to the backend, the agents, the audit chain, or any HTTP or SSE shape. A wider UI phase (Phase 8.7 in `docs/BACKLOG.md`) follows separately; do not start it here.

## What changes

All text stays in `frontend/src/copy/guide.ts`, reviewed as prose, not inline in components. Use the wording below as written unless a fact in it is wrong, in which case say so in the plan and do not correct it silently.

### 1. "What this is" — replace the paragraph

> An agentic insurance claims processor. Four AI agents handle a claim in turn:
>
> - **Doc-Parser** reads the claim and writes a short summary of what happened.
> - **Validator** finds the relevant passages of the policy and decides whether the loss is covered, quoting the passages it relied on.
> - **Adjuster** proposes a settlement figure within the market range for that type of loss, and gives its reasoning.
> - **Guardrail** checks the Adjuster's output for personal data, biased language and references to policy wording that does not exist.
>
> A set of rules then decides the outcome: the claim settles, or it goes to a person for review. Every step is recorded in an audit trail that shows if anything has been altered.
>
> The claims are synthetic and the policy is a short excerpt, so its scope is a prototype's. It is built and run to production standards: deployed on Azure, tested, audited and change-controlled.

### 2. "How it works" — new section, after "What this is"

> **Preparing the policy.** Before any claim arrives, the policy wording is split into twelve short passages. An embedding model turns each passage into a vector, a list of numbers that represents its meaning. The passages and their vectors are stored in the database.
>
> **Finding the relevant wording.** When a claim is processed, the same embedding model turns the claim's description into a vector. The database compares it with the stored vectors and returns the three passages closest in meaning. The Validator is given those three passages and nothing else, so its decision can only cite wording it was actually shown. The same model must be used for both steps, or the comparison would be meaningless.
>
> **Deciding.** The Adjuster's figure and the Guardrail's findings are tested against the escalation policy, a configuration file kept apart from the program code. A settlement over $250,000, low confidence from the Validator or Adjuster, or a Guardrail failure sends the claim to a person. Otherwise it settles.
>
> **Recording.** Each step writes a row to the audit trail: what the agent was asked, what it answered, and which rules fired. Each row carries a SHA-256 hash, a short code calculated from the row's contents and the hash of the row before it. Changing or removing any row breaks every hash after it. One click checks the whole trail.
>
> **Asking it questions.** An AI assistant such as Claude can connect to the system and ask why a claim settled or escalated. The answer is read from the audit trail, never worked out afresh.

Verify three facts before using this text, and report each in the plan: the number of passages the indexer produces from `backend/data/sample_policy.txt` (the build log says twelve; nothing in code or tests confirms it); the retrieval count (`RetrievalSettings.top_k`); and that the rules named match `backend/app/escalation/policy.yaml` today, including the hard rules the paragraph leaves out. If a number differs, use the true one.

### 3. "Try it" — new section, before "The three scenarios"

Five numbered steps, using the button and link labels exactly as the interface shows them: load a scenario on the Claims page; submit it; start the pipeline; read the run page; open the audit log and verify the chain. Then one sentence each on two further things a visitor can do: decide an escalated claim in the human review panel, and re-process a claim under a variant and compare the two runs. Draft the wording in the plan for approval; keep each step to one sentence.

### 4. "The three scenarios" — one addition

Coral Bay's text says the Guardrail finds the Adjuster citing an endorsement the policy does not contain. That citation is planted by the demo fixture so the scenario behaves the same every time, and the audit trail records `demo_fixture: true`. Add one sentence saying so in plain words.

### 5. "Reading a run page" — one wording change, here and on the card

"Refused claims" reads, on a page about insurance claims, as refused insurance claims. Change the term to "refused objections" in this paragraph and in the Guardrail card's label, with the tests that assert it. The audit keys (`llm_flags_discarded`) and every payload are unchanged.

### 6. A line about data

One sentence, placed where a visitor will see it before the form: the claims are synthetic and the app is open to anyone with the address, so do not enter real personal details.

### 7. Links

- Add: *How the system was tested* → `docs/test-evidence.md`.
- Change the architecture diagram's description to: "the production design in four views, the last marking what is built and what stands in".
- Keep the build story, the decision register and the repository.
- No link to a Policy page: that page does not exist yet and belongs to the UI phase.

## One decision to put in the plan

A comment in `guide.ts` says the opening paragraph is the glossary's definition of the system, so that the Guide, the build story and the decision register say the same thing. The new wording breaks that match. Recommended: change the glossary entry *The system* in both documents to the first and last paragraphs of the new "What this is" text (the agent list stays on the Guide only), regenerate with `scripts/regenerate-build-story.py`, and update the comment. Say in the plan whether any test enforces the match and what the alternative costs.

## Plan first

Produce `docs/prompts/26-guide-page-rewrite-plan.md` covering: the three fact checks; the "Try it" draft; the Coral Bay sentence and the data sentence, drafted; the glossary decision; the files touched (`guide.ts`, `GuidePage.tsx`, the Guardrail card, their tests, the two glossaries); the tests added or changed, in the existing style; the version (a point release is expected; say which); and confirmation that nothing outside the frontend and the two documents changes. Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`: plan first, text in the copy module, tests in the existing style, British English, no client name anywhere.
- Voice: plain and direct. No superlatives, no self-assessment, no scare quotes. Prefer "the system"; "prototype" appears only in the one sentence above, about scope.
- No change to the backend, the agents, the audit chain, settings, or any HTTP or SSE shape.
- Deployed verification with Dermot present: the Guide read on the Azure frontend after the push deploys it. `scripts/azure-start.sh` first if Azure is parked; check its state.

## Close-out

Build-log entry *Prompt 26*; build-story entry 26 with TL;DR and Technologies; signposts on this file, the plan and the report; the regeneration script; a decision-register entry only if a halt or deviation occurs; `CLAUDE.md` status; commit and push.

## Archive

Pre-saved at `docs/prompts/26-guide-page-rewrite.md`; plan and report alongside.
