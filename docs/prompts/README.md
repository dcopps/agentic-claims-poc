# The build, phase by phase, in plain language

## What this document is

This prototype is a working demonstration of insurance claims handling assisted by artificial intelligence: software that reads a claim, checks it against the policy, proposes a settlement, checks that proposal, and either settles or hands the claim to a person, with every step recorded in a tamper-evident audit trail. It was built in numbered phases, each driven by a written prompt, each planned and approved before any work began, and each reported on afterwards. This document tells that story in order, one entry per phase, for a reader who is not an engineer and does not want to read code. Each entry opens with a short paragraph labelled *TL;DR*, three or four plain sentences in a simpler voice than the rest, for the reader who has thirty seconds; then one bold line labelled *Technologies*, naming in plain words only the technologies the phase introduced or depended on; then says what the phase set out to do, what it delivered, and anything notable it found on the way; and ends with one line pointing to the engineer's record. The table at the top collects the TL;DR paragraphs so the whole build can be read at a glance. Where it helps the reader, an entry may look forward to a later phase. The incidents and decisions along the way have their own plain-language record, [the decision register](../decision-register.md), and entries here link to it where they belong together.

## Glossary

A handful of project terms recur throughout. They are defined here once, by what they do, and used consistently below.

**The prototype.** The working system this project built: software that reads an insurance claim, checks it against the policy wording, proposes a settlement figure, checks that proposal, and either settles the claim or sends it to a person.

**Agent.** One of the four specialised pieces of software in the prototype, each with a single job, each calling a language model to do it.

**Doc-Parser, Validator, Adjuster, Guardrail.** The four agents. The Doc-Parser reads the claim. The Validator decides whether the policy covers the loss. The Adjuster proposes a settlement figure and gives its reasons. The Guardrail checks the Adjuster's reasons for leaked personal data, for bias, and for references to policy wording that the policy does not contain.

**Orchestrator.** The part of the prototype that runs the four agents in order and applies the escalation rules at the end.

**Language model**, or **the model**. The external artificial-intelligence service each agent calls. The prototype uses Anthropic's Claude models. An alternative provider, Mistral, is kept available as a switch.

**Prompt.** The written instructions an agent sends to the model with each request. There are two kinds: the fixed instructions that define the agent's job, and the per-claim content that changes every time. The word is also used, in this archive, for the written instruction that drove each phase of the build; the context makes clear which is meant.

**Audit trail.** The tamper-evident record of everything each run did: every agent's input, its output and its call to the model, chained together so that any later alteration is detectable. The project's rule is that the audit trail alone must be enough to explain any past decision.

**Human review**, or **escalation**. The outcome in which the prototype stops and hands the claim to a person, recording which rule sent it there.

**The three scripted scenarios.** The three synthetic claims that every verification runs. A water-damage claim that should settle automatically. A fire claim large enough that a person must see it. And a claim whose reasoning cites a policy endorsement that does not exist, which the Guardrail must catch.

**Deployed stacks.** The two live installations of the same code: the original, hosted on Render, Vercel and Neon, which is the demonstration's home; and the Azure installation added in Phase 9.

**Approval gate.** The point in every phase where the written plan is put to Dermot, the person accountable for the project, and nothing is built until he approves it. Decisions taken there are recorded in the plan.

**Replay.** Re-sending a recorded prompt to the model to see whether its answer has changed. Since Phase 9.2.1 a set of recorded runs is replayed before every demonstration.

The names of the three synthetic claimants, Harborline, Northwood and Coral Bay, are invented. No real client is named anywhere in this project.

## The build, phase by phase

Each entry links to the three files that drove and recorded the phase: the prompt that asked for it, the plan that was approved, and the report written afterwards.

<a name="entry-01"></a>
### 01 — Phase 0: a repository that runs, tests itself and deploys

**TL;DR:** Before any real work, the project needed a shell that already worked end to end. This phase built that shell: a tiny web service, a web page that reports whether the service is up, and automatic checks that run every time something changes. Nothing in it handles a claim yet. It was finished and published on 8 May 2026.

**Technologies:** Python and FastAPI for the service, React with Vite and Tailwind for the page, PostgreSQL with the pgvector extension for the database, uv for Python packaging, GitHub Actions for the automatic checks, Render for hosting.

