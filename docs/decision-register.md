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

Every entry has the same ten parts, in the same order, and runs to about ten lines. The number and title say what it is about. *TL;DR* is a short paragraph of three or four plain sentences, in a simpler voice than the rest, for the reader who has thirty seconds and will go no further. *Technologies* is one bold line naming, in plain words, only the technologies the entry involves. The date and phase place it in the build. *What happened* describes the event in two or three sentences, or, for a decision, the situation that forced a choice. *Why it mattered* states the risk, or what would have followed had it gone unnoticed. *What was decided, and by whom* names the person and the gate. *What was done* describes the response. *How it was proven* names the test, replay or observation that showed the response worked, and says plainly if it did not fully work. *Status* is one of Resolved, Partially resolved or Open, with the follow-on if there is one. *Technical detail* is the one line that may use file names and identifiers, and it points to the engineer's record.

## Entries

The register begins with Phase 8.4 in June 2026, the first phase in the build that was itself a response to an incident. Earlier phases had approval-gate amendments but no incidents; those amendments are noted in the build story, phase by phase. Each entry stays in its own moment: it describes what was known at the time, and later developments are recorded in their own entries.

<a name="r-01"></a>
### R-01 — The audit trail was silently losing three of every seven entries on the live system

**TL;DR:** The audit trail is the record that is supposed to explain every decision the system makes. On the live system it was quietly dropping most of each run's entries, while the screen showed everything as fine. The cause was one database setting. It was fixed, and tests were added that would have caught it.

**Technologies:** PostgreSQL transactions through the psycopg database driver.

**Date and phase.** 26 June 2026, Phase 8.4.

**What happened.** While rehearsing the demonstration on the deployed system, a threshold-escalation run showed all four agents completing on screen, but the audit trail held entries for only the last agent and the orchestrator. The three earlier agents' entries, including the Validator's coverage verdict and the Adjuster's settlement reasoning, had never been written.

**Why it mattered.** The project's central claim is that the audit trail alone is enough to reconstruct and explain any past decision. A run whose record is two-sevenths complete cannot be explained, and nothing on screen said anything was wrong. Had it gone unnoticed, every live run since the connection setting was introduced would have been unexplainable after the fact.

**What was decided, and by whom.** Dermot commissioned the fix as its own phase and approved the plan at the gate with one amendment: two leftover commit calls in the data scripts, harmless but encoding the old behaviour, were brought into scope so the code would not mislead the next reader.

**What was done.** The database connection had been opened in a mode where an agent's first read quietly began a transaction, and the audit write then nested inside it and was discarded when the connection closed. The mode was changed so each write stands on its own, a now-redundant commit was removed, and every place that writes was reviewed to confirm nothing depended on the old behaviour. Four regression tests were added, one per agent, each writing through the real connection and reading back through a separate one.

**How it was proven.** The new tests were run against three connection states. Against the fix, all four passed. Against the original setting, three failed and one passed, reproducing the rehearsal exactly. Against the original setting with the redundant commit also removed, all four failed, which showed that commit had been holding the bug to three agents rather than four. The deployed verification was carried forward and discharged on 21 September 2026, when every run that reached a decision wrote exactly seven entries.

**Status.** Resolved.

*Technical detail:* build log, *Phase 8.4 — Audit-write Transaction Fix* (discriminator proof table); plan `12-phase-8.4-audit-write-fix-plan.md`; report `12-phase-8.4-audit-write-fix-report.md`; the fix is in `backend/db/connection.py`, the tests in `backend/tests/test_audit_persistence.py`.

<a name="r-02"></a>
### R-02 — A test run wiped the live database; the tests now refuse to touch any live host

**TL;DR:** The automated tests empty the database before they run. A developer's configuration pointed at the live database, so running the tests destroyed its contents. The fix was not a warning but a refusal: the tests now check where they are pointed and will not start against any live system, and there is no switch to make them.

**Technologies:** PostgreSQL; the pytest test harness; a hostname check against the Neon and, later, Azure database domains.

**Date and phase.** 27 June 2026, Phase 8.5; the guard was extended to the Azure database on 1 October 2026, Phase 9.1.

