# Prompt 03 — Phase 2: LLM Gateway and Validator Agent

## Read first

Before doing anything else, read these four files in this directory:

- `CLAUDE.md` — global standards reference, project overview, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 2.
- `docs/prompts/02-phase-1-data-layer-report.md` — what Phase 1 delivered, the data foundation Phase 2 builds on.
- `diagrams/2-rag-zoom.mmd` — the RAG mechanics diagram. Phase 2's Validator implements exactly this flow.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. The relevant items for this prompt: plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, **externalised prompts (no inline f-strings)**, **system/user message separation**, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 2 of `BUILD-PLAN.md` — LLM Gateway and Validator agent. The definition of done is in the build plan; meet it.

By the end of Phase 2 the system has:

- An `LLMProvider` interface with two implementations (`AnthropicProvider`, `MistralProvider`) that mediate every LLM call.
- An `APILogger` that writes one structured JSON record per LLM call (prompt, response, model, tokens, cost, latency, correlation ID), gated by a setting.
- A `PromptLoader` that loads externalised prompts from `backend/app/prompts/system/` and `backend/app/prompts/user/`. No inline f-string prompts in source code.
- The **Validator agent** running end-to-end: receives a claim narrative, embeds it via the same model used for indexing (`bge-small-en-v1.5`), retrieves the top 3 most similar chunks from `policy_chunks` via cosine similarity, builds the augmented prompt via PromptLoader, calls Mistral Large via the Gateway with system/user separation, returns a structured Pydantic verdict with cited chunks, writes the full reasoning trace to the audit log under a correlation ID.

No other agents (Doc-Parser, Adjuster, Guardrail, Orchestrator). No pipeline, no UI changes. Phase 3 brings the remaining agents; Phase 4 wires the orchestrator.

## Current state of the project (for orientation)

Phase 1 delivered: database schema (claims, audit_log, policy_chunks) on Neon Postgres, settings sub-models (Database, LLM, Embedding, Langfuse, Escalation), audit chain with defensive guards, sample commercial property policy excerpt indexed via bge-small-en-v1.5, 9 synthetic claims seeded covering the three demo scenarios. 67 backend tests + 2 frontend tests all green. Render Web Service Live with `DATABASE_URL` set; `/health` returns `{"status":"ok","version":"0.0.1"}`.

The deployment chain is intact: GitHub push → CI green → Render auto-deploy → uvicorn starts → `/health` healthy.

Phase 2 prerequisites the architect supplies (when this prompt asks):

- `MISTRAL_API_KEY` — confirmed working as of 2026-05-09 against `mistral-large-latest` (resolves to `mistral-large-2512`).
- `ANTHROPIC_API_KEY` — confirmed working as of 2026-05-09 against `claude-sonnet-4-6` and `claude-haiku-4-5-20251001`.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering:

- **Files and directories you will create or modify.** New code under `backend/app/llm/`, `backend/app/agents/`, `backend/app/logging/`. New prompt files under `backend/app/prompts/system/` and `backend/app/prompts/user/`. New tests under `backend/tests/`. The two preamble fix-ups described under "Preamble fix-ups" below.
- **LLM Gateway design:**
  - The `LLMProvider` interface — what methods, what argument shapes (system message, user messages, model, max_tokens, temperature, etc.), what return shape (text + token counts + raw provider response for debugging).
  - `AnthropicProvider` and `MistralProvider` implementations. Both raise on any non-recoverable failure (no silent fallback). Rate-limit handling strategy (retry with exponential backoff? immediate raise?). Network error handling. Malformed JSON response from the model handling.
  - System/user message separation — how the Gateway enforces it, how providers translate it into their respective SDK shapes (Anthropic uses `system` parameter; Mistral uses messages with `role: system` first).
  - How the Gateway is constructed at app startup (lazy initialisation? eager? singleton vs per-request?).
- **APILogger design:** the structured JSON shape, where files are written (or whether it writes to stdout / a logging sink), gating via `Settings.logging.api_log_enabled` (this setting needs to be added to `Settings`), what's redacted (PII in user messages must be configurable; for the prototype with synthetic data it's fine to log full content but the redaction hook should exist). How it integrates with the LLM Gateway — wrap-around or middleware-style.
- **Externalised prompts and PromptLoader:**
  - The `PromptLoader` class — methods, file resolution rules, formatting strategy (`.format(**kwargs)` vs Jinja2-style templates).
  - The first prompt files: `backend/app/prompts/system/validator.md` (role, output format, citation rules) and `backend/app/prompts/user/validator_template.md` (claim narrative + retrieved chunks placeholder).
  - The output schema for the Validator — exact JSON shape Mistral is asked to return, exact Pydantic model that parses it.
