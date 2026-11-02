# Decisions and incidents, in plain language

## What this document is

This is the record of every moment in the build of this system when something went wrong, when the work departed from its plan, or when a decision had to be taken by the person accountable for it. It is written for a reader who is not an engineer and does not want to read code: a compliance officer, an auditor, a hiring manager, or a future maintainer arriving cold. Each entry says what happened, why it mattered, what was decided and by whom, what was done, how it was shown to have worked, and where the engineer's detailed record is.

The project's claim is that software built with an AI assistant can be governed and inspected. A claim like that needs a record a non-engineer can inspect without someone beside them. This is that record. The engineer's record remains in three technical places, and every entry here ends with a pointer into it.

The rule from Prompt 23 onward is that every halt, every deviation from an approved plan, every incident and every decision taken at an approval gate produces an entry here before the phase that contains it is closed. Entries before that date were written afterwards from the technical record, and say so where the record is silent.

## Glossary

A handful of project terms recur throughout. They are defined here once, by what they do, and used consistently below.

**The system.** The working claims-handling system this project built. It is a prototype in scope, with synthetic claims and a short policy excerpt, and it is built and operated to production standards: deployed on two clouds, audited, verified and change-controlled.

**Agent.** One of the four specialised pieces of software in the system, each with a single job, each calling a language model to do it.

**Doc-Parser, Validator, Adjuster, Guardrail.** The four agents. The Doc-Parser reads the claim. The Validator decides whether the policy covers the loss. The Adjuster proposes a settlement figure and gives its reasons. The Guardrail checks the Adjuster's reasons for leaked personal data, for bias, and for references to policy wording that the policy does not contain.

**Orchestrator.** The part of the system that runs the four agents in order and applies the escalation rules at the end.

**Language model**, or **the model**. The external artificial-intelligence service each agent calls. The system uses Anthropic's Claude models. An alternative provider, Mistral, is kept available as a switch.

**Prompt.** The written instructions an agent sends to the model with each request. There are two kinds: the fixed instructions that define the agent's job, and the per-claim content that changes every time.

**Retrieval (and embedding).** The policy text is cut into short passages. Each passage is turned into a long list of numbers by a small, fixed model, so that passages with similar meaning end up with similar numbers, and those numbers are stored in the database beside the text. When a claim arrives its description is turned into numbers the same way, and the database returns the few passages whose numbers are nearest, so the Validator sees the relevant part of the policy rather than the model's general memory of insurance. The same fixed model must be used for both steps, which is why it is pinned and packed into the deployed image.

**Audit trail.** The tamper-evident record of everything each run did: every agent's input, its output and its call to the model, chained together so that any later alteration is detectable. The project's rule is that the audit trail alone must be enough to explain any past decision.

**Human review**, or **escalation**. The outcome in which the system stops and hands the claim to a person, recording which rule sent it there.

**The three scripted scenarios.** The three synthetic claims that every verification runs. A water-damage claim that should settle automatically. A fire claim large enough that a person must see it. And a claim whose reasoning cites a policy endorsement that does not exist, which the Guardrail must catch.

**Deployed stacks.** The two live installations of the same code: the original, hosted on Render, Vercel and Neon, which is the demonstration's home; and the Azure installation added in Phase 9.

**Approval gate.** The point in every phase where the written plan is put to Dermot, the person accountable for the project, and nothing is built until he approves it. Decisions taken there are recorded in the plan.

**Replay.** Re-sending a recorded prompt to the model to see whether its answer has changed. Since Phase 9.2.1 a set of recorded runs is replayed before every demonstration.

**MCP, or a connector.** The Model Context Protocol, a standard way for an AI assistant such as Claude to call a system's functions and read the answers. Since Phase 10 the system offers a small set of such functions, every one answered from the audit trail; a *connector* is the assistant's side of that link, and a shared token is what lets it in.

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

**TL;DR:** The system had been asking its second AI provider for "the latest large model" by a name the provider is free to repoint. The provider repointed it at a release the project's free account could not use, and a live run failed. The decision was to ask for one exact, dated release instead. That restored the name the system had been built against, but the next step showed the free account could not use that release either.

