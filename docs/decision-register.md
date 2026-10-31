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

<a name="r-04"></a>
### R-04 — Pinning the Mistral model to one named release

**TL;DR:** The system had been asking its second AI provider for "the latest large model" by a name the provider is free to repoint. The provider repointed it at a release the project's free account could not use, and a live run failed. The decision was to ask for one exact, dated release instead. That restored the name the prototype had been built against, but the next step showed the free account could not use that release either.

**Technologies:** Mistral's large model; the project's settings and settings template.

**Date and phase.** 14 September 2026, Phase 8.5.2.

**What happened.** A live run failed at the Validator with a refusal from the Mistral service: the requested model was not available on the account's tier. The configuration named a moving alias. When the project's key was first confirmed in May the alias pointed at a release the free tier allowed; the provider had since moved it to a newer release gated to paid accounts. Nothing on the project's side had changed.

**Why it mattered.** Two of the four agents depended on this provider by default. A moving name means the system's behaviour, and even whether it runs at all, can change without any change in the repository, which defeats the project's claim to be reproducible.

**What was decided, and by whom.** Dermot approved pinning both agents to the dated release the prototype was built and tuned against, as the cheapest of three options; adding a payment method and routing the two agents through Claude were both kept open. He also set the rule that archived prompts and plans naming the old alias stay unchanged, because rewriting them would falsify the record.

**What was done.** The two model names were changed in the settings and the settings template, in the tests that assert the defaults, and in a pricing example where a stale name would have silently made every call's cost unknown. Audit entries written from then on carry the dated name. The deployed verification was run by Dermot with a fresh claim.

**How it was proven.** The local suite passed unchanged. The deployed verification failed with the identical refusal: the dated release was gated on the free tier too. That the system had really sent the pinned name could be established only by elimination, because the audit entry records the model that answered and a refusal has no answer. That gap is the subject of R-05, and the provider question is settled in R-06.

**Status.** Partially resolved at the time; superseded by R-06. The pinned name remains in place for the retained Mistral path.

*Technical detail:* build log, *Phase 8.5.2 — Pin Mistral Model to `mistral-large-2512` (point release)*; plan `15-phase-8.5.2-pin-mistral-model-plan.md`; report `15-phase-8.5.2-pin-mistral-model-report.md`; the failing deployed run is `11f97ae8`.

<a name="r-05"></a>
### R-05 — Recording which model was asked, not only which answered; resetting the live database under a hostname check

**TL;DR:** The audit trail recorded the model that answered each request. When a request is refused there is no answer, so the record could not say what had been asked. This release added that, on every path. The build also departed from the brief's preferred design, for reasons recorded at the time, and reset the live database to a known state before testing.

**Technologies:** the audit entry format; the Neon hosted database; the project's seed script.

**Date and phase.** 14 September 2026, Phase 8.5.3.

**What happened.** The previous release's verification (R-04) could show which model the system had sent only by ruling out every other possibility, because the audit entry's model field is filled from the response and a refusal has no response. Separately, the deployed database had accumulated claims from failed runs and needed resetting to the nine seeded claims before a clean verification.

**Why it mattered.** An audit trail that cannot say what was asked when a call fails cannot settle a dispute with a provider, and the project's claim is that the audit trail alone explains every run, failures included. Resetting a live database is a destructive act, and the Phase 8.5 incident (R-02) had shown what a mis-pointed command could do.

**What was decided, and by whom.** Dermot approved the plan. The build then departed from the brief's stated preference, which was to pass the model name through as a separate value; the record explains why below. Dermot performed the deployed check himself through the live interface.

**What was done.** Every agent's audit entry gained the requested model, captured before the call so it is present on success, on an unreadable answer and on a refusal, and absent only when no call was made. Instead of a new parameter, the existing object that already carries the exact prompt was widened to carry the model too, so the recorded value is the sent value by construction and no lines were added to functions already over the project's size limit. The deployed database was reset after resolving its address through the application's own settings, comparing the hostname with the expected host, and printing the hostname only.

**How it was proven.** Nine new tests failed with the recording line temporarily removed and passed with it restored. Dermot's live run after the reset produced a Validator entry reading the pinned Mistral release beside the refusal, the evidence the previous release could not produce. The reset's before and after counts were recorded.

**Status.** Resolved. The requested-model field is a locked audit extension.

*Technical detail:* build log, *Phase 8.5.3 — Record `requested_model` in Agent Audit Payloads; Reset the Deployed DB (point release)*; plan `16-phase-8.5.3-requested-model-audit-and-db-reset-plan.md`; report `16-phase-8.5.3-requested-model-audit-and-db-reset-report.md`; the live run is `56a0d5b2`; the mechanism is `CapturedRequest` / `attach_request` in `backend/app/agents/_shared.py`.