The first phase set out to create the empty but working skeleton that every later phase would build on: a web service that answers a health check, a web page that shows whether the service is up, a settings mechanism that refuses malformed configuration rather than guessing, a script that prepares a local database, and automated checks that run on every change. It delivered all of that, with nine passing tests, and pushed the result to a new public repository on 8 May 2026. Two things were notable. The plan was approved with three answers and three amendments from Dermot, one of which told the work to stop and report if the database tooling did not install cleanly; it did not, because the add-on the project needs was not packaged for the database version first chosen, so the work stopped, reported, and resumed on the next version with approval. And the very first automated check on the shared build server failed because a dependency list generated on a Mac lacked entries the Linux server needed; the list was regenerated and the check went green. The same class of problem would return, unnoticed for months, in Phase 9.2.

*Technical detail:* prompt [`01-phase-0-repository-scaffold.md`](01-phase-0-repository-scaffold.md), plan [`01-phase-0-repository-scaffold-plan.md`](01-phase-0-repository-scaffold-plan.md), report [`01-phase-0-repository-scaffold-report.md`](01-phase-0-repository-scaffold-report.md); build log, entry *2026-05-08 — Phase 0: Repository scaffold*.

<a name="entry-02"></a>
### 02 — Phase 1: the database, the audit trail and the policy text

**TL;DR:** This phase built the places where everything gets stored. The most important of them is the audit trail, a record of every step the system takes that is designed so that nobody can quietly change it afterwards. It also wrote a short, made-up insurance policy for the system to read, and nine made-up claims to test it with. Finished the same day as the first phase, 8 May 2026.

**Technologies:** PostgreSQL with pgvector for storage and vector search, Alembic for versioned schema changes, psycopg for database access, SHA-256 hashing for the audit chain, the BGE small embedding model through sentence-transformers for indexing the policy text, Neon as the hosted database.

This phase set out to lay down everything the agents would later write to and read from: a versioned database with three tables for claims, audit entries and indexed policy text; a settings structure with named sections for the database, the models, the embedding, observability and escalation thresholds; the audit trail itself, in which each entry is hashed and chained to the one before so that any later alteration is detectable; a two-to-three-page generic commercial-property policy excerpt broken into passages and indexed for retrieval; and a generator of nine synthetic claims, three of them the scripted scenarios. It delivered all of it, and the shared build server gained a real database so the new tests run against the same kind of system the prototype will use. Dermot approved the plan as proposed across its seven headline decisions. Two things were notable. The policy excerpt was written to say explicitly that a flood endorsement is not attached, which is the hook the guardrail scenario later depends on. And the audit trail's canonical form had a quiet flaw during the build: the library step that prepared an entry for hashing was silently converting the very number types the design meant to refuse, so the refusal never fired; the preparation was reordered so the check sees the raw values first. Four smaller surprises in the tooling were fixed and recorded in the same way.

*Technical detail:* prompt [`02-phase-1-data-layer.md`](02-phase-1-data-layer.md), plan [`02-phase-1-data-layer-plan.md`](02-phase-1-data-layer-plan.md), report [`02-phase-1-data-layer-report.md`](02-phase-1-data-layer-report.md); build log, entry *2026-05-08 — Phase 1: Data layer and settings infrastructure*.

<a name="entry-03"></a>
### 03 — Phase 2: the first agent, and the door every model call goes through

**TL;DR:** This phase connected the system to the outside AI models for the first time, through a single doorway that every future agent would also use, so that each call is logged the same way and the provider can be swapped without rewriting the agents. It then built the first agent, the Validator, which finds the relevant passages of the policy and asks the model whether the loss is covered. Every call writes to the audit trail, including the ones that fail. Finished on 11 May 2026.

**Technologies:** Anthropic's Claude and Mistral's models as the two providers behind one gateway, pgvector similarity search for retrieving policy passages, Markdown files for the externalised prompts, structured JSON logging for every model call.

This phase set out to build the gateway through which every agent talks to a language model, with two providers behind it; a logger that writes one structured record per model call, with the cost when the price is known; a loader that keeps every prompt in a plain text file outside the code, so that what the model is told can be read and reviewed without reading the program; and the Validator, the agent that turns the claim narrative into a search, fetches the three most relevant passages of the policy, asks the model for a coverage verdict, and refuses any verdict that cites a passage it was not shown. It delivered all of that with 59 new tests, and one real call to the Mistral service confirmed the whole chain worked end to end. Dermot approved the plan as proposed. Two design rules that shaped the rest of the build were fixed here: the model's role and format instructions always travel separately from the per-claim content, and an audit entry is written on every exit path, so a failed call leaves as full a record as a successful one. The surprises were all in the tooling, six of them, including two places where the vendor libraries differed from their documentation; each was fixed and noted.