**Technologies:** Mistral's large model; the project's settings and settings template.

**Date and phase.** 14 September 2026, Phase 8.5.2.

**What happened.** A live run failed at the Validator with a refusal from the Mistral service: the requested model was not available on the account's tier. The configuration named a moving alias. When the project's key was first confirmed in May the alias pointed at a release the free tier allowed; the provider had since moved it to a newer release gated to paid accounts. Nothing on the project's side had changed.

**Why it mattered.** Two of the four agents depended on this provider by default. A moving name means the system's behaviour, and even whether it runs at all, can change without any change in the repository, which defeats the project's claim to be reproducible.

**What was decided, and by whom.** Dermot approved pinning both agents to the dated release the system was built and tuned against, as the cheapest of three options; adding a payment method and routing the two agents through Claude were both kept open. He also set the rule that archived prompts and plans naming the old alias stay unchanged, because rewriting them would falsify the record.

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

**TL;DR:** Standing the system up on Azure forced four design choices before anything was built. The service gets an identity of its own kind that can be referenced before it exists; the container image is built inside Azure's registry rather than on a laptop; the language-understanding model the service needs is packed into the image so the running service never fetches anything from the internet; and database sign-in by password is accepted for now with the stronger option deferred.

**Technologies:** Azure user-assigned managed identity; Azure Container Registry builds; a Docker image with the BGE embedding model baked in; Azure Key Vault secret references.

**Date and phase.** 1 October 2026, Phase 9.1, approval gate.

**What happened.** The brief described the service with a system-assigned identity, the simpler kind that is created with the service. Investigation before planning showed that the platform validates the service's references to Key Vault secrets and to the registry at deployment time, and a system-assigned identity does not yet exist at that moment, so the references cannot be created in the same pass. Separately, the embedding model, which turns text into the numbers used to search the policy, is normally downloaded at first use; a service in a regulated environment should not depend on reaching the model's publisher at runtime.

**Why it mattered.** Each choice is a one-way door for the deployment. The identity type decides whether the whole environment can be created in one description or needs manual steps between passes. Where the image is built decides whether a developer's machine is part of the production path. Whether the model is fetched or baked decides whether the service has an undeclared network dependency.

**What was decided, and by whom.** Dermot approved the plan with four numbered decisions: a user-assigned identity instead of the brief's wording; the processor library pinned to a CPU-only build on Linux, with confirmation that the Mac's resolution was unchanged; sign-in to the database by password with the connection string in the vault, the directory-based option deferred and recorded as a gap; and the model baked into the image with network access to its publisher switched off at runtime, so a missing model fails loudly rather than being silently fetched. The image is built by the registry's own build service, never on a laptop; the written record presents this as the plan from the start and says nothing about a free-trial restriction forcing it. **Dermot's recollection, recorded as such on 31 October 2026:** the decision to build in Azure's registry rather than locally was taken on 21 September 2026 to avoid making Docker Desktop a prerequisite; on 1 October the free-trial subscription refused registry build tasks, and Dermot upgraded the subscription to Pay-As-You-Go that day to proceed, keeping the remaining credit. The handbook's note that the subscription has been Pay-As-You-Go since 1 October is consistent with this.

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

<a name="r-11"></a>
### R-11 — The build had been red since 15 June and nobody could have deployed from it; fixed in two steps, the first with the wrong tool version

**TL;DR:** Every automatic check on the shared build server had been failing for four months, on the interface half only, because a list of dependencies had drifted out of step with its source. Nobody noticed because nothing depended on it. The new deploy-on-push feature would depend on it, so it had to be fixed first. The first fix used a newer tool than the server, and failed too.

**Technologies:** GitHub Actions; the npm package manager and its lock file; Node.js versions 20 and 24.

**Date and phase.** Found 26 October 2026 while planning Phase 9.2; red since 15 June 2026 (Phase 6).