- **Validator agent design:**
  - The class structure (`Validator` with a single `evaluate(claim_id: UUID, correlation_id: UUID) -> ValidatorResult` method? functional alternative?).
  - The flow: load claim → embed narrative → retrieve top K chunks → assemble prompt → call Gateway → parse result → write audit log entry → return result.
  - Embedding model loading — lazy on first call, cached at module level, loaded eagerly at app startup? The model is ~50MB and takes ~3 seconds to load. Phase 2's tests shouldn't pay this cost on every test run.
  - Similarity search — exact pgvector query (cosine distance, ORDER BY embedding <=> query LIMIT 3).
  - Audit log entry — the payload shape; what gets logged at validator step (probably: input claim narrative excerpt, retrieved chunk IDs and similarity scores, prompt used, raw model response, parsed verdict, latency, token counts).
  - Defensive guards: what happens if the claim narrative is empty? if no chunks are retrieved? if the model returns malformed JSON? if the Gateway raises? Each guard needs a triggering test.
- **Testing strategy:**
  - How to test without making real LLM calls in CI. Three options: mock the Gateway entirely; use `respx` or `vcr.py` to record/replay HTTP cassettes; conditional real-call tests gated by an env var (like `RUN_EMBEDDING_TESTS` in Phase 1). Recommend one and explain.
  - Embedding model in tests — lazy-load once per test session via fixture, or skip embedding tests in CI? CI is on Linux x64 with no GPU, but the model is small enough that CPU encode of a few sentences is fast.
  - Real end-to-end test with actual Mistral call — gated by env var (e.g. `RUN_LLM_E2E_TESTS=1` with a `MISTRAL_API_KEY` set), opt-in only.
- **CI changes:**
  - The pgvector service container from Phase 1 stays.
  - Add the embedding model dependencies to the install step (already in `pyproject.toml` from Phase 1).
  - LLM-mocking strategy doesn't add CI dependencies if mocks are pure-Python; flag if `respx` or similar is added.
- **New dependencies — flag each one:**
  - `anthropic>=0.40` — Anthropic Python SDK.
  - `mistralai>=1.5` — Mistral Python SDK.
  - `tenacity` (optional) — for retry-with-backoff if you choose that strategy.
  - `respx` or `vcr.py` (optional) — for HTTP-level mocking; avoid if pure-Python mocks suffice.
- **Risks and downstream impacts:** the LLM Gateway interface, the Validator's return shape (`ValidatorResult` Pydantic model), and the audit-log payload shape for validator events all become contracts Phase 3+ depend on. Flag what locks at end of Phase 2.
- **Any deployment steps requiring my involvement:** typically setting `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` on Render's Environment tab once you ask for the values, then verifying the auto-redeploy goes Live without errors.
- **Optional enhancements** clearly labelled as optional. Deliver the spec first.

Save the plan **before** asking me to review it, so I can read it in my editor. Write it to:

```
docs/prompts/03-phase-2-llm-gateway-and-validator-plan.md
```

Top-level heading: `# Plan 03 — Phase 2: LLM Gateway and Validator Agent`. Below that, the body of the plan in the same shape it was produced.

After saving the file, point me at it and ask for my verdict. Do not write any other code or modify any other files yet.

## Step 2 — Approval or rejection

Same workflow as Phases 0 and 1 (per `docs/prompts/README.md`).

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

**If I reject** (any reply that is not unambiguous approval — including detailed feedback, a counter-proposal, or a request for changes):

Treat the current plan as rejected. Do not silently amend the canonical plan file. Instead:

1. Append a `## Rejection` footer to the existing plan file with timestamp, summary of feedback, and a pointer to the next iteration.
2. Rename the rejected file to `03-phase-2-llm-gateway-and-validator-plan-rejected-NN.md`.
3. Produce a revised plan and save it freshly as `docs/prompts/03-phase-2-llm-gateway-and-validator-plan.md`.
4. Return to Step 2.

Iterate as needed. Only after the canonical plan file carries an `## Approval` footer should you proceed to Step 3.

## Step 3 — Execute

After the plan is approved, execute Phase 2 per `BUILD-PLAN.md`. Constraints from `CLAUDE.md` apply throughout:

- **Defensive programming** (sanitise → validate → abort → execute) for every function that takes input. No silent fallbacks. Every guard has a triggering test.
- **Function size:** 30 lines is a prompt to reconsider; 50 lines is a hard limit. The Validator's `evaluate` method may be the most complex function in the project so far — split aggressively.
- **Settings hierarchy:** new fields appear in both `backend/settings.py` and `backend/settings.yaml.template`. No hardcoded model names, no hardcoded retry counts, no magic numbers.
- **Type hints** on every function signature.
- **Tests:** every new function gets tests; every guard clause gets a triggering test asserting on error message content.
- **Anonymisation:** the client name does not appear anywhere in code, comments, tests, fixtures, prompt files, or commit messages.
- **Security:** API keys loaded from env vars only. Never logged. The APILogger must redact API key values from any structured log output (the prompts and responses themselves are fine in a synthetic-data prototype).
- **Externalised prompts:** all LLM prompts live in `backend/app/prompts/system/` (role, format) and `backend/app/prompts/user/` (templates with placeholders). Loaded via `PromptLoader`. No inline f-string prompts in source code anywhere.
- **System/user message separation:** the Gateway enforces this. System message is always the role/format instruction; user messages carry the dynamic content. Per the global standard documented in the application-insight project (which Dermot's other projects follow).
- **Interface stability:** the `LLMProvider` interface, the `ValidatorResult` Pydantic shape, and the validator-step audit-log payload shape are interfaces that Phase 3+ depend on. Anything you'd later change requires explicit acknowledgement in the plan.

### Preamble fix-ups (do these before any other Phase 2 work)

Two small hygiene fixes that land in the same Phase 2 commit:

1. **Bump the project version** from `0.0.1` to `0.2.0` in `pyproject.toml`. Per-phase versioning makes the `/health` version field a useful traceability signal — when Render reports `0.2.0`, you know Phase 2's code is what's running. Future phases bump to `0.3.0` (Phase 3), `0.4.0` (Phase 4), etc.
2. **Tighten the Render production install** by changing `render.yaml`'s `buildCommand` from `uv sync` to `uv sync --no-dev`. The dev dependencies (pytest, ruff, mypy, pip-audit, types-pyyaml, httpx) don't belong in the production container — they only run in CI. The CI workflow in `.github/workflows/ci.yml` keeps its plain `uv sync` because CI needs the dev deps. This fix-up was identified by the parallel learning conversation 2026-05-09; flagged here so Phase 2 closes it as a small hygiene commit alongside the substantive work.

### API key handling

After I approve the plan, ask me explicitly:

> "Ready to execute. Please paste both `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` into the chat — I will use them to (a) populate the local `.env` file (gitignored), (b) run the Validator's end-to-end test against real LLMs once locally to confirm the flow works, and (c) instruct you to set them as environment variables on Render for the deployed backend. I will not commit them to the repository or log them anywhere."

Wait for the keys before proceeding past the LLM Gateway scaffold. The Gateway can be built and unit-tested without keys (using mocks); the Validator's real-call test needs them.

## Step 4 — Log

When the code work is complete, append a new entry to `docs/build-log.md` following the entry format documented at the top of that file. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/03-phase-2-llm-gateway-and-validator.md`.
- Plan (approved): link to `docs/prompts/03-phase-2-llm-gateway-and-validator-plan.md`.
- Plan iterations: count of rejected revisions, if any. List the rejected files inline.
- Report: link to `docs/prompts/03-phase-2-llm-gateway-and-validator-report.md`.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate, with breakdown (LLM Gateway tests, APILogger tests, PromptLoader tests, Validator unit tests, Validator end-to-end test status).
- Issues discovered.
- Next: Phase 3 — Remaining agents (Doc-Parser, Adjuster, Guardrail).

## Step 5 — Write the report

Save the report to `docs/prompts/03-phase-2-llm-gateway-and-validator-report.md`. The report opens with a `## Summary` block containing, in this order:

- **Recap** — one sentence stating what's done plus one sentence stating what comes next.
- **Completed at** — ISO 8601 UTC timestamp at the moment of report-writing.
- **Phase** — `2 — LLM Gateway and Validator agent`.
- **Status** — Complete / Complete with deferrals.
- Links to the prompt, the approved plan, and the repository.
- CI status if relevant.

Body sections cover files created and modified by tier, test counts and pass rates with breakdown, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 2:

- Date: today's date in ISO format.
- Phase: "Phase 2 complete; Phase 3 next".
- What works: a one-line summary of the new capability (e.g. "Validator agent runs end-to-end against synthetic claims via the LLM Gateway, producing structured coverage decisions with cited policy chunks. Audit chain captures every LLM call. No other agents yet.").
- What's next: "Phase 3 — Remaining agents (Doc-Parser, Adjuster, Guardrail)."

## Step 7 — Git

Make a single commit covering all the Phase 2 work, with the commit message:

```
Phase 2: LLM Gateway and Validator agent

- LLM Gateway with AnthropicProvider and MistralProvider
- APILogger writing one JSON record per LLM call
- PromptLoader with externalised system/user prompt files
- Validator agent: embed -> retrieve top 3 chunks -> augmented prompt -> Mistral -> typed verdict
- First externalised prompts: system/validator.md, user/validator_template.md
- Defensive guards throughout, every guard with a triggering test
- pyproject.toml version bumped 0.0.1 -> 0.2.0
- render.yaml buildCommand tightened to "uv sync --no-dev"
- Approved plan archived; build log entry appended; report written
- CLAUDE.md Current Status updated
```

Push to `main` so Render auto-deploys the new code.

## Step 8 — Report back

Per the global "After coding" section, report:

- Files created and modified.
- Test count and pass rate, with breakdown.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend for follow-on work.

End the report with the action items I still need to handle:

- Set `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` on Render's Environment tab to the values I supplied to you in chat. Render will auto-redeploy after the env var changes. Confirm the deploy goes Live without errors.
- Verify the deployed backend reaches the LLM providers (the deployed Validator endpoint, when called, should produce a real Mistral response — or check the Render logs for any startup-time provider initialisation errors).