*Technical detail:* prompt [`03-phase-2-llm-gateway-and-validator.md`](03-phase-2-llm-gateway-and-validator.md), plan [`03-phase-2-llm-gateway-and-validator-plan.md`](03-phase-2-llm-gateway-and-validator-plan.md), report [`03-phase-2-llm-gateway-and-validator-report.md`](03-phase-2-llm-gateway-and-validator-report.md); build log, entry *2026-05-11 — Phase 2: LLM Gateway and Validator agent*.

<a name="entry-04"></a>
### 04 — Phase 3: the other three agents

**TL;DR:** With the first agent working, this phase built the remaining three. One reads the claim into structured fields. One proposes a settlement figure, and is held inside a published range for that kind of loss so it cannot invent a number. One checks the proposal for leaked personal data, bias and references to policy wording that is not there, and fails the claim if it finds any. Finished on 11 May 2026, with all four agents now writing to the audit trail.

**Technologies:** Claude Haiku for reading claims and for the Guardrail, Mistral Large for the settlement proposal, a static market-data table in YAML for the settlement ranges, regular expressions for the Guardrail's deterministic checks.

This phase set out to complete the set of agents on the plumbing laid in Phase 2. The Doc-Parser reads the claim narrative into a fixed set of fields. The Adjuster looks up the market range for the kind and severity of loss, asks the model for a figure inside it with reasons, and refuses any figure outside it rather than quietly correcting it. The Guardrail runs a fixed set of pattern checks first, for personal data, for protected characteristics, and for policy citations absent from the retrieved passages, then asks the model for anything subtler, and fails the claim if either finds anything; it cannot pass a claim that carries a flag. Each agent keeps its prompts in plain text files and writes a full audit entry on every path. It delivered all of that with 56 new tests. Dermot approved the plan as proposed. One finding is worth recording because it set a pattern: the first version of the bias check matched the word "age" inside "damage" and failed a clean claim, so the check was changed to match whole words only. The build also noticed, and would later rely on, the rule that the Adjuster's reasoning must not cite the policy at all, since coverage is the Validator's question.

*Technical detail:* prompt [`04-phase-3-remaining-agents.md`](04-phase-3-remaining-agents.md), plan [`04-phase-3-remaining-agents-plan.md`](04-phase-3-remaining-agents-plan.md), report [`04-phase-3-remaining-agents-report.md`](04-phase-3-remaining-agents-report.md); build log, entry *2026-05-11 — Phase 3: Remaining agents (Doc-Parser, Adjuster, Guardrail)*.

<a name="entry-05"></a>
### 05 — Phase 4: the agents become a pipeline, and the escalation rules are written down

**TL;DR:** Until now the four agents worked alone. This phase connected them into one run, from reading the claim to a final outcome, under a single reference number that ties every step together in the audit trail. It also wrote the rules that decide when a claim must go to a person, in a plain configuration file rather than in code, so anyone can read them. Finished on 14 June 2026.

**Technologies:** a YAML policy file for the escalation rules, Server-Sent Events for streaming progress to the browser, the asyncio event queue for delivering those events.

This phase set out to wire the four agents into one end-to-end run and to add the escalation engine: four hard rules that always send a claim to a person (a failed Guardrail check, a watch-listed claim type or claimant, a cross-border claim) and three threshold rules (a settlement above two hundred and fifty thousand dollars, or either the Validator or the Adjuster being insufficiently confident). Any one rule firing is enough. It also exposed a way to start a run and a way to watch its progress live, and it fixed how failures end: a failure in the first three agents aborts the run; a failure in the Guardrail sends the claim to a person, because that check must fail safe. It delivered all of that with 47 new tests, and the three scripted scenarios ran end to end for the first time. Dermot approved the plan with one amendment at the gate: the word "and" was removed from the list of phrases that mark a claim as cross-border, because it would have caught place names such as Trinidad and Tobago. Notable along the way: the thresholds now lived in two places, the earlier settings and the new policy file, and the record says plainly which one is authoritative.