**What happened.** The interface's dependency lock file had been out of step with its manifest since Phase 6. The server's install step refuses such a mismatch, so the interface job failed on every run since June while the service job passed. The new deploy workflows were designed to run only after a green build, so a red build meant they could never fire. The lock file was regenerated, but with npm 11 on Node 24, which omits entries that the server's npm 10 on Node 20 requires; the build stayed red on that push and the next.

**Why it mattered.** A continuous-integration check that is permanently red is worse than none, because it is ignored. Phase 0 had met the same class of problem on day one and fixed it; nothing had kept it fixed.

**What was decided, and by whom.** Dermot approved the lock file regeneration as the first commit of Phase 9.2, before any Azure work, because the deploy gate would otherwise be meaningless.

**What was done.** The lock file was regenerated a second time with the server's own npm version, verified locally under Node 20, and the rule written into the handbook: regenerate with npm 10 until the server's Node version changes.

**How it was proven.** The build went green on the second regeneration and the interface deploy ran for the first time. The first, wrong regeneration is recorded as a correction so the mistake is not repeated.

**Status.** Resolved.

*Technical detail:* build log, *Phase 9.2* (*Findings that shaped the work*, *CI lockfile*); commits `dcc52bd` (npm 11, wrong), `3abad04` (npm 10, correct); `frontend/package-lock.json`.

<a name="r-12"></a>
### R-12 — The interface host was refused in West Europe; East US 2 accepted, holding only static files

**TL;DR:** The hosting service for the web interface is not offered in the region where everything else lives, and the nearest alternative refused new customers. The interface was placed in a United States region instead. It holds only the static web pages, never any claim data, which stays in North Europe.

**Technologies:** Azure Static Web Apps.

**Date and phase.** 26 October 2026, Phase 9.2.

**What happened.** The interface hosting service is offered to this subscription in five regions, none of them North Europe. A preview deployment to West Europe was refused with the message that the region was not accepting new customers. A preview to East US 2 was accepted.

**Why it mattered.** The project's architecture keeps all data in one European region. Placing a component elsewhere needs a clear statement of what that component holds.

**What was decided, and by whom.** Dermot approved East US 2 at the approval gate as the one resource outside North Europe, on the basis that it holds the compiled interface files and deployment metadata only, served from a global edge, and that every resource holding data stays in North Europe.

**What was done.** The region was set as a parameter, the reason recorded in the infrastructure notes, and the handbook's description of the deployment states the exception.

**How it was proven.** The deployment succeeded; the interface served from the new host and reached the service in North Europe across origins, which the second verification pass exercised through the browser.

**Status.** Resolved, as a recorded exception to the single-region rule.

*Technical detail:* build log, *Phase 9.2* (*Findings that shaped the work*); plan `20-phase-9.2-static-web-apps-oidc-deploy-app-insights-plan.md` (*Approval*, decision 4); `staticWebAppLocation` in `infra/bicep/main.bicepparam`.

<a name="r-13"></a>
### R-13 — How a push was allowed to deploy to Azure: no cloud-written workflow files, no stored credential, infrastructure kept out of the pipeline

**TL;DR:** Letting a code push deploy itself to a cloud platform means giving an automated process the right to change that platform. Three decisions limited what it may do and how it proves who it is: the project writes and reviews its own deployment steps rather than accepting ones the platform generates; the process proves its identity with a short-lived token instead of a stored password; and it may update the running service but may not change the infrastructure around it.

**Technologies:** GitHub Actions workflows; OpenID Connect federation to a second Azure managed identity; Azure role assignments scoped to the registry and the service.

**Date and phase.** 26 October 2026, Phase 9.2, approval gate.

**What happened.** The interface hosting service offers to connect itself to the repository and write a deployment workflow into it. The service deployment needs cloud rights from the build server. Both are conveniences that widen what an automated process can do without review.

**Why it mattered.** A regulated insurer would ask exactly these questions of any deployment pipeline: who wrote the steps, how does the process authenticate, and what is the blast radius if it is compromised.

