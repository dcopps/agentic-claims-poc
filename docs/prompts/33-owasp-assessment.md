# Prompt 33 — Security assessment against the OWASP Top 10 lists

## Why this prompt exists

The system has never been assessed for security as a whole. Some of the right controls against prompt injection exist by design, and none of it has been tested or written down. The claimant's free-text description is untrusted text and goes straight to four models; nobody has tried a description written to mislead them.

This prompt produces the assessment. It changes no code. It reads the system as it stands, measures it against three published OWASP lists, records what is found with evidence, and proposes the fixes as small prompts to follow. The fixes are not built here.

The UI polish (the Agents page, then the Integrations page) is paused behind this work and resumes after it.

## The three lists

Assess against the current published edition of each. Fetch each list from its official OWASP page at the start, record the edition, the version and the date fetched, and use the official identifier and title of every item exactly as published. Do not work from memory: these lists were revised recently and the items and their order have changed.

1. **OWASP Top 10 for LLM Applications**, the 2026 edition (published August 2026, genai.owasp.org). The centrepiece.
2. **OWASP Top 10 for Agentic Applications**, the 2026 edition (published December 2025, genai.owasp.org). For the orchestrator, the four agents and the MCP server.
3. **OWASP Top 10** for web applications, the 2025 edition (owasp.org/Top10). The system is also a public web application and API.

If an official page cannot be fetched, stop and say so; do not substitute a third-party summary without Dermot's agreement.

## What to assess

Every item on each list, thirty in all, against the system as deployed on Azure and as written in the repository. For each item:

- **What the risk is**, in one or two plain sentences.
- **Whether it applies here**, and where: which page, endpoint, agent, table or workflow.
- **What the system does about it today**, with the evidence: the file and function, the test that proves it, the audit field that records it, or a read-only observation of the deployed system.
- **A rating**: *Addressed*, *Partly addressed*, *Not addressed*, *Accepted for a demonstration system* (with what production would do, in the manner of the architecture diagram's *Designed and Built* view), or *Does not apply* (with the reason).
- **How serious it is here**, in plain words, considering that the data is synthetic and the site is public.
- **The proposed fix**, sized as one small prompt, or the reason none is proposed.

Do not stop at the lists' wording. Look for what is actually there. At minimum, examine and report on each of these, wherever on the lists it falls:

- The claimant's description as an attack: text written to change the Doc-Parser's summary, the Validator's verdict or confidence, the Adjuster's figure or confidence, or the Guardrail's finding. State what each agent's instructions and the code after it do and do not prevent, and whether a claim under the settlement ceiling could be made to settle by its own description.
- What limits the damage if a model is misled: no tools on the agents, structured output and its validation, the escalation rules in code, the Guardrail's quote check, the person on escalated claims.
- The API having no sign-in: who can submit a claim, start a run, start a strict re-run, approve or reject a claim under any name, and read every claim, record and instruction.
- Cost and availability: whether a visitor can cause unlimited model calls, through the Claims page, the Agents test bench or the API directly; any rate limit, cap or budget that exists.
- The Agents test bench: arbitrary input sent to each model by any visitor.
- The MCP server: the single shared token, what a holder can do, what `run_scenario` can be made to do, how calls are recorded, and what the tool descriptions and results would do to a connected AI client if the claims they return contained instructions.
- The instructions sent to the models being readable on the Audit and run pages: by design, and what follows from it.
- Personal and sensitive data: what is stored, logged, sent to the model provider and shown, given the data notice on the Claims page.
- The policy index: who can change it, how the system would know it had been changed or was incomplete, and what recording the embedding model protects against.
- Model output shown in the browser, and any path by which it reaches a query, a file or a command.
- Database access, queries built from input, and the run-id prefix search.
- Secrets, identities and deployment: Key Vault, the two managed identities, the GitHub workflows and their permissions, pinned or unpinned actions, CORS, public endpoints.
- Dependencies and supply chain: lockfiles, the model provider, the embedding model's origin, the base image.
- Logging, monitoring and the audit chain: what would show that an attack had happened.
- Over-reliance: what a reader of a run page or an MCP answer is told about how far to trust it.

## How to gather evidence

- Read the code, the tests, the configuration and the Bicep templates.
- Read-only observation of the Azure deployment is allowed: `GET` requests, response headers, page text.
- Trying an attack is a separate matter. Propose in the plan a small set of attack descriptions and how each would be run. Run them locally against the test or development database, never against a deployed database, and say what each will cost in model calls. Nothing that writes to Azure or Render is run without Dermot's approval in the plan.
- Record what was tried and what happened, including attacks that failed. A control that held is evidence too.
- Where something cannot be determined, say so. Do not rate an item *Addressed* without evidence.

## What to produce

1. **`docs/security-assessment.md`**, written to the plain-language standard of `docs/decision-register.md` and `docs/test-evidence.md`, for a reader who is not a security engineer:
   - a one-page summary: what was assessed, against which editions, when, how many items fell under each rating, and the findings that matter most;
   - one table per list, a row per item, with the rating;
   - one short section per item with the detail above;
   - the attacks tried and their results;
   - the list of proposed fixes in the order they should be done, each sized as one prompt.
2. **Backlog entries** in `docs/BACKLOG.md` for every finding rated *Partly addressed* or *Not addressed*, under a new heading, each pointing at its section of the assessment.
3. **The proposed order of work** for the fix prompts that follow, with a recommendation for which two or three to do first.

## Wording

- The system is **assessed against** these lists. It is never described as "OWASP compliant", "OWASP certified" or "secure": the lists are awareness guides, not standards, and there is nothing to certify against. The assessment says so in its opening.
- State the limits of the assessment plainly: one assessor, the repository and the deployment as they stood on the date, no independent penetration test.
- The repository and the site are public. For any finding that would give a ready route to abuse the live site while it is unfixed (running up model costs is the obvious one), say in the plan how it will be worded, or whether the fix should land before the detail is published. Dermot decides.

## Plan first

Produce `docs/prompts/33-owasp-assessment-plan.md` covering:

1. The three lists as fetched: edition, version, date, source address, and all thirty items by identifier and title.
2. For each item, a first reading of whether it applies and where you will look, so that Dermot can see the coverage before the work is done.
3. The attack descriptions proposed, how and where each will be run, and the cost.
4. The structure of `docs/security-assessment.md`, with one item written out in full as a sample.
5. How findings that could be abused on the live site will be handled.
6. What will be read-only observed on Azure.
7. Anything in the record that contradicts this prompt.

Wait for explicit confirmation before doing the assessment.

## Constraints

- No change to any code, test, configuration, infrastructure or deployed system. Documentation only; no version change.
- Standing conventions per `CLAUDE.md`, including anonymisation and the commit-protocol rule.
- No credentials, tokens or connection strings in the assessment, the plan or any command output kept in the repository.
- Voice: plain and direct, British English, no superlatives, no scare quotes; "the system", not "the prototype".
- Azure is running and stays running.

## Close-out

Report; build-log entry *Prompt 33*; build-story entry 33 with TL;DR and Technologies; signposts; the regeneration script; the README's documentation index and *Not an engineer? Start here* section pointing at the assessment; a glossary entry for *OWASP Top 10* in both plain-language documents; a decision-register entry for any halt, deviation or gate decision; `CLAUDE.md` status, with *What's next* reading the first fix prompt, and the Agents page after the security fixes; commit and push.

## Archive

Pre-saved at `docs/prompts/33-owasp-assessment.md`; plan and report alongside.
