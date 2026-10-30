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