*Technical detail:* prompt [`05-phase-4-pipeline-orchestrator.md`](05-phase-4-pipeline-orchestrator.md), plan [`05-phase-4-pipeline-orchestrator-plan.md`](05-phase-4-pipeline-orchestrator-plan.md), report [`05-phase-4-pipeline-orchestrator-report.md`](05-phase-4-pipeline-orchestrator-report.md); build log, entry *Phase 4 — Pipeline Orchestrator*.

<a name="entry-06"></a>
### 06 — Phase 5: a claim is recorded before anything runs, and any run can be replayed

**TL;DR:** This phase separated two things that had been one: submitting a claim, and processing it. A claim is now saved first and processed later, as it would be in a real insurer. It also made every past run reconstructible from the audit trail alone, and added a way to re-run a claim with a different setting and compare the two outcomes side by side. A first, plain web interface arrived with it. Finished on 14 June 2026.

**Technologies:** React for the first working interface, the browser's built-in event stream for live progress, a YAML registry for the named run variants.

This phase set out to decouple submission from processing, to record the claim's status as the run moves through the agents, to add named variants (for example a stricter Validator) that can be chosen for a replay, to reconstruct any past run purely from the audit trail, and to expose runs and comparisons through the interface. It delivered all of that with 63 new tests. Dermot approved the plan with two amendments at the gate, both of which strengthened the audit trail: the Adjuster's full reasoning is recorded, not an excerpt, because the audit trail alone must be enough to explain any past decision; and the Validator's audit entry records the provider that was actually used rather than a fixed label, so that a run on a substitute provider is recorded truthfully. That second amendment is also what makes the project's third-party substitutability argument checkable. Notable along the way: the brief assumed a front-end library that was not yet installed, and the phase proceeded without it rather than add a dependency unasked.

*Technical detail:* prompt [`06-phase-5-decoupling-and-replay.md`](06-phase-5-decoupling-and-replay.md), plan [`06-phase-5-decoupling-and-replay-plan.md`](06-phase-5-decoupling-and-replay-plan.md), report [`06-phase-5-decoupling-and-replay-report.md`](06-phase-5-decoupling-and-replay-report.md); build log, entry *Phase 5 — Decoupling and Replay*.

<a name="entry-07"></a>
### 07 — Phase 6: an interface a person can work in

**TL;DR:** This phase turned the plain interface into the one the demonstration uses: separate pages for claims, for a live run with each agent's card filling in as it finishes, for the audit trail with a button that checks the whole chain has not been tampered with, for a person to approve or reject an escalated claim, and for trying each agent on its own. Finished on 14 June 2026.

**Technologies:** React Router for the pages, TanStack Query for fetching and caching server data, a small design system of shared components and tokens, a second database migration.

This phase set out to polish the Phase 5 interface into a routed application with a consistent design, live pipeline visualisation, an audit viewer with chain verification, a human-review panel and an agent test bench, together with the server endpoints those pages need. It delivered all of that with 34 new server tests and a rebuilt set of interface tests. Dermot approved the plan as written with two notes for the report: the chain-verification wording in the interface must say it checks the whole ledger, not one run; and the review panel assembles its evidence from the audit trail. Two things were notable. A person rejecting a claim needed a terminal state the database did not yet allow, so the schema gained it, and the audit trail gained a "human" actor so that a person's decision is recorded with the same rigour as an agent's. And the test bench needed to try an agent without writing to the audit trail, which was given its own path rather than a switch on the real one, so the real path stayed untouched.

*Technical detail:* prompt [`07-phase-6-frontend-polish.md`](07-phase-6-frontend-polish.md), plan [`07-phase-6-frontend-polish-plan.md`](07-phase-6-frontend-polish-plan.md), report [`07-phase-6-frontend-polish-report.md`](07-phase-6-frontend-polish-report.md); build log, entry *Phase 6 — Frontend Polish (+ supporting backend endpoints)*.

<a name="entry-08"></a>
### 08 — Phase 7: ready to show, and the governance documents

**TL;DR:** This phase made the prototype presentable and wrote the documents that explain how it is governed: how changes are classified and approved, which outside providers it depends on and how each could be replaced, and the reasons behind its main design choices. It also made the third scripted scenario, the one where the Guardrail must catch an invented endorsement, reproducible every time. Finished on 15 June 2026.

