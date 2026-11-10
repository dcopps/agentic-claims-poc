# The build in thirty seconds a phase

This file holds only the summaries. Each phase of the build has a full entry in [the build story](README.md), with what it set out to do, what it delivered, what it found, and where the engineer's record is. The paragraphs below are the opening *TL;DR* of each of those entries, in build order, for a reader who wants the shape of the whole project in a few minutes and nothing more. Every heading links to its full entry. The file is regenerated from the entries at every close-out, so it is always identical to them and to the at-a-glance table at the top of the build story. Incidents and decisions have their own plain-language record, [the decision register](../decision-register.md).

### [01 — Phase 0: a repository that runs, tests itself and deploys](README.md#entry-01)

Before any real work, the project needed a shell that already worked end to end. This phase built that shell: a tiny web service, a web page that reports whether the service is up, and automatic checks that run every time something changes. Nothing in it handles a claim yet. It was finished and published on Friday 8 May 2026.

### [02 — Phase 1: the database, the audit trail and the policy text](README.md#entry-02)

This phase built the places where everything gets stored. The most important of them is the audit trail, a record of every step the system takes that is designed so that nobody can quietly change it afterwards. It also wrote a short, made-up insurance policy for the system to read, and nine made-up claims to test it with. Finished the same day as the first phase, Friday 8 May 2026.

### [03 — Phase 2: the first agent, and the door every model call goes through](README.md#entry-03)

This phase connected the system to the outside AI models for the first time, through a single doorway that every future agent would also use, so that each call is logged the same way and the provider can be swapped without rewriting the agents. It then built the first agent, the Validator, which finds the relevant passages of the policy and asks the model whether the loss is covered. Every call writes to the audit trail, including the ones that fail. Finished on Monday 11 May 2026.

### [04 — Phase 3: the other three agents](README.md#entry-04)

With the first agent working, this phase built the remaining three. One reads the claim into structured fields. One proposes a settlement figure, and is held inside a published range for that kind of loss so it cannot invent a number. One checks the proposal for leaked personal data, bias and references to policy wording that is not there, and fails the claim if it finds any. Finished on Monday 11 May 2026, with all four agents now writing to the audit trail.

### [05 — Phase 4: the agents become a pipeline, and the escalation rules are written down](README.md#entry-05)

Until now the four agents worked alone. This phase connected them into one run, from reading the claim to a final outcome, under a single reference number that ties every step together in the audit trail. It also wrote the rules that decide when a claim must go to a person, in a plain configuration file rather than in code, so anyone can read them. Finished on Sunday 14 June 2026.

### [06 — Phase 5: a claim is recorded before anything runs, and any run can be replayed](README.md#entry-06)

This phase separated two things that had been one: submitting a claim, and processing it. A claim is now saved first and processed later, as it would be in a real insurer. It also made every past run reconstructible from the audit trail alone, and added a way to re-run a claim with a different setting and compare the two outcomes side by side. A first, plain web interface arrived with it. Finished on Sunday 14 June 2026.

### [07 — Phase 6: an interface a person can work in](README.md#entry-07)

This phase turned the plain interface into the one the demonstration uses: separate pages for claims, for a live run with each agent's card filling in as it finishes, for the audit trail with a button that checks the whole chain has not been tampered with, for a person to approve or reject an escalated claim, and for trying each agent on its own. Finished on Monday 15 June 2026, just after midnight.

### [08 — Phase 7: ready to show, and the governance documents](README.md#entry-08)

This phase made the system presentable and wrote the documents that explain how it is governed: how changes are classified and approved, which outside providers it depends on and how each could be replaced, and the reasons behind its main design choices. It also made the third scripted scenario, the one where the Guardrail must catch an invented endorsement, reproducible every time. Finished on Monday 15 June 2026.

### [09 — Phase 8: six fixes from the first rehearsal](README.md#entry-09)

A rehearsal of the demonstration found six things that got in the way, and this phase fixed them in one pass. The most visible was that the live run page was opening only after the run had finished, so nobody saw the agents work. The most consequential for later was a first attempt to stop the Guardrail treating the Adjuster's own market vocabulary as a policy citation, by telling it so in its instructions. Finished on Monday 15 June 2026.