<a name="r-06"></a>
### R-06 — Mistral withdrew its large model from the free tier; Claude Haiku became the default for all four agents, Mistral kept switchable

**TL;DR:** The second AI provider stopped letting the project's free account use its large model, under any name. Two of the four agents depended on it. The decision was to run all four on Claude by default and keep the Mistral route as a switch, so the system works today and the ability to swap providers stays demonstrable rather than theoretical.

**Technologies:** Claude Haiku; Mistral Large; a per-agent provider setting; the variant mechanism.

**Date and phase.** 14 to 15 September 2026, Phase 8.6.

**What happened.** The Phase 8.5.2 verification (R-04) and the audit entry from Phase 8.5.3 (R-05) established together that the Mistral service refused the project's free account for the large model whether asked by alias or by dated release. The provider's account pages gave no catalogue of what the free tier allowed. The Validator and Adjuster, both on Mistral by default, could not complete a run.

**Why it mattered.** The demonstration could not run end to end. Beyond that, the project's third-party register argues that any provider can be substituted through configuration; this was the first time that argument was tested by events rather than asserted.

**What was decided, and by whom.** Dermot, on 14 September, chose the Claude default over adding a Mistral payment method. At the plan's approval gate on 15 September he set the shape: a provider selector for each of the four agents, defaulting to Anthropic; the Mistral route kept as a named variant that a setting can make the default; an older Claude-only variant retired; the truthful provider label made a locked audit rule for every agent.

**What was done.** The selectors and the variant were built; the default build no longer constructs a Mistral client or requires its key. A finding during the work was fixed on the way: three agents had been writing a fixed provider name into the audit trail, so the swap alone would have labelled every Claude settlement as Mistral; all four now record the provider actually used. The production-target documents were annotated with the date and reason, not rewritten, because the target architecture still names Mistral.

**How it was proven.** Nineteen new tests, including one that fails if the default wiring is made to need a Mistral key. On 21 September the retained Mistral route was exercised live and aborted with the expected refusal, recorded in full in the audit trail, which is the substitutability argument demonstrated in both directions.

**Status.** Resolved. Re-enabling Mistral as the default is an open backlog item that needs only a setting.

*Technical detail:* build log, *Phase 8.6 — Validator and Adjuster Default to Claude Haiku; Mistral Path Retained as a Variant*; plan `17-phase-8.6-validator-adjuster-on-claude-haiku-plan.md` (*Plan decisions*); report `17-phase-8.6-validator-adjuster-on-claude-haiku-report.md`; the selectors are `llm.*_provider` in `backend/settings.py`; the variant is `v1_mistral` in `backend/app/orchestrator/variants.yaml`.

<a name="r-07"></a>
### R-07 — The live verification halted: a mis-written pattern treated ordinary prose as a policy citation

**TL;DR:** The first scenario of the live check, a claim that should settle on its own, was sent to a person instead. The Guardrail's pattern check had read the everyday phrase "one floor section with inventory" as a citation of a policy section. The pattern had been wrong since Phase 3 and never showed because the earlier model never wrote that way. The check was halted, not retried, and a one-line fix followed.

**Technologies:** the Guardrail's regular-expression check for policy citations; Claude Haiku as the new Adjuster.

**Date and phase.** 15 September 2026, Phase 8.6 verification; fixed in Phase 8.6.1 on 21 September 2026.

**What happened.** After the switch to Claude (R-06), the three scripted scenarios were run on the deployed system. The threshold and guardrail scenarios behaved as designed. The auto-approve scenario escalated, because the Guardrail's deterministic citation check flagged the Adjuster's sentence about the loss being contained to "one floor section with inventory and drying as primary components" as a reference to a policy section that did not exist. The pattern had been compiled case-insensitively as a whole, which also made the rule that a cited name must start with a capital letter match lowercase words, so any keyword followed by any word became a candidate.

**Why it mattered.** A guardrail that fails clean claims is as much a defect as one that passes bad ones: it would send every claim whose reasoning used an ordinary word like "section" to a person. The defect had been latent since Phase 3; the previous model's phrasing had never triggered it, which is the general lesson that a check tuned against one model's prose can fail on another's.

**What was decided, and by whom.** The halt rule was applied: no prompt change, no re-run, no adjustment, because the failure depended on phrasing and a pass on retry would have been false evidence. The deployed database was left as it stood, as the evidence. A narrow point release was recommended, and Dermot approved it with two decisions on the plan: scope the case-insensitivity to the keyword alone, and let a cited name begin with a digit as well as a capital, since numbered sections are the commonest shape of an invented citation.