**Technologies:** a deterministic demo fixture in place of a live model call for one scenario, an automated test that scans every shipped file for a forbidden client name, a reference pipeline definition for Azure DevOps, a verification script that runs the three scenarios against a live deployment.

This phase set out to expand the README to its final form, to write the change-governance document, the third-party register, the design-decisions record and the walkthrough, to add the production pipeline reference, and to close one gap in the demonstration: the guardrail scenario depended on a live model happening to cite a made-up endorsement, which it did not do reliably. It delivered all of that with 15 new tests. The guardrail scenario now uses a fixed, pre-written Adjuster output that names an endorsement the policy does not have, and the audit trail records openly that a fixture was used rather than a model call, so the convenience is visible rather than hidden. Dermot approved the plan as written, with one gate decision worth recording: he would run a one-time manual search for the real client's name before the first public push, and the new automated scan would be the standing guard thereafter. That scan has run on every change since.

*Technical detail:* prompt [`08-phase-7-demo-polish-and-documentation.md`](08-phase-7-demo-polish-and-documentation.md), plan [`08-phase-7-demo-polish-and-documentation-plan.md`](08-phase-7-demo-polish-and-documentation-plan.md), report [`08-phase-7-demo-polish-and-documentation-report.md`](08-phase-7-demo-polish-and-documentation-report.md); build log, entry *Phase 7 — Demo Polish and Documentation*.

<a name="entry-09"></a>
### 09 — Phase 8: six fixes from the first rehearsal

**TL;DR:** A rehearsal of the demonstration found six things that got in the way, and this phase fixed them in one pass. The most visible was that the live run page was opening only after the run had finished, so nobody saw the agents work. The most consequential for later was a first attempt to stop the Guardrail treating the Adjuster's own market vocabulary as a policy citation, by telling it so in its instructions. Finished on 15 June 2026.

**Technologies:** no new ones; changes to the React pages and to one agent's instructions.

This phase set out to fix the six rehearsal findings: the run page must open before the run completes so the agents can be watched; a page asked for data before it exists must wait gracefully rather than error; each agent's card shows that it is running, with an expected duration; the three scenario narratives state their dollar figures in words so the Doc-Parser does not read zero; the Guardrail's instructions say that market-data vocabulary is settlement framing and not a policy citation; and a run that fails to start, or aborts mid-way, shows an error banner rather than nothing. It delivered all six with 12 new tests. Dermot approved the plan as written and asked that the reasoning behind three design choices be carried into the report, where it is. The Guardrail instruction, fix number five, deserves a forward look: it worked for the model in use at the time, and would turn out, in October, to be exactly the kind of fix that does not survive a change in the model's behaviour. Phases 9.2.1 and 9.2.2 tell that story.

*Technical detail:* prompt [`09-phase-8-demo-polish-fixes.md`](09-phase-8-demo-polish-fixes.md), plan [`09-phase-8-demo-polish-fixes-plan.md`](09-phase-8-demo-polish-fixes-plan.md), report [`09-phase-8-demo-polish-fixes-report.md`](09-phase-8-demo-polish-fixes-report.md); build log, entry *Phase 8 — Demo Polish Fixes from Rehearsal Discoveries*.

<a name="entry-10"></a>
### 10 — Phase 8.2: the claim record is the source of truth, and the model only summarises

**TL;DR:** The first agent had been asked to pull dates, amounts and places out of the claim's free text, and the model kept filling in placeholders that broke the run. This phase stopped asking it to. The structured facts now come straight from the claim as recorded, and the model is used only for what it is good at: a short summary of the narrative. The audit trail says so on every run. Finished on 15 June 2026.

**Technologies:** no new ones; a change of design in one agent and its instructions.

This phase set out to refactor the Doc-Parser after a rehearsal discovery: the model reliably defaulted the structured fields to placeholder values that failed validation and aborted the pipeline, and an earlier attempt to fix that by rewriting its instructions had not moved it. The architectural answer was to take the structured fields from the claim record, which already holds them, and to ask the model for a narrative summary only. The audit entry records that the fields came from the record. It delivered that with the agent's tests rewritten for the new contract. Dermot approved the plan as written, resolving one open question at the gate: a field the record cannot supply is filled with a fixed "unknown" marker rather than guessed. Notable along the way: several older tests had been proving behaviour the phase deliberately abandoned, including one that relied on garbled text to force an abort; with no parsing left, garbled text is a perfectly good summary, so the tests were redesigned to express the same guarantees differently.