**What was decided, and by whom.** Dermot approved three decisions. First, no platform-written workflow files: the interface host is created with no repository link, and both deploy workflows are written and reviewed in the repository; the one manual step is pasting the host's upload token into the repository's secrets. Second, the process proves itself by OpenID Connect to a second managed identity created for the purpose, with no application registration and no stored secret; the identifiers it needs are stored as plain variables because they are not secrets. Third, the service workflow does not run the infrastructure description: it builds the image in the registry and points the existing service at it, under exactly three rights scoped to the registry and the service; infrastructure changes stay an operational act from a developer's shell, because the parameter file reads its secrets from that shell. The deployer and the running service have disjoint rights.

**What was done.** The second identity, its federation and its three role assignments were added to the infrastructure description; the two workflows were written to trigger only after a green build; the frontend workflow needs no cloud sign-in at all.

**How it was proven.** The gate was shown working when a red build skipped both deploys; the service deploy ran green end to end on a later push; an additional right the plan had held in reserve turned out not to be needed and was not granted.

**Status.** Resolved. Recorded as locked decisions in the handbook.

*Technical detail:* build log, *Phase 9.2* (*What was built*, *Deployment*); plan `20-phase-9.2-static-web-apps-oidc-deploy-app-insights-plan.md` (*Approval*, decisions 1 to 3); `.github/workflows/deploy-backend.yml`, `deploy-frontend.yml`; `infra/bicep/modules/deployer-identity.bicep`.

<a name="r-14"></a>
### R-14 — A correct deployment reported as failed: the check read a two-line answer as one

**TL;DR:** The first automatic deployment of the service to Azure succeeded, but the step that confirms success reported failure. The confirmation asked the platform two questions at once and received two lines back, but read only the first, so the second always looked blank and the check could never pass.

**Technologies:** GitHub Actions; the Azure command-line tool's query output.

**Date and phase.** 26 October 2026, Phase 9.2.

**What happened.** On the first green build after the lock file fix (R-11), the service deploy workflow built the image, updated the service, and saw it healthy with full traffic on the new image. Its final verification step then failed. The step requested two revision names in one query and the tool printed them on two lines; the shell read them as one name and an empty one, so the equality it tested was always false.

**Why it mattered.** A deployment check that fails when the deployment is good trains people to ignore it, which is the same failure as R-11 in a different place.

**What was decided, and by whom.** Fixed as part of the phase, in the shared script the workflow calls, and verified from a shell against the live service before being pushed. The record does not name a separate decision.

**What was done.** The query was changed to join the two names on one line. The fix was checked against the live service with a matching image, returning success, and a stale image, returning the expected mismatch message.

**How it was proven.** The push carrying the fix changed nothing under the service's own files, so the workflow correctly reported nothing to deploy, which proved the change detection. The next real service change, the telemetry fix (R-15), ran the corrected step green end to end.

**Status.** Resolved.

*Technical detail:* build log, *Phase 9.2* (*Deployment*, *`require_active_image`*); commit `8d211ad`; `require_active_image` in `scripts/azure-common.sh`; workflow run 40362374360 (the false red).

<a name="r-15"></a>
### R-15 — Telemetry recorded nothing because of the order in which two pieces of code loaded

**TL;DR:** Monitoring was switched on and showed the service's calls to the database and to the AI provider, but no incoming requests at all. The monitoring library works by swapping in an instrumented version of the web framework when it starts, but the service had already taken hold of the original version before that happened. A one-line change made the service pick up whichever version is current when it builds.

**Technologies:** Azure Application Insights; the Azure Monitor OpenTelemetry distribution; FastAPI.

**Date and phase.** 26 October 2026, Phase 9.2.

**What happened.** After deployment, the monitoring workspace held outgoing dependency records but no request records. The monitoring distribution instruments the web framework by rebinding the framework's main class to an instrumented subclass. The service's entry module had imported the original class at load time, before the monitoring was configured, so every application it built was uninstrumented.

**Why it mattered.** Request telemetry is the view an operator uses first; dependencies without the requests that caused them are hard to read, and a monitoring claim in the architecture document would have been false.

**What was decided, and by whom.** Fixed within the phase; the record does not name a separate decision.

