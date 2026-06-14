# Prompt 05 — Phase 4: Pipeline Orchestrator

## Read first

Before doing anything else, read these files in this directory:

- `CLAUDE.md` — global standards reference, project overview, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 4.
- `docs/prompts/04-phase-3-remaining-agents-report.md` — what Phase 3 delivered and the interfaces it locked. The four agent output Pydantic models, the audit-log payload shapes, and the market-data lookup's typed return are inputs the orchestrator orchestrates against — those contracts are load-bearing for Phase 4.
- `backend/app/agents/validator.py` and `backend/app/agents/adjuster.py` — the two agents most consequential for the pipeline. Read enough to know the `evaluate(...)` signature, what each returns, and how each writes to the audit vault.
- `backend/app/agents/_shared.py` — the small helper module shared across the Phase 3 agents.
- `backend/app/audit/writer.py` — how audit-log entries are appended under a correlation_id. Phase 4 adds a pipeline-level audit entry on top of the per-agent entries the agents already write.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. The relevant items: plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts (no inline f-strings), system/user message separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 4 of `BUILD-PLAN.md` — Pipeline orchestrator. By the end of this phase:

- The four Phase 2/3 agents (Doc-Parser → Validator → Adjuster → Guardrail) run as a single end-to-end pipeline against any seeded claim.
- An **escalation policy engine** consumes `backend/app/escalation/policy.yaml` and produces a typed decision after Guardrail returns. The locked policy (per `CLAUDE.md`) has OR semantics across hard rules (always escalate: `guardrail_failed`, `claim_type_watchlist`, `claimant_watchlist`, `cross_jurisdictional`) and threshold rules (`settlement > $250,000`, `validator_confidence < 0.65`, `adjuster_confidence < 0.75`). Every decision logs which rules fired.
- A **synchronous trigger** REST endpoint accepts a claim_id, runs the pipeline, and returns the typed outcome (`settled` / `awaiting_human` / `aborted`).
- A **Server-Sent Events endpoint** streams agent progress to the frontend in real time as each agent completes.
- The three locked demo scenarios behave correctly end-to-end: auto-approve ($85k water damage), threshold escalation ($850k fire), guardrail escalation ($1.4M with hallucinated endorsement).
- Complete audit trail per claim under one correlation_id: every per-agent entry the agents already write, plus pipeline-level entries (`pipeline_started`, `escalation_decision`, `pipeline_finalised`).

No frontend changes beyond the SSE endpoint contract (the frontend wiring is Phase 6). No decoupling / replay (Phase 5). No demo polish (Phase 7). Phase 4 builds the orchestrator, the policy engine, the two endpoints, and verifies the three scenarios.

Plus the per-phase preamble fix-up bundled into the same Phase 4 commit:

- Bump `pyproject.toml` version `0.3.0` → `0.4.0`. The `/health` `version` field on the deployed backend will then read `0.4.0` after the Phase 4 push, confirming Phase 4 code is live.

## Current state of the project (for orientation)

Phase 3 delivered:

- Three agents (`backend/app/agents/doc_parser.py`, `adjuster.py`, `guardrail.py`) joining the Phase 2 Validator. Each runs in isolation against seeded claims and writes a structured audit entry per call.
- A shared helper module at `backend/app/agents/_shared.py` (`extract_json_block`, `excerpt`, `clamp_unit`, `new_correlation_id`).
- The market-data lookup at `backend/data/market_data.yaml` (six claim_types × three severities) and its typed loader at `backend/data/market_data.py`.
- Per-agent Pydantic models (`*_models.py`) — typed inputs, typed outputs, audit-payload shapes locked.
- ~180 backend+frontend tests passing; ruff and mypy clean across the codebase.
- `/health` reports `version=0.3.0`.

The deployment chain is intact. `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` are set on Render and confirmed working. All four agents have been exercised end-to-end against real model endpoints individually; no agent has yet run as part of a composed pipeline.

The frontend (`frontend/`) currently shows the Phase 0 "backend: ok" probe; no UI work is in scope for this phase.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering everything below.

### Shared questions to answer

Before describing the implementation, address these cross-cutting design decisions in the plan:

1. **Where does the orchestrator live, and what's its interface?**
   - Recommended: `backend/app/orchestrator/pipeline.py` with a `PipelineOrchestrator` class. Constructor takes the four agents (already-constructed instances), the `EscalationPolicy`, the `AuditWriter`, the `APILogger`, and `Settings`. A single public method `run(claim_id: UUID) → PipelineResult` runs the pipeline synchronously.
   - Alternative: a module-level `run_pipeline(claim_id, ...)` function. Less easy to mock; harder to inject collaborators in tests.
   Recommend one. Phase 5's decoupling work will wrap whatever this is in an event-driven trigger; the synchronous trigger here is the reference shape.

2. **How is the correlation_id managed?** The orchestrator generates a fresh `correlation_id` at entry, passes it explicitly to each agent's `evaluate(...)` call, and includes it on every audit entry it writes itself. Confirm that every Phase 2/3 agent's `evaluate(...)` accepts an injected `correlation_id` rather than generating its own; if any agent currently self-generates, surface it as a deviation needing a small fix-up in this phase. The pipeline must be queryable end-to-end by correlation_id from the audit vault.

3. **Agent failure handling — abort, escalate, or surface?** If `Doc-Parser` throws, the pipeline can't proceed; abort with a typed result `aborted` and a clear error attribution. If `Validator` throws, same. If `Adjuster` throws, abort. If `Guardrail` throws, escalate to human (fail-closed posture — a broken guardrail should not be silently accepted). Document the matrix in the plan and lock it. Every abort writes a `pipeline_aborted` audit entry naming the failing agent and the exception type. Do *not* convert agent exceptions to escalation decisions silently; only Guardrail-throw maps to escalation, and only because Guardrail's whole semantics are fail-closed.

4. **Where does the escalation policy engine live?**
   - Recommended: `backend/app/escalation/policy.py` with `EscalationPolicy.load_from_yaml(path) → EscalationPolicy` and `EscalationPolicy.evaluate(state: PipelineState) → EscalationDecision`. Pure function on a typed input; no I/O during `evaluate`.
   - The YAML schema lives at `backend/app/escalation/policy.yaml` (location locked in `CLAUDE.md`). Specify the schema in the plan: a `version`, a list of `hard_rules` (each with `name`, `condition`, `description`), and a list of `threshold_rules` (each with `name`, `field`, `comparator`, `value`, `description`). Recommend the simplest practical schema; don't introduce a DSL.
   - Loading: load once at FastAPI startup (lifespan), inject into the orchestrator, treat as immutable for the request lifecycle. Re-load only via a deliberate restart. Document this; tests can construct policies in-memory.

5. **What does the typed `PipelineResult` and `EscalationDecision` look like?** Sketch the Pydantic models in the plan. Suggested shape:
   - `EscalationDecision { escalate: bool, fired_rules: list[FiredRule], reasoning: str }` where `FiredRule` carries `name`, `rule_type` (`hard` or `threshold`), `description`, and the relevant field value if a threshold rule.
   - `PipelineResult { status: PipelineStatus, claim_id, correlation_id, escalation_decision: EscalationDecision | None, doc_parser_output, validator_output, adjuster_output, guardrail_output, completed_at }`.
   - `PipelineStatus = Literal["settled", "awaiting_human", "aborted"]`.
   These are the interfaces Phase 5 (decoupling), Phase 6 (frontend) and Phase 7 (demo) consume; treat as locked at end of Phase 4.

