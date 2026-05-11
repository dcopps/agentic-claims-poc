# Prompt 04 — Phase 3: Remaining Agents (Doc-Parser, Adjuster, Guardrail)

## Read first

Before doing anything else, read these five files in this directory:

- `CLAUDE.md` — global standards reference, project overview, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 3.
- `docs/prompts/03-phase-2-llm-gateway-and-validator-report.md` — what Phase 2 delivered and the interfaces it locked.
- `backend/app/agents/validator.py` — the Phase 2 reference implementation. Each Phase 3 agent follows the same shape (constructor injection, decomposed named helpers, defensive guards, structured audit log entry).
- `backend/app/agents/validator_models.py` — the Pydantic patterns for typed input / output / cited references.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. The relevant items: plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts (no inline f-strings), system/user message separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 3 of `BUILD-PLAN.md` — Remaining agents. By the end of this phase the system contains three more agents, each runnable in isolation against the seeded claims, each using the LLM Gateway / APILogger / PromptLoader plumbing Phase 2 landed:

- **Doc-Parser** (Claude Haiku) — accepts a raw claim narrative, returns a typed Pydantic structure with extracted fields (loss date, jurisdiction, claim type, claimed amount, claimant identifier, narrative summary). Text-only in Phase 3; vision support remains deferred per the Phase 0 report.
- **Adjuster** (Mistral Large) — accepts a structured claim plus the Validator's verdict, looks up the market-data range for the (claim_type, severity) cell from a static YAML table, calls Mistral to pick a settlement value *within that range* and produce a justification. The LLM never invents the range; only selects within bounds the table provides.
- **Guardrail** (Claude Haiku) — accepts an Adjuster output (full structured response), checks for PII leakage, biased reasoning, and hallucinated policy citations. Returns a typed pass/fail with named flags. Fails closed: any guard tripping returns `pass=False`.

No orchestrator, no pipeline, no UI changes. Phase 4 wires them together. Phase 3 builds each agent in isolation and verifies the three are individually correct against the seeded fixtures.

Plus one small preamble fix-up bundled into the same Phase 3 commit (the same per-phase versioning pattern Phase 2 introduced):

- Bump `pyproject.toml` version `0.2.0` → `0.3.0`. The `/health` `version` field on the deployed backend will then read `0.3.0` after the Phase 3 push, confirming Phase 3 code is live.

## Current state of the project (for orientation)

Phase 2 delivered:

- `LLMProvider` interface with `AnthropicProvider` and `MistralProvider` implementations under `backend/app/llm/`.
- `APILogger` writing structured JSON records under `backend/app/logging/`.
- `PromptLoader` and the first externalised prompts under `backend/app/prompts/loader.py` and `backend/app/prompts/{system,user}/`.
- The `Validator` agent at `backend/app/agents/validator.py` with its supporting types at `backend/app/agents/validator_models.py`.
- `LLMSettings` extended with per-call defaults; new `LoggingSettings` and `RetrievalSettings` sub-models.
- 124 tests passing (Phase 1 + Phase 2 combined); two opt-in e2e tests gated by `RUN_LLM_E2E_TESTS=1` and `RUN_EMBEDDING_TESTS=1`.
- `/health` reports `version=0.2.0`.

The deployment chain is intact. `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` are set as environment variables on Render and confirmed working. The Validator has been exercised end-to-end against real Mistral; the anti-hallucination cross-check (cited chunks must be in retrieved set) was verified live.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering everything below.

### Shared questions to answer

Before describing the individual agents, address these cross-cutting design decisions in the plan:

1. **Do the three agents share a base class?** Each agent has the same shape (constructor injection, named helpers, audit log entry, defensive guards, LLM call via Gateway, structured Pydantic return). After Phase 2 you've written this pattern once; after Phase 3 you'll have written it four times. Options:
   - Keep each agent independent (no shared base). Easier to read each file in isolation; small amount of duplication; matches what Phase 2 did.
   - Introduce a `BaseAgent` abstract class with a hook method pattern. Reduces duplication but adds an inheritance layer that has to be understood before any single agent makes sense.
   - Introduce a small `_audit_step(...)` helper at module level (not a class). Minimal abstraction; just shares the audit-log entry construction.
   Recommend one. Phase 4's orchestrator will instantiate all four agents, so the construction story matters but isn't load-bearing on this decision.