**What was done.** The entry module now looks the framework class up at the moment it builds the application rather than at import time, with comments naming the real mechanism. A test rebinds the class the way the instrumentor does and asserts the application is built from the replacement; reinstating the import-time binding makes it fail.

**How it was proven.** After the fix, a probe of the agent test bench appeared in the monitoring workspace as one request with its database and AI-provider calls as children, with route templates rather than raw identifiers and the health check excluded as configured.

**Status.** Resolved.

*Technical detail:* build log, *Phase 9.2* (*FastAPI request telemetry fix*, *Application Insights observation*); commit `2b662da`; `create_app` in `backend/app/main.py`; `backend/app/telemetry.py`; test `test_create_app_builds_the_class_the_distro_installs`.

<a name="r-16"></a>
### R-16 — The pinned model changed its verdict on identical input between 1 and 26 October; proven by replay; entered in the governance and third-party registers

**TL;DR:** The claim that should settle on its own was sent to a person, twice, by the Guardrail's AI check. Nothing in the project had changed. Sending the exact recorded instructions from a run that had passed on 1 October back to the same named model showed it now failed them too. The model behind a fixed name had changed its behaviour. The audit trail is what made that provable.

**Technologies:** Claude Haiku under a fixed model identifier; the recorded prompts in the audit trail; replay at temperature zero.

**Date and phase.** 26 October 2026, Phase 9.2 second verification pass.

**What happened.** Both auto-approve runs through the Azure interface ended in human review on a Guardrail failure raised by its AI check alone; the deterministic checks found nothing. The flags treated the Adjuster's own vocabulary, such as "moderate-severity band" and "market range", and a paraphrase of the loss as citations of policy wording. The exact instructions recorded in the audit trail were re-sent to the same model identifier from a laptop, without the new monitoring packages: that day's prompt failed five of five times, and the 1 October prompt, which had passed then, failed three of three.

**Why it mattered.** A pinned model identifier is treated as a guarantee of stable behaviour. It is not. None of the project's change controls could have caught this, because there was no change on the project's side to classify. The same model and prompts serve the original demonstration platform, so the demonstration was affected everywhere.

**What was decided, and by whom.** Dermot ruled the second pass passed for the deployment, with this as an explicit recorded exception, since the deployment itself behaved correctly. He directed that the finding be entered in the change-governance document as an observed case of third-party behaviour change, and in the third-party register against the provider, and that the response be its own phase.

**What was done.** The investigation, replays and conclusion were written into the build log; the governance document gained a section on what production adds, a scheduled evaluation against the live model; the register's provider row gained the observed change; two backlog items were raised and became Phase 9.2.1.

**How it was proven.** By the replays themselves: byte-identical recorded input, same model identifier, different verdict on two dates. The audit trail's recording of the exact prompt and the requested model, added in Phases 8.3 and 8.5.3, is what made the replay possible and ruled out the deployment as the cause.

**Status.** Resolved as a finding; the response is R-17 and R-18.