**What happened.** The test harness took its database address from the same configuration file the application uses. On a developer's machine that file pointed at the deployed database. The test fixtures empty the claims, audit and policy tables before each test, so an ordinary test run wiped the live system. The hazard had existed since Phase 1 and surfaced during the Phase 8.4 verification.

**Why it mattered.** The deployed database held the demonstration's claims and the audit trail that explains them. A single habitual command could destroy both without any prompt or confirmation, and nothing distinguished a safe run from a destructive one until it was too late.

**What was decided, and by whom.** Dermot commissioned the fix as its own phase, approved the plan as written, and chose to set up the local test database himself with the project's existing script, guided rather than driven. On 1 October 2026 he approved extending the same refusal to the Azure database as part of Phase 9.1.

**What was done.** The tests gained their own database and a dedicated setting for it. The harness now resolves the address before anything runs: it prefers the test setting, accepts the ordinary setting only when it points at a local machine, and refuses outright on any deployed host, naming the host and pointing to the setup instructions. There is deliberately no environment variable or flag that bypasses the refusal. The error names only the hostname, never the full connection string.

**How it was proven.** Three tests exercise each branch of the decision without touching a database. The guard was then run against the real configuration and stopped the suite before the table-clearing fixture, with the expected error. When the Azure host was added, the two new tests were shown to fail with the Azure domain temporarily removed from the guard and to pass with it restored.

**Status.** Resolved. The two-database rule and the refusal are recorded as a locked decision in the project's handbook.

*Technical detail:* build log, *Phase 8.5 — Test-isolation Fix* and *Phase 9.1 — Azure Foundation* (test guard); plan `13-phase-8.5-test-isolation-fix-plan.md`; report `13-phase-8.5-test-isolation-fix-report.md`; the resolver is `_resolve_test_database_url` in `backend/tests/conftest.py`, the tests in `backend/tests/test_db_isolation.py`.

<a name="r-03"></a>
### R-03 — A migration test passed while leaving the database broken, invisibly in CI

**TL;DR:** A test that checks a safety property worked by temporarily breaking the database and expecting it to be put back automatically. An earlier fix had removed the automatic undo. The test still passed, but left the database broken for every test run after it. The shared build server never noticed because it starts from a clean database each time.

**Technologies:** PostgreSQL constraints and transactions; the pytest harness.

**Date and phase.** 14 September 2026, Phase 8.5.1.

**What happened.** Running the full suite for the first time against the persistent local test database gave two failures in the migration tests. One test proves a documented hazard of undoing a migration: it drops a constraint and re-adds a narrower one, expecting the database to refuse. It had relied on both statements sharing one implicit transaction, so the refusal would roll back the drop. Phase 8.4 had removed that implicit transaction to fix the audit-trail loss (R-01). The drop now stood, the test passed, and the constraint was gone for every run that followed.

**Why it mattered.** Three properties made this dangerous. It was permanently invisible on the shared build server, which provisions a fresh database per run. The test passed on exactly the run that did the damage and failed on every innocent run afterwards, so blame would land on whoever ran next. And the harness's row-clearing between tests does not touch the schema, so nothing in the framework could notice. A test suite that can poison its own database while green is not a safety net.

**What was decided, and by whom.** Dermot commissioned a point release to fix it. The record does not describe a separate approval gate; the prompt, diagnosis and plan were one document produced from the investigation.

**What was done.** The test's schema surgery was wrapped in an explicit transaction that rolls back on exit, and a check was added afterwards that the constraint is present again. The local test database was repaired with one statement. This release also established the point-release numbering for small fixes.

**How it was proven.** The old form of the test was deliberately reinstated with the new check kept, and it failed, showing the check can tell the difference. The fix was restored, the suite passed, and the migration tests were run twice in a row to show nothing leaked between runs. The constraint was confirmed present afterwards.

**Status.** Resolved. A suggestion for a broader guard, a snapshot of all constraints before and after a run, is recorded in the backlog and not built.

*Technical detail:* build log, *Phase 8.5.1 — Migration-test Autocommit Fix (point release)*; combined prompt and plan `14-phase-8.5.1-migration-test-autocommit-fix.md`; report `14-phase-8.5.1-migration-test-autocommit-fix-report.md`; the test is `backend/tests/test_migration_0002.py`.

_Entries follow, in build order._