**What was done.** One line changed in the rule engine. Seven tests were added, including the verbatim paragraph from the deployed run and the demonstration's planted endorsement read from its own file so the two cannot drift apart. One existing test that had never actually exercised the check was corrected. The Phase 8.6 report had stated that a numbered section still flagged under the recommended fix; that was wrong, the correction is in the record, and the report stands unaltered as history.

**How it was proven.** Reinstating the old pattern made the new tests fail with exactly the production flag text; restoring the fix made them pass. The full verification was then re-run from a fresh reset on 21 September 2026: all three scenarios as designed, seven audit entries each, and the chain verified end to end.

**Status.** Resolved. The lesson is recorded as a backlog item: test the rule engine against real reasoning from more than one model.

*Technical detail:* build log, *Phase 8.6* (*Deployed verification — HALTED*) and *Phase 8.6.1 — Guardrail Citation-regex False Positive (point release)*; plan `18-phase-8.6.1-guardrail-citation-regex-fix-plan.md`; report `18-phase-8.6.1-guardrail-citation-regex-fix-report.md`; the halted run is `8bff04e2`; the pattern is `_CITATION_CANDIDATE_RE` in `backend/app/agents/guardrail_rules.py`.

<a name="r-08"></a>
### R-08 — Three findings from the 21 September verification, ruled findings rather than halts and left open

**TL;DR:** The live check that closed the Guardrail fix also found three problems nobody had seen: five of the six background claims cannot complete; a claim the Validator judges not covered aborts instead of going to a person; and the search for policy passages missed the right one for a theft claim. None was caused by the fix and none touches the three scripted scenarios. Dermot ruled them findings to record, not reasons to stop, and they remain open.

**Technologies:** the market-data table; the orchestrator's handling of a coverage denial; vector retrieval over the policy passages.

**Date and phase.** 21 September 2026, Phase 8.6.1 verification.

**What happened.** Steps of the verification beyond the three scenarios exercised background claims for the first time. One background claim aborted at the Adjuster because its type of loss has no entry in the market-data table; five of the six background claims share that fate. On another, a stricter-Validator replay returned "not covered"; the orchestrator ran the Adjuster anyway, the model correctly proposed nothing, and the run aborted because a zero settlement is rejected, leaving the claim marked as if coverage had been confirmed. On the same claim, retrieval never fetched the passage that lists covered perils, which is what drove the denial.

**Why it mattered.** In a demonstration, pressing the process button on most background claims aborts. A coverage denial is a decision a person must see, and the system turns it into an error. A status that says the opposite of the recorded verdict is a small falsehood in the record. None of these is hidden, but all are visible to anyone who strays from the three scripted claims.

**What was decided, and by whom.** Dermot ruled during the verification that the abort was a new finding and not a halt on the release under test, because the halt rule covers the three scripted scenarios and the abort was a missing branch, not a regression. All three findings were written into the backlog with scope notes, including the instruction not to fix the denial path by accepting a zero settlement, which would turn a visible abort into a silent nothing.

**What was done.** Nothing in code. The findings were recorded with the runs that exposed them, and the demonstration guidance says to stay off the background claims.

**How it was proven.** Not applicable; these are open findings. Each is tied to a recorded run whose audit trail shows the behaviour.

**Status.** Open. The denial path is noted as an interface-stability event for whichever phase takes it, since a run that skips two agents writes fewer audit entries.

*Technical detail:* build log, *Phase 8.6* amendment *Deployed verification outcome (21 September 2026)*, findings F1 to F3; backlog, *Findings from the 21 September 2026 verification*; runs `765f1ad2` (abort on lookup) and `74513bca` (denial path).

<a name="r-09"></a>
### R-09 — Azure foundation decisions: the service's own identity, building the image in the cloud registry, and baking the embedding model into the image

**TL;DR:** Standing the prototype up on Azure forced four design choices before anything was built. The service gets an identity of its own kind that can be referenced before it exists; the container image is built inside Azure's registry rather than on a laptop; the language-understanding model the service needs is packed into the image so the running service never fetches anything from the internet; and database sign-in by password is accepted for now with the stronger option deferred.

**Technologies:** Azure user-assigned managed identity; Azure Container Registry builds; a Docker image with the BGE embedding model baked in; Azure Key Vault secret references.

**Date and phase.** 1 October 2026, Phase 9.1, approval gate.

**What happened.** The brief described the service with a system-assigned identity, the simpler kind that is created with the service. Investigation before planning showed that the platform validates the service's references to Key Vault secrets and to the registry at deployment time, and a system-assigned identity does not yet exist at that moment, so the references cannot be created in the same pass. Separately, the embedding model, which turns text into the numbers used to search the policy, is normally downloaded at first use; a service in a regulated environment should not depend on reaching the model's publisher at runtime.

