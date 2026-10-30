# Prompt 23 — Plain-language documentation: the decision register, the build story, and the signposts to them

## Why this phase exists

Everything that has happened in this build is recorded, but in three technical places: `docs/build-log.md` (what was built), the `-report.md` files (how each phase went) and `docs/BACKLOG.md` (what is pending). An auditor, a hiring manager, a compliance reviewer or a future maintainer who is not an engineer cannot read any of them without someone beside them. The project's claim is that AI-assisted delivery can be governed and inspected; that claim needs documents a non-engineer can inspect.

This phase adds two plain-language documents and the signposts that make them impossible to miss, then makes both part of the standing routine so they never fall behind again. It is a documentation phase: **no code, prompt, infrastructure or test changes**, no version bump. Decided by Dermot on 29 and 30 October 2026. Phase 9.3 (Azure AI Foundry) becomes prompt 24.

## Audience and writing standard

Write for a competent professional who has never seen the code and does not want to: an insurance compliance officer, an auditor, a hiring manager. The test for every sentence is whether that reader could repeat it accurately to a colleague. Concretely:

- British English. No bullet-point fragments; short paragraphs or short complete sentences.
- No code identifiers, file paths, commit hashes, function names or error strings in the body of an entry. Each entry ends with one *Technical detail* line pointing to where the engineer's record is (build-log section, report, plan). That line may use identifiers; nothing above it may.
- Name things by what they do, not what they are called: "the check that compares the model's claim against the policy wording", not "the Guardrail rule engine". Where a project term is unavoidable (Guardrail, Adjuster, audit trail), define it once in a short glossary at the top of each document and use it consistently.
- Say what happened, what it meant, what was decided and by whom, what was done, and how it was proven. No adjectives about quality; the evidence does that.
- Dates in full. Correlation ids and version numbers belong in the *Technical detail* line only.
- Anonymisation applies as everywhere: the client name appears nowhere.

## Deliverable 1 — the decision register: `docs/decision-register.md`

**Title:** *Decisions and incidents, in plain language.*

**Purpose paragraph** at the top: what this document is, who it is for, and the rule that every halt, deviation, incident or decision taken at an approval gate gets an entry before the phase closes.

**Entry format**, fixed, one entry per incident or decision, each about ten lines:

- Number and short title (for example *R-07 — The Guardrail model changed its verdict on identical input*).
- Date, and the phase it belongs to.
- *What happened.* Two or three sentences.
- *Why it mattered.* One or two sentences: the risk, or the consequence had it gone unnoticed.
- *What was decided, and by whom.* Dermot, as the person accountable, at which gate.
- *What was done.*
- *How it was proven.* The test, replay, or observation that showed the fix worked; or, if it did not fully work, say so.
- *Status.* Resolved / Partially resolved / Open, with the follow-on if any.
- *Technical detail:* one line of pointers.

**Backfill.** Mine `docs/build-log.md`, the reports and `docs/BACKLOG.md` from Phase 8.4 onward and write an entry for every incident or gate decision found. The following must appear; add any others the record shows:

1. The audit-write transaction bug (Phase 8.4).
2. The test-isolation incident: a test run against the deployed database wiped it, and the guard that now refuses deployed hosts (Phase 8.5, extended in 9.1).
3. The migration-test autocommit fix (Phase 8.5.1).
4. Pinning the Mistral model (Phase 8.5.2) and recording the requested model in the audit (8.5.3).
5. Mistral withdrawing its large model from the free tier, and the decision to make Claude Haiku the default while keeping Mistral as a switchable alternative (Phase 8.6).
6. The citation-check false positive caused by a case-insensitive pattern (Phase 8.6.1).
7. Azure decisions in 9.1: a user-assigned rather than system-assigned identity; `az acr build` instead of local Docker after the free-trial block on registry tasks; baking the embedding model into the image.
8. CI red since 15 June, found during 9.2 planning, and the two-step fix (wrong npm version first).
9. Static Web Apps refused in West Europe; East US 2 accepted, holding only static files.
10. The deploy-check bug that made a good deployment look red (9.2).
11. The telemetry import-order bug (9.2).
12. The pinned model changing its verdict on identical input between 1 and 26 October, proven by replaying recorded prompts; the governance and DORA entries (9.2).
13. Phase 9.2.1: narrowing the Guardrail's question; the "market range" finding; the template change (D5 revised); the Render script and Vercel escalations on new phrases; closing as partially verified.
14. Phase 9.2.2: moving the decision into code (quote-verified flags); the conflict found in the prompt and how it was resolved; verification on all three surfaces.

Where an entry is a decision rather than an incident (7, parts of 5), use the same format; *What happened* becomes the situation that forced a choice.