2. **Where does the market-data lookup table live, and what's its shape?** Options:
   - `backend/data/market_data.yaml` — declarative, editable without touching Python code, parseable. Recommended.
   - `backend/data/market_data.py` — a Python dict / dataclass at module level. More refactorable but less editor-friendly for non-engineers.
   - A new `market_data` table in Postgres. Over-engineered for a 5×3 (claim_type × severity) prototype lookup.
   Recommend one. Whichever you pick, propose the exact rows for the demo: at minimum one row each for `water_damage`, `fire`, `wind`, `theft`, and `flood`, across severities `minor`, `moderate`, `severe`. Round numbers; ranges that comfortably contain the locked demo scenario amounts ($85k auto-approve, $850k threshold escalation, $1.4M guardrail escalation). Document the severity-derivation logic — is severity an input from Doc-Parser, derived from the reported amount, or always supplied at the call site?

3. **What is the typed input shape for each agent's `evaluate(...)` method?** The Validator took `(claim_id: UUID, correlation_id: UUID)` and loaded everything else from the database. Adjuster needs the Validator's verdict and the structured claim — does it pull those from the database via `claim_id` (same pattern as Validator) or does the caller pass them in directly (Phase 4-friendly pattern)? Same question for Doc-Parser (input is the raw narrative — load from DB or accept directly?) and Guardrail (input is Adjuster's output — same question).

4. **What does each agent's typed output look like?** Sketch the Pydantic models. These are the contracts Phase 4 will orchestrate against, so they need to be stable.

5. **How does each agent's audit-log payload look?** The Validator's payload was locked at end of Phase 2 (input excerpt, retrieval block, llm_call block, verdict block). Each Phase 3 agent gets its own payload shape; document it in the plan and treat as locked at end of phase.

### Per-agent design (in the plan)

For each of the three agents, the plan should specify:

- **File location and module structure.** `backend/app/agents/doc_parser.py`, `adjuster.py`, `guardrail.py`. Pydantic models in matching `*_models.py` files (or a single `agents/models.py` if you prefer — recommend one).
- **The class constructor signature.** What collaborators are injected (provider, prompt_loader, audit_writer, api_logger, settings, plus any agent-specific dependencies like the market-data lookup).
- **The `evaluate(...)` method signature and return type.**
- **The internal flow as named helpers.** Each ≤30 lines, decomposed faithfully like the Validator's `_load_claim` / `_embed_narrative` / `_retrieve_top_chunks` / `_build_user_prompt` / `_call_provider` / `_parse_verdict` / `_audit_log` split.
- **The externalised prompt files.** `backend/app/prompts/system/{doc_parser,adjuster,guardrail}.md` and `backend/app/prompts/user/{doc_parser,adjuster,guardrail}_template.md`. Specify the persona, the output schema, the placeholders in the user template. No inline f-string prompts anywhere.
- **The Pydantic output model** — exact fields, constraints, cross-validation rules.
- **The audit-log payload shape** — exact JSON shape locked at end of phase.
- **The defensive guards** — every error path that needs a guard, every guard with its `ValueError` message; every guard with a triggering test.
- **The agent-specific subtleties:**
  - **Doc-Parser:** how do you handle malformed JSON output (Haiku doesn't have a true JSON mode)? Strip-and-retry-parse, or fail immediately? What if the model extracts a date that isn't a valid ISO date — `ValueError` or graceful coercion? Document the choice.
  - **Adjuster:** the LLM must pick *within* the looked-up range. How do you enforce this? Re-validate the returned value against the range and raise on out-of-bounds (recommended), or trust the prompt and let the value pass? Recommend re-validate.
  - **Guardrail:** what's the precise set of checks? At minimum: (a) PII tokens in the Adjuster's `reasoning` field (regex on common patterns — SSN, phone, email), (b) hallucinated policy citation (Adjuster mentions a clause / endorsement / sub-limit name that doesn't appear in the policy chunks for this claim's correlation_id), (c) reasoning that references a protected characteristic. List the exact regex / pattern sets in the plan; commit to a small, explicit set rather than a probabilistic detector.

### Testing strategy

- Unit tests for each agent with mocked LLMProvider (same pattern as the Validator's test suite). Every guard clause has a triggering test asserting on message content.
- One opt-in real-call test per agent, gated by `RUN_LLM_E2E_TESTS=1`. Confirms the live integration works against the actual Haiku / Mistral endpoints.
- Tests for the market-data lookup function in isolation — bounds, missing cells, severity derivation.
- Tests for the agent-specific subtleties — Doc-Parser's date coercion guards, Adjuster's range-enforcement guard, Guardrail's per-check rules.

Aim ~30–40 new tests across the three agents plus the lookup table. Update the running total in the report.

### CI changes

- No new service containers, no new gated-by-env-var test categories beyond `RUN_LLM_E2E_TESTS=1` (already exists from Phase 2).
- No new dependencies — every Phase 3 agent reuses what Phase 2 added.

### New dependencies — flag each one

If your plan introduces any, flag and justify per the dependency-discipline standard. The expected answer is **none new**; if you find yourself adding one, surface why before writing code.

### Risks and downstream impacts

The Pydantic output models for all three agents lock at end of Phase 3 — Phase 4's orchestrator passes Validator → Adjuster → Guardrail outputs around. Anything you'd later change is an interface-stability event needing explicit re-acknowledgement. Enumerate the locked contracts in the plan, same shape as Phase 2's list.

### Deployment steps requiring architect involvement

Same as Phase 2: after the commit lands and pushes, Render auto-redeploys. No new env vars are required (the existing `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` cover Phase 3). The architect verifies `/health` returns `version=0.3.0` after the redeploy.

### Optional enhancements

Clearly labelled, delivered separately, never silently. Carry forward from Phase 2's report the items still deferred (retries via tenacity, SSE streaming, pricing table population, real PII redactor, prompt golden-text fixtures). Add any new Phase 3 enhancements you'd recommend.

### Save the plan

Save the plan **before** asking me to review it, so I can read it in my editor. Write it to:

```
docs/prompts/04-phase-3-remaining-agents-plan.md
```

Top-level heading: `# Plan 04 — Phase 3: Remaining Agents`. Below that, the body of the plan.

After saving the file, point me at it and ask for my verdict. Do not write any other code or modify any other files yet.

## Step 2 — Approval or rejection

Same workflow as Phases 0, 1, and 2 (per `docs/prompts/README.md`).

**If I approve** (any reply along the lines of "yes", "go ahead", "approved", or similar):

Append a horizontal rule and an `## Approval` section to the plan file. Order the section so the timestamp closes the file:

```
## Approval

**Approval message:** "<my exact approval message, quoted>"

---

**Approved by:** Dermot Copps
**Approved at:** <ISO 8601 timestamp in UTC>
```

Then proceed to Step 3.

**If I reject**, append a `## Rejection` footer, rename the file to `04-phase-3-remaining-agents-plan-rejected-NN.md`, produce a revised plan as the fresh canonical file, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 3. Constraints from `CLAUDE.md` apply throughout:

- **Defensive programming** (sanitise → validate → abort → execute) for every function that takes input. Every guard has a triggering test that asserts on message content.
- **Function size:** 30 lines is a prompt to reconsider; 50 lines is a hard limit. The agent `evaluate(...)` methods decompose into named helpers; the helpers themselves stay small.
- **Settings hierarchy:** any new fields appear in both `backend/settings.py` and `backend/settings.yaml.template`. No hardcoded values. No magic numbers without a named constant and a comment.
- **Type hints** on every function signature.
- **Tests:** every new function gets tests; every guard clause gets a triggering test asserting on error message content.
- **Anonymisation:** the client name does not appear anywhere — code, comments, tests, fixtures, prompt files, market-data table, commit messages.
- **Security:** no new credentials introduced in Phase 3 (the LLM keys cover everything). The market-data lookup is plain configuration, not secret.
- **Externalised prompts:** all six new prompt files live under `backend/app/prompts/system/` and `backend/app/prompts/user/`, loaded via `PromptLoader`. No inline f-string prompts anywhere.
- **System/user message separation:** the Gateway already enforces this. Each agent's call site uses the same convention.
- **Interface stability:** the three agent output Pydantic models, the three agent audit-log payload shapes, and the market-data lookup's typed return shape are interfaces Phase 4 depends on.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.2.0` → `0.3.0`. The `/health` `version` field then reflects Phase 3 once deployed.

## Step 4 — Log

When the code work is complete, append a new entry to `docs/build-log.md`. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/04-phase-3-remaining-agents.md`.
- Plan (approved): link to `docs/prompts/04-phase-3-remaining-agents-plan.md`.
- Plan iterations: count of rejected revisions, with links to each.
- Report: link to `docs/prompts/04-phase-3-remaining-agents-report.md`.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate, with breakdown per agent.
- Issues discovered.
- Next: Phase 4 — Pipeline orchestrator.

## Step 5 — Write the report

Save the report to `docs/prompts/04-phase-3-remaining-agents-report.md`. The report opens with a `## Summary` block containing, in this order:

- **Recap** — one sentence stating what's done plus one sentence stating what comes next.
- **Completed at** — ISO 8601 UTC timestamp at the moment of report-writing.
- **Phase** — `3 — Remaining agents (Doc-Parser, Adjuster, Guardrail)`.
- **Status** — Complete / Complete with deferrals.
- Links to the prompt, the approved plan, and the repository.
- CI status if relevant.

Body sections cover files created and modified by tier, test counts and pass rates with per-agent breakdown, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 3:

- Date: today's date in ISO format.
- Phase: "Phase 3 complete; Phase 4 next".
- What works: a one-line summary of the new capability (e.g. "All four agents (Doc-Parser, Validator, Adjuster, Guardrail) run end-to-end in isolation against the seeded claims, each producing typed structured output with a full audit-log entry per call. No orchestrator wiring yet; that's Phase 4.").
- What's next: "Phase 4 — Pipeline orchestrator."

## Step 7 — Git

Make a single commit covering all the Phase 3 work, with the commit message:

```
Phase 3: remaining agents (Doc-Parser, Adjuster, Guardrail)

- Doc-Parser agent (Claude Haiku): structured field extraction from claim narratives
- Adjuster agent (Mistral Large): market-data lookup table + within-range LLM pick
- Guardrail agent (Claude Haiku): PII / hallucination / bias checks on Adjuster output
- Externalised prompts: six new system/user files
- Pydantic models for each agent's input, output, audit payload
- Market-data lookup table (backend/data/market_data.yaml)
- Defensive guards throughout, every guard with a triggering test
- pyproject.toml version bumped 0.2.0 -> 0.3.0
- Approved plan archived; build log entry appended; report written
- CLAUDE.md Current Status updated
```

Push to `main` so Render auto-deploys.

## Step 8 — Report back

Per the global "After coding" section, report:

- Files created and modified.
- Test count and pass rate, with per-agent breakdown.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend for follow-on work.

End the report with the action items I still need to handle:

- Verify the Render redeploy completes and `/health` reports `version=0.3.0`.
- Optionally exercise each agent end-to-end against the seeded claims via the gated `RUN_LLM_E2E_TESTS=1` test run, locally — confirms the Haiku integration works for Doc-Parser and Guardrail, and that the Adjuster's range-enforcement guard fires correctly when the model returns a value outside bounds (a deliberate failure case worth seeing once).