*Technical detail:* prompt [`10-phase-8.2-doc-parser-refactor.md`](10-phase-8.2-doc-parser-refactor.md), plan [`10-phase-8.2-doc-parser-refactor-plan.md`](10-phase-8.2-doc-parser-refactor-plan.md), report [`10-phase-8.2-doc-parser-refactor-report.md`](10-phase-8.2-doc-parser-refactor-report.md); build log, entry *Phase 8.2 — Doc-Parser Refactor (Claim Record as Source of Truth)*.

<a name="entry-11"></a>
### 11 — Phase 8.3: the audit trail records exactly what each model was told

**TL;DR:** When you opened an agent's card to see what it had asked the model, you saw a blank template with placeholders in it, not the real question. This phase made every agent record the exact, filled-in instructions it sent, and the interface now shows those. It also fixed a panel that said "waiting" forever and gave each run a link to its audit entries. Finished on 16 June 2026.

**Technologies:** no new ones; an additive field on every agent's audit entry and matching changes to the React cards.

This phase set out to make the explainability surfaces usable end to end: the prompt panel showed a template rather than the real prompt; the response panel never left its waiting state on finished runs; the run header truncated the reference number and offered no path to the audit view. It delivered all three fixes with 10 new tests. The lasting change is to the audit trail: every agent's entry now carries the literal instructions the model received, system and per-claim parts separately, present only when a call was actually made, so the absence of the field truthfully means no call. This was recorded as an additive extension to the locked audit contract. Dermot approved the plan as written and confirmed one design choice: the audit entry is passed down to the card rather than fetched by it, so there is one source of truth on the page. Notable along the way: the brief's diagnosis of the "waiting" fault was wrong, and the record says so; the real defect was that two different missing-data cases had been merged into one, and the fix separates them explicitly.

*Technical detail:* prompt [`11-phase-8.3-explainability-panel-fixes.md`](11-phase-8.3-explainability-panel-fixes.md), plan [`11-phase-8.3-explainability-panel-fixes-plan.md`](11-phase-8.3-explainability-panel-fixes-plan.md), report [`11-phase-8.3-explainability-panel-fixes-report.md`](11-phase-8.3-explainability-panel-fixes-report.md); build log, entry *Phase 8.3 — Explainability Panel Fixes*.

_Further entries follow, in build order._

## For engineers: how the archive is organised

Every prompt used to build this prototype is archived here in numerical order, paired with the plan that was approved before execution and the report that was produced after execution. Together with the build log, this gives a complete audit trail per phase: intent, design, outcome.

### Convention

- One prompt per logical step (typically one per build phase).
- Numbered sequentially with zero-padded prefixes: `01-`, `02-`, etc.
- Descriptive filename, lowercase with hyphens: `01-phase-0-repository-scaffold.md`.
- Each prompt is self-contained — it can be read and executed without external context beyond the repository itself and the global standards at `~/.claude/CLAUDE.md`.
- Prompts are authored by the architect and saved here directly. Claude Code is invoked by referencing the file (for example: *"Read and execute docs/prompts/01-phase-0-repository-scaffold.md"*).
- Each prompt opens by referencing `CLAUDE.md` and the relevant section of `BUILD-PLAN.md` (the build plan is kept locally and is not committed to the public repository).
- Each prompt follows the global plan-first workflow: produce a written plan, wait for confirmation, then execute.
- Each prompt's execution ends by appending an entry to `docs/build-log.md`, saving a report file alongside the plan, and updating the "Current Status" section of `CLAUDE.md`. The build-log entry references the prompt, the plan, the report, and any rejected plan iterations.

### The four artefacts per phase

| Artefact | When | Authored by | Captures |
|---|---|---|---|
| **Prompt** — `NN-phase-N-name.md` | Before execution | Architect | What was asked. |
| **Plan** — `NN-phase-N-name-plan.md` | Before execution, after planning | Claude Code, approved by architect | What was agreed. Approval footer at the bottom of the file with verbatim approval message and ISO 8601 UTC timestamp. Decisions made during planning live here in "Approach and key design decisions". |
| **Report** — `NN-phase-N-name-report.md` | After execution | Claude Code | What was actually built. One-line `Recap`, `Completed at` ISO 8601 UTC timestamp, files created/modified, test counts, deviations from the plan with reasons, guard clauses added, optional enhancements recommended, outstanding items. |
| **Build-log entry** — appended to `docs/build-log.md` | After execution | Claude Code | One-paragraph chronological summary linking to the other three artefacts. |