**Why it mattered.** Each choice is a one-way door for the deployment. The identity type decides whether the whole environment can be created in one description or needs manual steps between passes. Where the image is built decides whether a developer's machine is part of the production path. Whether the model is fetched or baked decides whether the service has an undeclared network dependency.

**What was decided, and by whom.** Dermot approved the plan with four numbered decisions: a user-assigned identity instead of the brief's wording; the processor library pinned to a CPU-only build on Linux, with confirmation that the Mac's resolution was unchanged; sign-in to the database by password with the connection string in the vault, the directory-based option deferred and recorded as a gap; and the model baked into the image with network access to its publisher switched off at runtime, so a missing model fails loudly rather than being silently fetched. The image is built by the registry's own build service, never on a laptop; the record presents this as the plan from the start and says nothing about a free-trial restriction forcing it.

**What was done.** The Bicep files, the two-stage image build, the start and stop scripts and the pinned processor library were built as approved. The platform preview and two deployment passes were run, the database bootstrapped under a hostname check, and the three scenarios verified.

**How it was proven.** The deployment succeeded in two passes with the service resolving its vault references at start; the processor pin was proven not to change the Mac's resolution by comparing exported dependency lists; the baked model served the scenarios with external access disabled. Cold start from zero was measured at 28 seconds.

**Status.** Resolved. The deferred directory-based database sign-in and the absence of private network endpoints are recorded gaps in the architecture reference.

*Technical detail:* build log, *Phase 9.1 — Azure Foundation* (*What was built*, *Deployment*, *Issues and deviations*); plan `19-phase-9.1-azure-foundation-bicep-container-apps-plan.md` (§0 findings, §5 identity, *Approval*); report `19-phase-9.1-azure-foundation-bicep-container-apps-report.md`; `infra/bicep/`, `Dockerfile`.

<a name="r-10"></a>
### R-10 — Parking the Azure stack: the replica that outlived the stop, and the database that restarts itself after seven days

**TL;DR:** To keep costs down, the Azure installation is switched off between demonstrations by a script. Two things about switching off turned out not to be what the script's own description claimed. The last running copy of the service stayed up for several minutes after the database had stopped. And the platform silently restarts a stopped database after seven days, so "parked" does not stay parked.

**Technologies:** Azure Container Apps scale-to-zero; Azure Database for PostgreSQL Flexible Server stop and start.

**Date and phase.** 1 October 2026, Phase 9.1 (the replica); 26 October 2026, Phase 9.2 (the restart).

**What happened.** On 1 October the stop script set the service's minimum copies to zero and then stopped the database. Setting the minimum to zero permits the service to scale down but does not stop a copy that is already running; the one that had served the scenarios stayed up for its five-minute cooling-off period and outlived the database by about that long. It was idle and nothing failed, but the script's header said the service went down first, which was not true. On 26 October the database was found running although it had been stopped on 1 October; the platform's log showed the stop had succeeded and the platform itself had restarted the server around 8 October, as it does to any Flexible Server stopped for seven days.

**Why it mattered.** A parking procedure whose description does not match its behaviour will mislead the next person to run it, and a database that quietly restarts itself incurs cost and leaves the system in a state the handbook does not predict.

**What was decided, and by whom.** The script's description was corrected at once in Phase 9.1, and making the script wait for the last copy to drain was recorded as a follow-on rather than changed on the spot, because it is a behaviour change. In Phase 9.2 Dermot directed that the database be left running for the session and that the stop script be the last act of every Azure session, and the seven-day restart was written into the handbook as something to check at the start of each session. The wait-for-drain was built in Phase 9.2.

**What was done.** The stop script now polls until no copy of the service is running, for up to seven minutes, and aborts leaving the database running if the copy never drains. Every session since records the parked time and the expected auto-restart date in the handbook and the build log.

**How it was proven.** Observed directly: the 1 October stop and start round trip recorded the timings and resulting states; the 26 October session found the database running and the platform log explained why; the stop script's drain wait has been observed completing in later sessions, for example after 285 seconds on 30 October.

**Status.** Resolved for the script; the seven-day restart is a platform behaviour that is worked around, not removed.

*Technical detail:* build log, *Phase 9.1* (*Issues and deviations*, *Stop/start round trip*) and *Phase 9.2* (*Findings that shaped the work*, *Parking*); `scripts/azure-stop.sh`, `wait_for_zero_replicas` in `scripts/azure-common.sh`.

_Entries follow, in build order._
