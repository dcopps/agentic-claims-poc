# Decisions and incidents, in plain language

## What this document is

This is the record of every moment in the build of this prototype when something went wrong, when the work departed from its plan, or when a decision had to be taken by the person accountable for it. It is written for a reader who is not an engineer and does not want to read code: a compliance officer, an auditor, a hiring manager, or a future maintainer arriving cold. Each entry says what happened, why it mattered, what was decided and by whom, what was done, how it was shown to have worked, and where the engineer's detailed record is.

The project's claim is that software built with an AI assistant can be governed and inspected. A claim like that needs a record a non-engineer can inspect without someone beside them. This is that record. The engineer's record remains in three technical places, and every entry here ends with a pointer into it.

The rule from Prompt 23 onward is that every halt, every deviation from an approved plan, every incident and every decision taken at an approval gate produces an entry here before the phase that contains it is closed. Entries before that date were written afterwards from the technical record, and say so where the record is silent.

## Glossary

A handful of project terms recur throughout. They are defined here once, by what they do, and used consistently below.

**The prototype.** The working system this project built: software that reads an insurance claim, checks it against the policy wording, proposes a settlement figure, checks that proposal, and either settles the claim or sends it to a person.

**Agent.** One of the four specialised pieces of software in the prototype, each with a single job, each calling a language model to do it.

**Doc-Parser, Validator, Adjuster, Guardrail.** The four agents. The Doc-Parser reads the claim. The Validator decides whether the policy covers the loss. The Adjuster proposes a settlement figure and gives its reasons. The Guardrail checks the Adjuster's reasons for leaked personal data, for bias, and for references to policy wording that the policy does not contain.

**Orchestrator.** The part of the prototype that runs the four agents in order and applies the escalation rules at the end.

**Language model**, or **the model**. The external artificial-intelligence service each agent calls. The prototype uses Anthropic's Claude models. An alternative provider, Mistral, is kept available as a switch.

**Prompt.** The written instructions an agent sends to the model with each request. There are two kinds: the fixed instructions that define the agent's job, and the per-claim content that changes every time.

**Audit trail.** The tamper-evident record of everything each run did: every agent's input, its output and its call to the model, chained together so that any later alteration is detectable. The project's rule is that the audit trail alone must be enough to explain any past decision.

**Human review**, or **escalation**. The outcome in which the prototype stops and hands the claim to a person, recording which rule sent it there.

**The three scripted scenarios.** The three synthetic claims that every verification runs. A water-damage claim that should settle automatically. A fire claim large enough that a person must see it. And a claim whose reasoning cites a policy endorsement that does not exist, which the Guardrail must catch.

**Deployed stacks.** The two live installations of the same code: the original, hosted on Render, Vercel and Neon, which is the demonstration's home; and the Azure installation added in Phase 9.

**Approval gate.** The point in every phase where the written plan is put to Dermot, the person accountable for the project, and nothing is built until he approves it. Decisions taken there are recorded in the plan.

**Replay.** Re-sending a recorded prompt to the model to see whether its answer has changed. Since Phase 9.2.1 a set of recorded runs is replayed before every demonstration.

The names of the three synthetic claimants, Harborline, Northwood and Coral Bay, are invented. No real client is named anywhere in this project.

## How to read an entry

Every entry has the same ten parts, in the same order, and runs to about ten lines. The number and title say what it is about. *In one line* is a single bold sentence that summarises the whole entry, for the reader who will go no further. The date and phase place it in the build. *What happened* describes the event in two or three sentences, or, for a decision, the situation that forced a choice. *Why it mattered* states the risk, or what would have followed had it gone unnoticed. *What was decided, and by whom* names the person and the gate. *What was done* describes the response. *How it was proven* names the test, replay or observation that showed the response worked, and says plainly if it did not fully work. *Status* is one of Resolved, Partially resolved or Open, with the follow-on if there is one. *Technical detail* is the one line that may use file names and identifiers, and it points to the engineer's record.

## Entries

The register begins with Phase 8.4 in June 2026, the first phase in the build that was itself a response to an incident. Earlier phases had approval-gate amendments but no incidents; those amendments are noted in the build story, phase by phase. Each entry stays in its own moment: it describes what was known at the time, and later developments are recorded in their own entries.

_Entries follow, in build order._