### [10 — Phase 8.2: the claim record is the source of truth, and the model only summarises](README.md#entry-10)

The first agent had been asked to pull dates, amounts and places out of the claim's free text, and the model kept filling in placeholders that broke the run. This phase stopped asking it to. The structured facts now come straight from the claim as recorded, and the model is used only for what it is good at: a short summary of the narrative. The audit trail says so on every run. Finished on Monday 15 June 2026.

### [11 — Phase 8.3: the audit trail records exactly what each model was told](README.md#entry-11)

When you opened an agent's card to see what it had asked the model, you saw a blank template with placeholders in it, not the real question. This phase made every agent record the exact, filled-in instructions it sent, and the interface now shows those. It also fixed a panel that said "waiting" forever and gave each run a link to its audit entries. Finished on Tuesday 16 June 2026.

### [12 — Phase 8.4: the audit trail was losing entries on the live system](README.md#entry-12)

During a rehearsal on the live system, three of the four agents showed as finished on screen but their audit entries were missing. The record that is meant to explain every decision was silently incomplete. This phase found the cause, a database connection setting that discarded writes under a particular sequence of operations, fixed it, and added tests that read back through a second connection to prove the entries really persist. Finished on Friday 26 June 2026. The first entry in the decision register belongs to this phase.

### [13 — Phase 8.5: the tests can never again touch a live database](README.md#entry-13)

The automated tests clear the database before each run. On a developer's machine, the configuration file pointed at the live database, so running the tests wiped it. This phase gave the tests their own database and, more importantly, made the test harness refuse outright to run against any live host, with no way to override it. Finished on Saturday 27 June 2026.

### [14 — Phase 8.5.1: a test that passed while breaking the database](README.md#entry-14)

The first run of the tests against the new local test database showed two failures that had never appeared on the shared build server. One test was proving a safety property by temporarily breaking the database, and relied on an automatic undo that an earlier phase had removed. It passed the first time, left the damage behind, and every later run failed. This small release fixed the test so the undo is explicit and checked. Finished on Monday 14 September 2026. The first "point release" in the numbering.

### [15 — Phase 8.5.2: the model that moved underneath us](README.md#entry-15)

A live run failed because the second AI provider refused the request: the project's free account was no longer allowed to use the model. The system had been asking for "the latest large model", a name the provider can repoint at will, and it had been repointed at a paid release. This release pinned the exact release the system had been built against. It did not work, because that release had been withdrawn from the free tier too, and finding that out took the next release. Finished on Monday 14 September 2026.

### [16 — Phase 8.5.3: record what was asked, not only what answered; and reset the live data](README.md#entry-16)

When a model refuses a request, there is no answer to record, so the audit trail could not say which model had been asked. This release makes every agent record the model it asked for, on success and on failure alike. It also reset the live database to a clean, known state before testing, under a check that it was pointed at the right host. With the new field in place, the previous release's question was answered from the audit trail in one line. Finished on Monday 14 September 2026.

### [17 — Phase 8.6: Claude for all four agents, Mistral kept as a switch; and a halt](README.md#entry-17)

With the Mistral model withdrawn from the free tier, two agents could not run. Rather than pay for the provider or leave the system half-working, Dermot decided that all four agents would use Claude by default, with the Mistral route kept and switchable so the substitutability argument stays real. The code was built so that each agent's provider is a setting. Then the live verification halted on its first scenario, for a reason that turned out to be eight months old. Finished on Tuesday 15 September 2026, the verification having halted the same afternoon.

### [18 — Phase 8.6.1: one line fixed, the verification passed, and three findings left open on purpose](README.md#entry-18)

This small release fixed the pattern that had halted the previous verification, with tests built from the real sentence that tripped it. The full live check was then re-run from a clean start and passed. Along the way it found three further problems that nobody had seen before, none caused by the fix, and Dermot ruled that they were findings to record rather than reasons to halt. Finished on Monday 21 September 2026.

### [19 — Phase 9.1: a second home on Azure, built from a written description](README.md#entry-19)