*Technical detail:* build log, *Phase 9.2* (*Recorded exception — the Guardrail's verdict changed under an unchanged model id*); `docs/change-governance.md` (*Observed in the prototype*); `docs/dora-third-party-register.md` (Anthropic row); runs `8590b47e`, `f02fb888` (26 October) and `08d514f2` (1 October).

<a name="r-17"></a>
### R-17 — Phase 9.2.1: narrowing the Guardrail's question, the "market range" finding, a revised decision on the wording, new escalations on two other paths, and a close as partially verified

**TL;DR:** The response to the model changing its mind (R-16) was to ask it a much narrower question: name only policy provisions cited by title or number, and never judge coverage. That removed most of the false alarms but not the one on the phrase "market range". A further change to the per-claim wording cleared every recorded case, and all three scenarios passed on Azure. Then two other paths to the same system escalated on phrases nobody had seen before. The release was closed as only partly successful, with the failing runs kept as tests that stay red until the real fix.

**Technologies:** the Guardrail's system and per-claim instruction files; Claude Haiku at temperature zero; a corpus of seven recorded runs replayed live; a read-only extraction script against the Azure and Neon databases; an infrastructure parameter and a hosting-dashboard variable for the Adjuster's temperature.

**Date and phase.** 28 to 30 October 2026, Phase 9.2.1.

**What happened.** The instructions were rewritten to define a citation as a provision named by title or number, to list what is not a citation, and to state that coverage had already been decided upstream. Replaying the recorded runs showed two of the three failure modes gone and one remaining: texts containing the literal phrase "market range" still failed, with the model conceding in its own words that the phrase was settlement methodology and flagging it anyway. A scratch experiment on the per-claim wording found that removing a heading's claim that the retrieved passages were "the only authoritative source", together with a reworded task line, cleared every case while the invented-endorsement case still flagged. Deployed, all three scenarios passed through the Azure interface for the first time since 1 October. The same day the verification script against the original platform escalated on "supply line"; the next day the original platform's interface escalated on "$200,000 ceiling", the Adjuster's own market-band ceiling.

**Why it mattered.** Each path produced a different Adjuster text, and the model's verdict was sensitive to wording that no instruction could anticipate. A fix that holds only for the texts one has seen is not a fix.

**What was decided, and by whom.** Dermot approved the plan on 28 October with five decisions, one of which was that the per-claim wording would not change. On 29 October, shown the experiment's results, he revised that decision and adopted the two-line change, recording why in the plan's approval section. He chose to set the Adjuster's temperature to zero on both deployed systems through their configuration, leaving the committed default alone. On 29 October he closed the release as partially verified, directed that the failing run be committed as a test expected to pass and therefore red on purpose, and scheduled the next release. On 30 October he directed that the second failing run join it and that the documentation state plainly that the scenario was unreliable on every path.

**What was done.** The two instruction files were changed; the replay corpus, its contract tests and the extraction script were built; the temperature was set on both stacks; the two failing runs were extracted read-only and committed as fixtures.

**How it was proven.** Before and after replays, three repetitions each at temperature zero, recorded case by case; the model was deterministic across repetitions throughout. The deployed verification: three for three through the Azure interface, two of three through the script, and the second interface path failing too. The replay reproduced both new failures three of three.

**Status.** Partially resolved; superseded by R-18, which made the corpus green.

*Technical detail:* build log, *Phase 9.2.1 — Guardrail False Positives on the Auto-approve Scenario (point release)* (the mutation-proof table, the template experiment table, *Close-out*, *Addendum — 30 October 2026*); plan `21-phase-9.2.1-guardrail-false-positive-fix-plan.md` (*Approval*, D5 revised); report `21-phase-9.2.1-guardrail-false-positive-fix-report.md`; fixtures under `backend/tests/fixtures/guardrail_replay/`; runs `8e886c66` (script, 29 October) and `2c42cf40` (Vercel, 30 October).

<a name="r-18"></a>
### R-18 — Phase 9.2.2: the decision moved into code; the conflict in the brief and how it was resolved; verified on all three paths

**TL;DR:** The Guardrail's AI check keeps its job of spotting a suspicious reference but loses the power to fail a claim on its own say-so. It must quote the words it objects to; code checks the quote is really in the Adjuster's reasoning and really looks like a named provision. Refusals are recorded, not hidden. The brief contained a contradiction about where the quote should be stored, which was found in planning and settled before any code was written. Verified on all three paths the same day.

**Technologies:** a verification function reusing the rule engine's provision pattern; two additive fields on the Guardrail's audit entry; a quote field in the model's required output.

**Date and phase.** 30 October 2026, Phase 9.2.2.

**What happened.** Planning found that the brief expected the new quote field on the flag's data model and also forbade any change to the service's responses, but that data model is rebuilt from the audit trail for the runs interface, returned by the agent test bench and carried in the live event stream, so adding a field to it would change all three. Planning also found that the rule engine's own pattern, run over all seven recorded reasonings, matched nothing in the six that should pass and exactly one span in the invented-endorsement case, which meant a code check using that pattern would be deterministic for every known case.

**Why it mattered.** Two prompt-only fixes had each held for the texts they were tested on and failed on the next. A check in code cannot be moved by the model changing its mind, and the audit trail gains the model's claim and the code's refusal side by side on every run, which is what an auditor would want to see.

**What was decided, and by whom.** Dermot approved the plan with five decisions: the flag model untouched and the quote held in the audit trail only; the verified quote recorded for accepted flags as well as refused ones, so the audit holds the evidence for acceptances too; the normalisation rules for locating the quote; a new module rather than growing the existing one; and the replay test judging the agent's verdict rather than the model's raw claims. He asked to be present for the deployed verification on all three paths.

**What was done.** A verification module was built: the quote is stripped of wrapping punctuation, located in the reasoning with tolerance only for case, whitespace and quote glyphs, and the reasoning's own span, not the model's string, is tested against the provision pattern; the first failing check names the reason, and refused claims are recorded and logged, never raised. The model's output format gained the quote field with one rule. Thirty-seven tests were added.

**How it was proven.** Mutation proof: with the verifier neutered 18 tests failed; with the old instructions restored the output-format test failed. The replay corpus went from seven of eight to eight of eight. Deployed, all three scenarios ran as designed through the Azure interface, the original interface and the script; the original interface produced three new model objections, each refused as not a provision and each recorded with the model's own words and the reason.

**Status.** Resolved. The audit extension is recorded as a locked interface change.

*Technical detail:* build log, *Phase 9.2.2 — the LLM citation flag must quote its evidence, and code verifies it (30 October 2026)*; plan `22-phase-9.2.2-guardrail-quote-verified-citation-flags-plan.md` (§0 findings, *Approval*); report `22-phase-9.2.2-guardrail-quote-verified-citation-flags-report.md`; `backend/app/agents/guardrail_llm_flags.py`; audit keys `llm_flags_counted`, `llm_flags_discarded`; refused runs `0cdfa114`, `4142f33b`, `6197d116`.

<a name="r-19"></a>
### R-19 — Phase 9.2.2's accepted trade-off: a citation written without a provision keyword no longer counts from the model's check alone

**TL;DR:** Making the model's objection verifiable has a cost. If the Adjuster ever cited a non-existent provision without using one of the recognised words, such as "endorsement" or "section", the model's check could notice but could no longer fail the claim by itself. Dermot accepted this knowingly, and said where the fix would go if it ever mattered.

**Technologies:** the rule engine's provision pattern, used as the oracle for the model's quotes.

**Date and phase.** 30 October 2026, Phase 9.2.2, approval gate.

**What happened.** The code check accepts a quote only if the span of reasoning it points at has the shape the deterministic check recognises: a provision keyword followed by a capitalised or numbered name. A quote such as "the coastal surge rider" in lower case, with no keyword, would be refused as not a provision even if the model were right that no such rider exists. The plan named this before any code was written, and named the one risk to the acceptance test: if the model quoted the demonstration's invented endorsement without its keyword, that test would go red for this reason.

**Why it mattered.** A standing limitation should be findable on its own by a reviewer, not buried inside the entry for the release that introduced it.

**What was decided, and by whom.** Dermot accepted the trade-off at the gate: if the risk materialised, report it as observed and do not widen the pattern within the release. He confirmed that the deterministic pattern is the place to widen if a real citation is ever missed, not the model's check, because a widening there is reviewable and testable where a looser model check is not.

**What was done.** The limitation is recorded in the plan, the backlog and the handbook's description of the Guardrail.

**How it was proven.** On the day, the risk did not materialise: the model quoted the invented endorsement with its keyword in every repetition, and the no-rule-engine test passed three of three. The limitation remains by design.

**Status.** Open by design; a documented limitation, not a defect.

*Technical detail:* plan `22-phase-9.2.2-guardrail-quote-verified-citation-flags-plan.md` (§2 property, §5, *Approval*); backlog, the closed *Findings from the 26 October 2026 verification* section; `CLAUDE.md` → *Escalation policy*.

<a name="r-20"></a>
### R-20 — Phase 10's two decisions at the gate: who may ask the system questions, and what a question may do

**TL;DR:** The system was given a way for an AI assistant such as Claude to ask it questions about a claim and get answers from the audit trail. Two decisions shaped it. Only a holder of a shared secret may connect, and with no secret configured there is no door at all. And a question may only read, except for one action: running one of the three rehearsed scenarios. Decided on Monday 2 November 2026; the live check with Dermot present is still to come.

**Technologies:** the Model Context Protocol (MCP) and its Python library; a bearer token; a new database table for the access record.

**Date and phase.** 2 November 2026, Phase 10, approval gate.

**What happened.** Phase 10 adds an MCP endpoint inside the backend so that a claims manager or an auditor can ask, in natural language, why a claim settled or escalated, and get an answer drawn only from what the agents recorded. The plan had to settle how a client proves it may connect, and what a connected client may do. It also found, while planning, that the prompt's worked example had attached one run's refused phrase to another run; the plan corrected it from the recorded data.

**Why it mattered.** An AI assistant with a tool that could change a claim would be a new decision-maker outside the audited pipeline. An endpoint reachable without a secret would expose synthetic but realistic claims to anyone. And an access path that left no record would be the one part of the system a reviewer could not reconstruct.

**What was decided, and by whom.** Dermot, at the gate, as the plan recommended: the endpoint exists only when a shared token is configured, with no anonymous mode and no switch to create one; every call must present that token; eight tools read, one runs a scripted scenario, and there is no tool for the human approve-or-reject decision or the agent test bench; every call is recorded in its own table, kept out of the audit chain because questions about the record are not decisions in it. Also decided: the library's own OAuth-shaped sign-in is not used (the prototype has no sign-in service to point it at), the library's localhost-only host check is switched off for this endpoint because the hosting platforms own the host name and the token is the control, and the demonstration compares the two Harborline runs of 30 October on the Render deployment, since the earlier Azure run is on a different claim and cannot be compared.

**What was done.** The endpoint, the guard, the nine tools, the access-record table and the live feed were built, with an *Integrations* page that lists what the server offers from its own definitions and shows calls as they happen, and a *Guide* page for first-time visitors. The Guardrail's card on the run page now shows the model's refused citation claims without opening the audit record.

**How it was proven.** Every guard has a test that triggers it: a missing, wrong or differently-formed token is refused; an unset token leaves no route; a scenario name outside the three is refused before anything is looked up. Two tests were deliberately broken and watched fail: removing the token comparison fails the wrong-token test (the missing-header refusal sits before the comparison, so that test still passes, which is the correct reading of it); forcing the endpoint to mount without a token fails the two unset-token tests. The official client library was run against a local backend over HTTP: tools listed, policy read, claims listed, chain verified, wrong token refused. On 2 November 2026, with Dermot present, the Azure deployment mounted the endpoint behind a token generated and stored by the deploy script, and the official client was refused without the token and admitted with it. Claude's own connector was then refused six times. The record could not say whether the connector had sent the secret at all, because the guard said nothing about why it refused, so a first point release made it say why, and a second made the application's log lines reach the Azure log at all: nothing had ever told the service how loud to be, and on Azure the monitoring library had quietly set it to warnings only. With both in place the connector's next refusal read *header absent*: the connector's set-up form probes the server before the secret is saved, is refused, looks for a sign-in service, finds none and reports a failure, and once the form is saved with the secret the connection succeeds. Claude Desktop then listed the claims, and the call appeared on the Integrations page.

**Status.** Partially resolved: the access decision and the read-only decision are settled and proven on Azure; the Render deployment and the three scripted scenarios through the connector remain to be checked.

*Technical detail:* plan `24-phase-10-mcp-server-and-integrations-page-plan.md` (§0 findings 5, 11 and 12; §2; *Decisions requested*, D1–D8; *Approval*); `backend/app/mcp/auth.py`, `server.py`, `tools.py`; migration `0003_mcp_tool_calls`; `backend/tests/test_mcp_auth.py` (mutation proofs in the module docstring and the build log); build log, entry *Phase 10*.