**Cross-check:** every entry's *Technical detail* line must point at something that exists. Verify each pointer.

## Deliverable 2 — the build story: `docs/prompts/README.md`

**Title:** *The build, phase by phase, in plain language.*

Keep the existing *Convention* and *The four artefacts per phase* sections (they are correct and useful to engineers), but move them below a new plain-language index and retitle them *For engineers: how the archive is organised*. **Correct the sentence "There is no separate 'decisions' file"**: there now is a plain-language one, `docs/decision-register.md`, and the three technical locations it describes remain the engineer's record.

The index: one entry per prompt, 01 to 23, in order, three to five plain sentences each: what the phase set out to do, what it delivered, and anything notable it found along the way. Link each to its prompt, plan and report. Every entry has a *Technical detail* line as above, and the body obeys the same writing standard. The known-debt line in `CLAUDE.md` ("index not maintained past prompt 04") is closed by this.

## Deliverable 3 — the signposts

1. **`README.md`**, at the very top, before any technical content, a short section headed *Not an engineer? Start here.* Two or three sentences pointing to the build story and the decision register, and saying in one line what the project is in plain words.
2. **Every file in `docs/prompts/`** (prompt, plan and report, 01 through 23) gets a one-line note at the very top: *Plain-language summary of this phase: see [the build story](README.md#…), entry NN.* Anchor to the entry. Do not otherwise alter those files; they are the archive.
3. **`docs/build-log.md`** gets the same one-line pointer at the top to both documents.
4. The two document titles above, so the file names do not have to do the work.

## Deliverable 4 — make it stick

In `CLAUDE.md` *Standing Instructions*, add two rules in the house style:

- *Decision register.* Every halt, deviation from a plan, incident, or decision taken at an approval gate produces an entry in `docs/decision-register.md`, in plain language per that document's standard, before the phase's closing commit.
- *Build story.* Every phase's close-out adds its entry to the plain-language index in `docs/prompts/README.md`, and the new prompt, plan and report files carry the one-line signpost at the top.

Update the *Build Approach* section's "every phase ends with two appends" to four (build log, prompt archive, register entry where applicable, build-story entry). Update the project-structure tree to include `docs/decision-register.md`.

## Plan-first, then one phase at a time

Produce `docs/prompts/23-plain-language-documentation-plan.md` covering: the glossary terms you will define; the list of register entries you found in the record (with the fourteen above as the minimum and any additions flagged); the exact signpost line; the `CLAUDE.md` changes; how you will verify every pointer resolves; and the working method below. Wait for approval.

**Working method — decided by Dermot, 30 October 2026.** The documents are written **one phase at a time, in build order, with Dermot reviewing each phase's entries before the next is written.** This is deliberate: Dermot is using the exercise to build his own plain-language account of the project, and the voice is cheaper to correct on one entry than on forty. For each phase, from prompt 01 to prompt 22:

1. Write that phase's build-story entry, and any decision-register entries that belong to it.
2. Stop. Present the entries to Dermot in full and wait. He may ask questions about the phase, request rewording, or approve.
3. On approval, commit that phase's entries (one commit per phase, so the history shows the review), then move to the next.

The first stop, after the plan is approved, is prompt 01 (Phase 0). Expect the early phases to be quick and the Phase 8.4 onward entries to take longer, since that is where the register entries begin. The signposts, the `README.md` section, the `CLAUDE.md` changes and the restructuring of `docs/prompts/README.md` are done once, at the end, after the last phase is approved. If a session ends mid-way, the committed entries are the record of where to resume; note the next phase number in `CLAUDE.md` *Current Status*.

## Deliverables (after approval)

- `docs/decision-register.md` (new), `docs/prompts/README.md` (restructured), `README.md`, `docs/build-log.md` (pointer line and a short entry for this phase), `CLAUDE.md` (standing instructions, build approach, tree, Current Status, known debt closed, What's next → prompt 24 Foundry), the one-line signpost in every `docs/prompts/*.md` file.
- `docs/prompts/23-plain-language-documentation-plan.md` and `-report.md`.
- Commit and push. No deployment; no Azure session.

## Constraints

- No change to any file outside `docs/`, `README.md` and `CLAUDE.md`. No code, prompts under `backend/app/prompts/`, tests, infrastructure or workflows.
- Prompt, plan and report files in the archive are modified only by the one-line signpost at the top.
- Anonymisation: the client name appears nowhere, including in any quotation from earlier records.
- Nothing is invented. If the record does not say who decided or how something was proven, the entry says that the record is silent on it.

## Archive

Pre-saved at `docs/prompts/23-plain-language-documentation.md`; plan and report alongside. Azure AI Foundry is prompt 24.