The system had lived on three small hosting services. This phase stood up a second, complete installation on Microsoft Azure, the kind of platform a regulated insurer would actually use, described entirely in infrastructure files so it can be recreated from the repository. The same code, the same database layout and the same settings ran there unchanged. The three scenarios passed on it the same day. Finished on Thursday 1 October 2026.

### [20 — Phase 9.2: the Azure installation completes itself, and the model changes its mind](README.md#entry-20)

This phase finished the Azure installation: the web interface hosted there too, both halves deploying themselves whenever a change is pushed and passes its checks, with no stored cloud password, and monitoring switched on. The second full verification was run through the browser. It passed for the deployment, with one recorded exception that became the story of the next two phases: the AI model had changed its verdict on identical input between 1 and 26 October, with no change on the project's side. Finished on Monday 26 October 2026.

### [21 — Phase 9.2.1: asking the model a narrower question, and finding it was not enough](README.md#entry-21)

The Guardrail's AI check had started treating the Adjuster's ordinary words as policy citations. This release rewrote the check's instructions to define a citation precisely and to say that coverage is not its question, and it built a way to replay recorded runs against the live model before every demonstration. The rewrite cleared most cases but not all; a second wording change cleared the rest, until a new run on a different path escalated on yet another phrase. The release closed as partially verified, with the failing case kept as a deliberate red test. Begun on Wednesday 28 October 2026; closed as partially verified on Thursday 29 October 2026; the addendum followed on Friday 30 October.

### [22 — Phase 9.2.2: the model may suspect, but code decides](README.md#entry-22)

After two releases of adjusting the Guardrail's instructions, this one changed who makes the decision. The model must now quote the exact words it objects to. Code checks that the quote really is in the Adjuster's reasoning and that it looks like a named policy provision, using the same test the deterministic check already uses. If either fails, the objection is recorded in the audit trail with the reason and does not count. The auto-approve scenario passed on all three paths the same day. Finished on Friday 30 October 2026.

### [23 — Prompt 23: the story told in plain language](README.md#entry-23)

Everything in this build had been recorded, but only in places an engineer can read. This phase wrote two documents for everyone else: this one, which tells the build phase by phase, and the decision register, which records every incident and every decision taken at a gate. It also put signposts to them at the top of every technical file, and made writing them part of the routine for every future phase. Begun on Friday 30 October 2026 and finished on Saturday 31 October 2026.

### [24 — Phase 10: a way to ask the system questions, and a page that shows it being asked](README.md#entry-24)

Until now the system could only be used through its web pages. This phase let an AI assistant such as Claude ask it questions — why did this claim settle, what did the Guardrail object to and why did the objection not count — and get answers taken only from the audit trail, never from deciding again. Every question is recorded, only a holder of a shared secret may ask, and a new page shows the questions arriving as they are asked. A short Guide page for first-time visitors was added at the same time. Begun on Monday 2 November 2026 and finished on Wednesday 4 November 2026.

### [25 — Prompt 25: one document that shows how the system was tested](README.md#entry-25)

The proof that the system had been tested was spread across twenty-four plans, twenty-four reports and the build log, each with its own count and its own wording. This prompt gathered it into one document: what an automated test is and why there are hundreds, what the two test suites hold today, which tests each phase planned and delivered and whether it proved them, how the model's behaviour is watched, and what is not tested at all — finished on Thursday 5 November 2026.

### [26 — Prompt 26: the Guide rewritten for a first-time visitor](README.md#entry-26)

The repository and its README now send a first-time visitor straight to the app, and the Guide is the page that tells them what they are looking at. Its opening paragraph described the project before it said what the system was, it never named the four agents or said how a claim is processed, it gave no steps to follow, and its links predated the testing document and the diagram's fourth view. This prompt rewrote the Guide's text and added three sections — finished on Tuesday 10 November 2026.

### [27 — Prompt 27: a Policy page, so a reader can see the wording every decision rests on](README.md#entry-27)

Every coverage decision in the system rests on the policy wording, but a visitor could not read it: the Validator named the passages it relied on, the review panel showed excerpts, the Guide said there were twelve passages, and the policy itself sat only in the repository as a text file. This prompt added a Policy page that shows the policy exactly as the system indexed it, and linked to it from every place that names a passage — finished on Tuesday 10 November 2026.