6. **SSE event structure.** Each event needs a typed payload, an event name, and the correlation_id. Suggested event types:
   - `pipeline_started` — claim_id, correlation_id, timestamp.
   - `agent_started` — agent name, correlation_id, timestamp.
   - `agent_completed` — agent name, correlation_id, duration_ms, brief summary (one or two fields per agent — e.g. Validator's verdict.covered boolean).
   - `escalation_decision` — fired_rules list, escalate boolean.
   - `pipeline_completed` — final PipelineStatus, summary.
   - `pipeline_aborted` — failing agent, exception type and message (sanitised — no secrets, no PII).
   - Optional `heartbeat` every N seconds to keep the connection live; recommend skipping unless a pipeline run can exceed Render's default request timeout.
   Document the JSON shape per event. Treat as locked at end of phase.

7. **How are the two endpoints structured?**
   - Recommended split: `POST /api/pipeline/run/{claim_id}` (synchronous; runs the whole pipeline and returns the final `PipelineResult`) and `GET /api/pipeline/stream/{correlation_id}` (SSE; the synchronous trigger publishes events to an in-process pub/sub keyed by correlation_id; the SSE handler subscribes and yields).
   - Alternative: a single `POST /api/pipeline/run/{claim_id}` that *is* the SSE response — the same request both triggers and streams. Simpler but couples trigger to client connection lifetime; if the client disconnects, the run is harder to track. The two-endpoint split is recommended.
   - For the in-process pub/sub, recommend a tiny `PipelineEventBus` class (in-memory `dict[correlation_id, asyncio.Queue]`, with a TTL or explicit cleanup on `pipeline_completed`). Don't introduce Redis or external pub/sub for this phase; Phase 5 may revisit when decoupling.

8. **Where is the audit-log entry for the pipeline written?** Each agent already writes its own audit entries. The orchestrator writes three additional entries under the same correlation_id: `pipeline_started`, `escalation_decision`, and one of `pipeline_settled` / `pipeline_awaiting_human` / `pipeline_aborted`. Specify the exact payload shapes in the plan; treat as locked at end of phase.

### Pipeline implementation details

For each step of the pipeline (Doc-Parser → Validator → Adjuster → Guardrail → Escalation → Outcome), the plan should specify:

- The helper method name inside `PipelineOrchestrator` (each ≤30 lines, decomposed faithfully).
- The expected input and output types.
- The SSE event(s) emitted around it.
- The audit entries written.
- The failure mode and what it produces (per question 3 above).

The orchestrator's public `run(...)` method should read as a sequence of named helper calls (`_extract`, `_validate`, `_adjust`, `_guard`, `_decide_escalation`, `_finalise`), each delegating to the right collaborator and emitting the right events.

### Escalation policy details

- The YAML schema (with the locked rules expressed inline so the engine has something concrete to load on day one).
- The exact rule names that must be recognised (`guardrail_failed`, `claim_type_watchlist`, `claimant_watchlist`, `cross_jurisdictional`, plus three threshold rules).
- The `claim_type_watchlist` and `claimant_watchlist` lists live in policy.yaml under named keys; agree on whether the lists are case-sensitive (recommend case-insensitive matching after a normalising guard).
- For threshold rules: comparators (`>`, `<`, `>=`, `<=`); confidence fields read from the relevant agent's typed output.
- The `evaluate(...)` semantics: OR across all rules; any one rule firing → `escalate=True`. The fired_rules list captures every rule that fired, not just the first.
- Defensive guards: invalid YAML schema → fail at startup with a clear error, not at first request. Unknown rule name in YAML → fail at load. Missing required field on `PipelineState` → fail-closed (treat as escalation, log the gap).

### SSE implementation

- `sse-starlette` is already a locked dependency per `CLAUDE.md`. Use `EventSourceResponse`.
- Confirm the integration sets the right headers for Render's reverse proxy (no `X-Accel-Buffering: no` needed for SSE-starlette by default, but worth verifying once during execution).
- The SSE stream emits typed events as JSON in the `data:` payload, with `event:` set to the event-type name. The frontend (Phase 6) will consume these by event name.
- Cleanup: on `pipeline_completed` or `pipeline_aborted`, the orchestrator publishes the terminal event and tears down the queue keyed by correlation_id (with a short grace period for late subscribers).

### Demo scenario verification (definition-of-done evidence)

Build integration tests that exercise the three scripted demo scenarios end-to-end against the seeded claims, with the LLM layer mocked at the LLMProvider boundary (the same testing posture used in Phases 2 and 3). Each test asserts:

1. **Auto-approve scenario** — $85k water damage seed claim → `PipelineResult.status == "settled"`, no fired rules, audit trail shows every agent succeeded and no escalation.
2. **Threshold escalation scenario** — $850k fire loss seed claim → `PipelineResult.status == "awaiting_human"`, fired_rules includes `settlement > $250,000`, audit trail shows Guardrail passed but escalation fired.
3. **Guardrail escalation scenario** — $1.4M loss with the Adjuster output mocked to contain a hallucinated endorsement reference → Guardrail returns `pass=False`, `PipelineResult.status == "awaiting_human"`, fired_rules includes `guardrail_failed`, regardless of the threshold rules' state.

Each of these is one integration test. Plus one opt-in real-call test (gated by `RUN_LLM_E2E_TESTS=1`) that exercises the auto-approve scenario against the actual LLM endpoints.

### Testing strategy

- Unit tests for `PipelineOrchestrator` with each agent mocked. Cover happy path, each abort case (one per agent throwing), and Guardrail-fail-closed.
- Unit tests for `EscalationPolicy`: each hard rule fires correctly; each threshold rule fires at correct boundaries; OR-combination tests; missing-field guards trigger; YAML-schema-load failures surface usefully.
- Unit tests for the `PipelineEventBus`: subscribe → publish → unsubscribe; late subscriber after publish (queued or dropped — document the choice); cleanup behaviour.
- Integration tests: the three demo scenarios above.
- API tests: the two endpoints behave correctly under happy paths and obvious failure modes (unknown claim_id, claim already settled, etc.).
- One opt-in real-call test exercising the auto-approve scenario.

Aim ~35–50 new tests across the orchestrator, policy engine, event bus, integration scenarios, and API surface. Update the running total in the report.

### CI changes

- No new service containers, no new gated test categories beyond `RUN_LLM_E2E_TESTS=1` (already in place since Phase 2).

### New dependencies — flag each one

If your plan introduces any beyond `sse-starlette` (already locked), flag and justify per the dependency-discipline standard. The expected answer is **one new** (`sse-starlette`); if you find yourself adding more, surface why before writing code.

### Risks and downstream impacts

The Pydantic `PipelineResult`, `EscalationDecision`, and SSE event payload shapes lock at end of Phase 4 — Phase 5 (decoupling) and Phase 6 (frontend) both consume them. Enumerate the locked contracts in the plan, same shape as Phases 2 and 3.

The `PipelineEventBus` is an in-process construct; flag that Phase 5 may replace it with a real event bus (Service Bus in production, in-process for prototype) and that the SSE endpoint's coupling to in-process subscribers is a deliberate prototype simplification.

### Deployment steps requiring architect involvement

Same as Phases 2 and 3: after the commit lands and pushes, Render auto-redeploys. No new env vars are required. The architect verifies `/health` returns `version=0.4.0` after the redeploy, and exercises the synchronous `POST /api/pipeline/run/{claim_id}` against a seeded claim from the deployed backend to confirm the pipeline runs end-to-end live.

### Optional enhancements

Clearly labelled, delivered separately, never silently. Carry forward from Phase 3's report the items still deferred (retries via tenacity, pricing table population, real PII redactor, prompt golden-text fixtures). Add any Phase 4 enhancements you'd recommend — likely candidates: a per-agent timeout, idempotent re-run protection on the synchronous endpoint, structured exception types for pipeline aborts.

### Save the plan

Save the plan **before** asking me to review it, so I can read it in my editor. Write it to:

```
docs/prompts/05-phase-4-pipeline-orchestrator-plan.md
```

Top-level heading: `# Plan 05 — Phase 4: Pipeline Orchestrator`. Below that, the body of the plan.

After saving the file, point me at it and ask for my verdict. Do not write any other code or modify any other files yet.

## Step 2 — Approval or rejection

Same workflow as Phases 0, 1, 2, and 3 (per `docs/prompts/README.md`).

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

**If I reject**, append a `## Rejection` footer, rename the file to `05-phase-4-pipeline-orchestrator-plan-rejected-NN.md`, produce a revised plan as the fresh canonical file, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 4. Constraints from `CLAUDE.md` apply throughout:

- **Defensive programming** (sanitise → validate → abort → execute) for every function that takes input. Every guard has a triggering test that asserts on message content.
- **Function size:** 30 lines is a prompt to reconsider; 50 lines is a hard limit. The orchestrator `run(...)` method decomposes into named helpers; the helpers themselves stay small.
- **Settings hierarchy:** any new fields appear in both `backend/settings.py` and `backend/settings.yaml.template`. No hardcoded values. No magic numbers without a named constant and a comment. The escalation thresholds live in policy.yaml; the policy.yaml path lives in settings.
- **Type hints** on every function signature.
- **Tests:** every new function gets tests; every guard clause gets a triggering test asserting on error-message content.
- **Anonymisation:** the client name does not appear anywhere — code, comments, tests, fixtures, prompt files, policy file, commit messages.
- **Security:** no new credentials introduced in Phase 4. The policy.yaml is plain configuration, not secret. Pipeline event payloads on SSE never carry secrets or unsanitised exception strings.
- **Externalised prompts:** Phase 4 introduces no new LLM calls (the agents already own theirs). No new prompts.
- **System/user message separation:** no LLM calls in the orchestrator. Untouched.
- **Interface stability:** the `PipelineResult`, `EscalationDecision`, SSE event payloads, and the two endpoint shapes are interfaces Phases 5–7 depend on.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.3.0` → `0.4.0`. The `/health` `version` field then reflects Phase 4 once deployed.

## Step 4 — Log

When the code work is complete, append a new entry to `docs/build-log.md`. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/05-phase-4-pipeline-orchestrator.md`.
- Plan (approved): link to `docs/prompts/05-phase-4-pipeline-orchestrator-plan.md`.
- Plan iterations: count of rejected revisions, with links to each.
- Report: link to `docs/prompts/05-phase-4-pipeline-orchestrator-report.md`.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate, with breakdown by area (orchestrator, policy engine, event bus, API, integration scenarios).
- Issues discovered.
- Next: Phase 5 — Decoupling and replay.

## Step 5 — Write the report

Save the report to `docs/prompts/05-phase-4-pipeline-orchestrator-report.md`. The report opens with a `## Summary` block containing, in this order:

- **Recap** — one sentence stating what's done plus one sentence stating what comes next.
- **Completed at** — ISO 8601 UTC timestamp at the moment of report-writing.
- **Phase** — `4 — Pipeline orchestrator`.
- **Status** — Complete / Complete with deferrals.
- Links to the prompt, the approved plan, and the repository.
- CI status if relevant.

Body sections cover files created and modified by tier, test counts and pass rates with the breakdown above, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 4:

- Date: today's date in ISO format.
- Phase: "Phase 4 complete; Phase 5 next".
- What works: a one-line summary of the new capability (e.g. "The four agents now run as a single composed pipeline against any seeded claim under one correlation_id; the escalation policy engine evaluates hard and threshold rules and produces a typed decision; a synchronous REST endpoint runs the pipeline and an SSE endpoint streams progress events; the three locked demo scenarios behave correctly end-to-end. No decoupling / replay yet; that's Phase 5.").
- What's next: "Phase 5 — Decoupling and replay."

## Step 7 — Git

Make a single commit covering all the Phase 4 work, with the commit message:

```
Phase 4: pipeline orchestrator + escalation policy + SSE streaming

- PipelineOrchestrator wiring Doc-Parser -> Validator -> Adjuster -> Guardrail
- EscalationPolicy engine consuming backend/app/escalation/policy.yaml (OR semantics)
- POST /api/pipeline/run/{claim_id} synchronous trigger
- GET /api/pipeline/stream/{correlation_id} SSE progress events
- PipelineEventBus in-process pub/sub keyed by correlation_id
- Pipeline-level audit entries (started, escalation_decision, finalised/aborted)
- Three demo scenarios verified end-to-end (auto-approve, threshold, guardrail)
- Defensive guards throughout, every guard with a triggering test
- pyproject.toml version bumped 0.3.0 -> 0.4.0
- Approved plan archived; build log entry appended; report written
- CLAUDE.md Current Status updated
```

Push to `main` so Render auto-deploys.

## Step 8 — Report back

Per the global "After coding" section, report:

- Files created and modified.
- Test count and pass rate, with breakdown by area.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend for follow-on work.

End the report with the action items I still need to handle:

- Verify the Render redeploy completes and `/health` reports `version=0.4.0`.
- Exercise `POST /api/pipeline/run/{claim_id}` against a seeded claim from the deployed backend; confirm the three demo scenarios behave correctly live (auto-approve, threshold escalation, guardrail escalation). The guardrail scenario relies on Adjuster returning a hallucinated endorsement; document in the report whether this is reproducible from the seeded fixtures alone or requires manual prompting nudges in this phase.
- Open the SSE stream against a known correlation_id (via `curl -N` or similar) while a synchronous run is in flight, and confirm the event sequence matches the locked schema.

## Save this prompt

Per the "Save every prompt" standing instruction in `CLAUDE.md`, save this prompt verbatim to `docs/prompts/05-phase-4-pipeline-orchestrator.md` if it isn't already there.