The plain-language decision register ([`../decision-register.md`](../decision-register.md)) is the reader's record of incidents and gate decisions. The engineer's record stays in three places:

- **Pre-execution design decisions** — in the plan body's "Approach and key design decisions" section.
- **Decisions made at the approval gate** — in the plan's `## Approval` footer (overrides, amendments to the plan, the verbatim approval message).
- **In-flight deviations forced by reality during execution** — in the report's "Deviations from spec" section.

Tracing the lineage end-to-end: open the plan to see what was originally proposed → scroll to the Approval section to see what was actually approved → open the report to see what was actually executed.

### Plan workflow

The plan-first standard is implemented as follows:

1. **Plan saved before approval.** Claude Code writes the plan verbatim to `NN-phase-N-name-plan.md` *before* asking for approval. This lets the architect read it in their editor rather than scrolling through a chat transcript.
2. **Approval recorded in the plan file.** When the architect approves, Claude Code appends an `## Approval` footer to the plan file. The footer's order ends with the timestamp so it sits at the very bottom of the file:

   ```
   ## Approval

   **Approval message:** "..."

   ---

   **Approved by:** Dermot Copps
   **Approved at:** <ISO 8601 UTC>
   ```

3. **Rejected plans preserved.** When the architect rejects (any feedback short of unambiguous approval), Claude Code appends a `## Rejection` footer to the current plan file (timestamp, summary of feedback, pointer to the next iteration), renames it to `NN-phase-N-name-plan-rejected-MM.md` where `MM` is the iteration number, and saves a revised plan as the new canonical `NN-phase-N-name-plan.md`. Iteration repeats until the canonical plan carries an `## Approval` footer.
4. **Execution proceeds against the approved plan only.** Claude Code does not write code until the canonical plan file is approved.

### Report workflow

After Phase execution completes:

1. Claude Code writes the report verbatim to `NN-phase-N-name-report.md`.
2. The report opens with a `## Summary` block containing, in this order:
   - **Recap** — one sentence stating what's done plus one sentence stating what comes next. The kind of single-paragraph elevator pitch a reader can scan in five seconds. (Example: *"Phase 0 of the agentic-claims-poc build is complete and pushed to dcopps/agentic-claims-poc with CI green. Next: provision the Render Web Service via the committed `render.yaml` blueprint and the Vercel project so deployments go live."*)
   - **Completed at** — ISO 8601 UTC timestamp at the moment of report-writing (e.g. `2026-05-09T14:32:18Z`). This is the precise time the phase concluded.
   - **Phase** — the phase number and title.
   - **Status** — Complete / Complete with deferrals / etc.
   - Links to the prompt, the approved plan, and the repository.
   - CI status if relevant.
3. Body sections cover files created and modified by tier, test counts and pass rates, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement.
4. The build-log entry references the report file alongside the plan and prompt.

**Why the recap line.** It's the highest-leverage element in the file — anyone scanning the report (an interview reviewer, a future Claude session, a stakeholder updating themselves) gets the "what got done, what's next" in one line without reading further. Carries the same role for the report that the build-log entry's `Prompt summary` line carries for the chronological log.

**Timestamp format.** Both the plan's `## Approval` footer and the report's `Completed at` field use ISO 8601 UTC (e.g. `2026-05-08T11:50:06Z`). This pairs cleanly with the build-log entry's ISO date heading and gives the audit trail consistent timestamps end-to-end.

### Reproducibility note

The pre-build setup work — restructuring `CLAUDE.md` to follow the global standards, creating `BUILD-PLAN.md`, creating `docs/build-log.md`, adding the four diagrams under `diagrams/`, copying the stack reference under `docs/`, and seeding this prompts archive — was performed manually before the prompts archive was opened. That work is recorded in the first entry of `docs/build-log.md`. From `01-phase-0-repository-scaffold.md` onward, every change to the repository is driven by a prompt in this folder and recorded by the matching plan, report, and build-log entry.
