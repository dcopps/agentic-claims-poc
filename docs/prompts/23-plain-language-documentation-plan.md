# Prompt 23 — Plan: plain-language documentation (decision register, build story, signposts)

**Prompt:** `23-plain-language-documentation.md`. **Scope:** documentation only — no code, prompt, test, infrastructure or workflow change; no version bump; no deployment; no Azure session. **Status:** awaiting approval; nothing has been written yet beyond this plan.

Read before planning: the prompt; `docs/prompts/README.md` as it stands; every `## Phase` heading and the Phase 8.4 → 9.2.2 entries of `docs/build-log.md` (with their *Issues and deviations*, *Findings*, *Recorded exception*, *Halt* and *Close-out* subsections); `docs/BACKLOG.md` (open findings and closed sections); the 67 files under `docs/prompts/` (22 prompts with plans and reports, prompt 14 has no plan, prompt 23 with this plan; 68 once this phase's report exists); the anonymisation test's scan roots (it covers `docs/`, `README.md` and `CLAUDE.md`, so the new documents are inside the standing guard).

---

## 1. The two documents, in outline

### `docs/decision-register.md` — *Decisions and incidents, in plain language.*

1. Title. 2. Purpose paragraph (what it is, who it is for, the rule: every halt, deviation, incident or approval-gate decision gets an entry before the phase closes). 3. Glossary (§2). 4. How to read an entry (the nine fixed fields, one sentence each). 5. Entries R-01 … in build order (§3). Each entry carries an HTML anchor `<a name="r-07"></a>` above its heading so links from the build story and the reports can point at an entry, not at a heading whose generated slug could change.

### `docs/prompts/README.md` — *The build, phase by phase, in plain language.*

1. New title. 2. Purpose paragraph (one paragraph: what the prototype is, that this index tells the build's story in order, who it is for, where the technical record is). 3. The same glossary, verbatim (the two documents must stand alone; a reader may open either first). 4. The index: entries 01 … 23, each with an anchor `<a name="entry-12"></a>`, a heading of the form *12 — Phase 8.4: the audit trail was losing entries*, three to five plain sentences, links to the prompt, plan and report files, and a *Technical detail* line. Entries that have register entries link to them by anchor. 5. Retitled *For engineers: how the archive is organised*, holding the existing *Convention*, *The four artefacts per phase*, *Plan workflow* and *Report workflow* sections unchanged, with one correction: the paragraph beginning *"There is no separate 'decisions' file"* becomes *"The plain-language decision register (`../decision-register.md`) is the reader's record of incidents and gate decisions; the engineer's record stays in three places:"* followed by the same three bullets. 6. The *Reproducibility note*, unchanged. **The old four-row `## Index` table is removed** (decision D3): every file it listed is linked from the plain-language index, and a second, stale index would contradict the first.

---

## 2. Glossary terms (defined once at the top of each document, used consistently)

The test for inclusion: a word the reader will meet repeatedly that cannot be replaced by a plain phrase every time without becoming unreadable. Twelve terms, each defined in one sentence by what it does:

| Term | Working definition (final wording in the document) |
|---|---|
| **The prototype** | The working system this project built: software that reads an insurance claim, checks it against the policy wording, proposes a settlement figure, checks that proposal, and either settles the claim or sends it to a person. |
| **Agent** | One of the four specialised pieces of software in the prototype, each with a single job, each calling a language model to do it. |
| **Doc-Parser, Validator, Adjuster, Guardrail** | The four agents: the one that reads the claim; the one that decides whether the policy covers the loss; the one that proposes a settlement figure with its reasons; the one that checks the Adjuster's reasons for leaked personal data, bias and policy wording that the policy does not contain. |
| **Orchestrator** | The part of the prototype that runs the four agents in order and applies the escalation rules at the end. |
| **Language model** (or *the model*) | The external AI service each agent calls. The prototype uses Anthropic's Claude models; the alternative provider, Mistral, is kept switchable. |
| **Prompt** | The written instructions an agent sends to the model with each request. Two kinds: the fixed instructions that define the agent's job, and the per-claim content. |
| **Audit trail** | The tamper-evident record of everything each run did: every agent's input, output and model call, chained so that any later alteration is detectable. The project's rule is that the audit trail alone must be enough to explain any past decision. |
| **Human review** (*escalation*) | The outcome in which the prototype stops and hands the claim to a person, with the rule that fired. |
| **The three scripted scenarios** | The three synthetic claims every verification runs: a water-damage claim that should settle automatically; a fire claim large enough to need a person; and a claim whose reasoning cites a policy endorsement that does not exist, which the Guardrail must catch. |
| **Deployed stacks** | The two live installations of the same code: the original on Render, Vercel and Neon (the demo's home), and the Azure installation added in Phase 9. |
| **Approval gate** | The point in every phase where the written plan is put to Dermot and nothing is built until he approves it; decisions taken there are recorded in the plan. |
| **Replay** | Re-sending a recorded prompt to the model to see whether its answer has changed; since Phase 9.2.1 a set of recorded runs is replayed before every demo. |

Names of the three synthetic claimants (Harborline, Northwood, Coral Bay) are synthetic and stay; the client name appears nowhere.

---

## 3. Register entries found in the record

The prompt's fourteen are the minimum. Mining the build log, reports and backlog from Phase 8.4 onward gives **nineteen** entries: the fourteen (some of which split naturally into two) plus four additions, flagged. Order is build order. Working titles; final titles follow the writing standard.

| # | Working title | Phase / date | Kind | Prompt item |
|---|---|---|---|---|
| R-01 | The audit trail was silently losing three of every seven entries on the live system | 8.4, 26 June 2026 | incident | 1 |
| R-02 | A test run wiped the live database; the tests now refuse to touch any live host | 8.5, June 2026; extended 9.1, 1 October | incident + control | 2 |
| R-03 | A migration test passed while leaving the database broken, invisibly in CI | 8.5.1 | incident | 3 |
| R-04 | Pinning the Mistral model to one named release | 8.5.2, 14 September | decision | 4 |
| R-05 | Recording in the audit trail which model was asked, not only which answered; and resetting the live database to a known state under a hostname check (the design overrode the prompt's stated preference — a deviation) | 8.5.3, 14 September | decision + deviation | 4 |
| R-06 | Mistral withdrew its large model from the free tier; Claude Haiku became the default for all four agents, Mistral kept switchable | 8.6, 14–15 September | incident + decision | 5 |
| R-07 | The live verification halted: a mis-written pattern treated ordinary prose as a policy citation | 8.6, 15 September → 8.6.1 | halt + incident; includes the correction of a wrong statement in the 8.6 report | 6 |
| R-08 | **Addition.** Three findings from the 21 September verification, ruled findings rather than halts and left open: five background claims cannot complete; no path for a coverage denial; retrieval missed the governing section | 8.6.1, 21 September | decision (Dermot's ruling) + open items | — |
| R-09 | Azure foundation decisions: a user-assigned identity; building the image in the cloud registry after the free-trial block; baking the embedding model into the image | 9.1, 1 October | decisions | 7 |
| R-10 | **Addition.** Parking the Azure stack: the replica that outlived the stop, and the database that restarts itself after seven days | 9.1, 1 October; 9.2, 26 October | operational finding + decision | — |
| R-11 | The build had been red since 15 June and nobody could have deployed from it; fixed in two steps, the first with the wrong tool version | 9.2, 26 October | incident | 8 |
| R-12 | The frontend host was refused in West Europe; East US 2 accepted, holding only static files | 9.2, 26 October | decision | 9 |
| R-13 | **Addition.** How a push was allowed to deploy to Azure: no cloud-written workflow files, no stored credential, infrastructure kept out of the pipeline | 9.2, 26 October (gate decisions 1–3) | decisions | — |
| R-14 | A correct deployment reported as failed: the check read a two-line answer as one | 9.2, 26 October | incident | 10 |
| R-15 | Telemetry recorded nothing because of the order in which two pieces of code loaded | 9.2, 26 October | incident | 11 |
| R-16 | The pinned model changed its verdict on identical input between 1 and 26 October; proven by replay; entered in the governance and third-party registers | 9.2, 26 October | incident + governance | 12 |
| R-17 | Phase 9.2.1: narrowing the question; the "market range" finding; changing the user-side instructions (a revised decision); temperature set to zero on the live stacks; new escalations on the script and Vercel paths; closed as partially verified with a failing test kept on purpose | 9.2.1, 28–30 October | decisions + partial outcome | 13 |
| R-18 | Phase 9.2.2: the decision moved into code; the conflict in the brief (a field on the flag model versus no change to responses) and how it was resolved; verified on all three surfaces; the Coral Bay latency question answered from the audit | 9.2.2, 30 October | decision + verification | 14 |
| R-19 | **Addition.** Phase 9.2.2's accepted trade-off: a citation written without a provision keyword no longer counts from the model's check alone | 9.2.2, 30 October | decision (approval gate) | 14 (split out, because it is a standing limitation a reviewer should find on its own) |

**Not included, flagged for Dermot:** the record before Phase 8.4 holds approval-gate amendments (Phase 0's three answers and three amendments; Phase 4's `cross_jurisdictional` marker; Phase 5's two audit amendments; Phase 7's manual client-name grep before push; Phase 8's six rehearsal fixes) and two engineering surprises (Phase 1's Decimal canonicalisation, Phase 2's typing of the embedding loader). The prompt starts the register at 8.4; these will appear in the **build story** entries for prompts 01–09 as "notable along the way", not in the register. Say the word and any of them becomes a register entry.

**Where the record is silent.** R-03's "who decided" is the prompt itself (a point release Dermot commissioned); R-10's first half was observed, not decided. Entries will say so rather than attribute.

---

## 4. The exact signpost line

Top of every file under `docs/prompts/` (prompt, plan, report; 01 through 23; 68 files including this plan and its report), as the first line, followed by a blank line:

```
> *Plain-language summary of this phase: see [the build story](README.md#entry-12), entry 12.*
```

`NN` is the two-digit prompt number; the anchor is the `<a name="entry-NN">` placed in the index. Nothing else in those files changes. For `docs/build-log.md`, the first line after the title:

```
> *Plain-language versions of this record: [the build story](prompts/README.md) (phase by phase) and [the decision register](decision-register.md) (incidents and decisions).*
```

For `README.md`, immediately after the H1 and before the existing opening paragraph:

```
## Not an engineer? Start here

This project is a working prototype of AI-assisted insurance claims handling, built to show that such a system can be governed, inspected and audited. Two documents tell its story without code: [the build, phase by phase](docs/prompts/README.md) and [the decisions and incidents register](docs/decision-register.md).
```

Final wording of that paragraph is Dermot's to adjust at the end-of-build review.

---

## 5. `CLAUDE.md` changes (done once, at the end)

- **Standing Instructions**, two new paragraphs in the house style, after *Save every prompt to `docs/prompts/`*:
  - **Decision register.** Every halt, deviation from a plan, incident, or decision taken at an approval gate produces an entry in `docs/decision-register.md`, in plain language per that document's standard, before the phase's closing commit.
  - **Build story.** Every phase's close-out adds its entry to the plain-language index in `docs/prompts/README.md`, and the new prompt, plan and report files carry the one-line signpost at the top.
- **Build Approach:** "Every phase ends with two appends" → four: the build-log entry; the prompt archived verbatim; a decision-register entry where the phase had a halt, deviation, incident or gate decision; the build-story entry.
- **Project structure tree:** `docs/decision-register.md     # plain-language incidents and gate decisions` inserted after `BACKLOG.md`.
- **Current Status:** during the work, a line *Prompt 23 in progress — entries approved through prompt NN; next: prompt NN+1* so a session can resume; at the end, the phase closed, the known-debt line about the index closed, *What's next* → prompt 24 (Azure AI Foundry).

---

## 6. Verifying every pointer

Run from the shell at the end (and at each per-phase commit for that phase's links); not committed, because the constraints keep this phase inside `docs/`, `README.md` and `CLAUDE.md`:

1. Every Markdown link in the two documents, the README section and the build-log pointer is extracted; the target file must exist relative to the linking file.
2. Every `#anchor` must match an `<a name="…">` in the target (for the two documents) or a heading slug (for links into `docs/build-log.md`, which are to `## Phase …` headings — the check computes the slug the way the renderer does and also greps the heading text).
3. Every *Technical detail* line is parsed for its pointers (file paths, and build-log section titles in quotes); each file must exist and each section title must appear as a heading in the build log.
4. Every `docs/prompts/*.md` file begins with the signpost line whose anchor is `entry-NN` for its own `NN`.
5. `uv run pytest backend/tests/test_anonymisation.py` (it scans `docs/`, `README.md`, `CLAUDE.md`); plus a manual read of every quotation lifted from earlier records.

The report lists the counts: links checked, anchors checked, files checked, zero failures.

---

## 7. Working method (as decided by Dermot, 30 October 2026)

One phase at a time, in build order, each reviewed before the next is written, one commit per phase.

- **Stop 1, prompt 01 (Phase 0):** both documents are created with their title, purpose paragraph, glossary and "how to read an entry" section, plus build-story entry 01, so the voice of the preambles is reviewed on the first stop too. No register entry (the register's first entry is at prompt 12).
- **Stops 2–11, prompts 02–11:** build-story entry only, three to five sentences each; notable gate amendments go in the entry's last sentence.
- **Stops 12–22, prompts 12–22:** build-story entry plus the register entries of §3 that belong to that prompt (R-01 at prompt 12 … R-18/R-19 at prompt 22). These stops are longer.
- **Stop 23:** build-story entry 23 (this phase), the signposts in all 68 archive files, the build-log pointer and short entry, the README section, the `docs/prompts/README.md` restructure, the `CLAUDE.md` changes, the pointer check, the report. One commit, push.

At each stop the entries are presented **in full** in the reply, not summarised. Commit message shape: `docs(plain-language): prompt NN — build story entry[, register R-xx…]`. If a session ends mid-way, `CLAUDE.md` *Current Status* names the next prompt number.

---

## 8. Files

**Created:** `docs/decision-register.md`; `docs/prompts/23-plain-language-documentation-plan.md` (this file), `-report.md`.
**Rewritten:** `docs/prompts/README.md`.
**Edited:** `README.md` (one new section at the top); `docs/build-log.md` (pointer line; one short entry for this phase); `CLAUDE.md` (§5); the one-line signpost at the top of the 68 files under `docs/prompts/`.
**Untouched:** everything else.

---

## Decisions requested at the approval gate

- **D1 — Nineteen register entries** (§3): the fourteen, with four additions (R-08 open findings, R-10 parking, R-13 deploy-permission decisions, R-19 the accepted trade-off). *Recommended:* all nineteen.
- **D2 — Pre-8.4 gate amendments** stay in the build story, not the register. *Recommended:* yes.
- **D3 — Remove the stale four-row index table** from `docs/prompts/README.md` (superseded by the plain-language index, which links every file). *Recommended:* yes.
- **D4 — HTML anchors** (`<a name="entry-NN">`, `<a name="r-NN">`) rather than relying on generated heading slugs, so the signpost links survive a retitled heading. *Recommended:* yes.
- **D5 — Glossary repeated verbatim in both documents** rather than one linking to the other. *Recommended:* yes; each document must stand alone for a reader who opens only one.
- **D6 — Both documents' preambles reviewed at stop 1** with entry 01, so the voice is set before the long middle.

## Optional enhancements (clearly labelled; not in scope unless approved)

- A one-page *Start here* document for the production-architecture reader (the column of `docs/architecture-stack-reference.md`), in the same standard. Not part of this prompt.
- An entry-count line in `CLAUDE.md` *Current Status* (registers: 19 entries) maintained at each close-out — cheap, but one more thing to keep in step.

## Approval

**Approved 30 October 2026 (Dermot).** D1–D6 as recommended: nineteen register entries; pre-8.4 amendments stay in the build story; the stale index table is removed; HTML anchors; the glossary repeated in both documents; both preambles reviewed at stop 1. Neither optional enhancement. Work proceeds one phase per stop, beginning with prompt 01.

**Stop 1 approved as written, with one addition to the format (Dermot, 30 October 2026):** every build-story entry and every register entry opens with a short paragraph labelled *TL;DR:* in bold — three or four plain sentences, simpler in voice than the main entry (revised from a one-line opener at stop 2), followed by one bold line labelled *Technologies:* naming in plain words the technologies the phase introduced or depended on (added at stop 2) — and at the end of the build the build story gets an at-a-glance table at the top listing every phase with its TL;DR. Forward references: the build story may reach forward where it helps the reader; register entries stay in their own moment. Also requested: a backlog item for an MCP server in front of the prototype's API (recorded under *Future work*).
