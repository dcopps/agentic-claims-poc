# Report 05 — Phase 4: Pipeline Orchestrator

## Summary

**Recap.** Phase 4 wires the four Phase 2/3 agents into a single end-to-end pipeline under one correlation_id, adds a typed escalation policy engine driven by `policy.yaml`, and exposes a synchronous trigger endpoint plus an SSE progress-stream endpoint — the three locked demo scenarios pass end-to-end. Next: Phase 5 — decoupling and replay.

**Completed at:** 2026-06-14T15:16:00Z
**Phase:** 4 — Pipeline orchestrator
**Status:** Complete (no deferrals; optional enhancements carried forward, labelled)

**Links**

- Prompt: [`docs/prompts/05-phase-4-pipeline-orchestrator.md`](05-phase-4-pipeline-orchestrator.md)
- Plan (approved): [`docs/prompts/05-phase-4-pipeline-orchestrator-plan.md`](05-phase-4-pipeline-orchestrator-plan.md) — approved 2026-06-14T14:00:04Z
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 4 entry)
- Repository: pushed to `main` after this commit lands; Render auto-redeploys.

**CI status.** Unchanged. No new service containers, no new gated test categories beyond the existing `RUN_LLM_E2E_TESTS=1`. One new gated real-call test (the auto-approve pipeline) joins the four prior gated tests; none run in CI.

---

## Files created and modified, by tier

### Escalation policy engine

- **created** `backend/app/escalation/policy.yaml` — the single authoritative rule set: `version`, `watchlists` (claim_types, claimants — empty for the demo), `cross_jurisdictional_markers` (`/`, `multi-jurisdiction`, `cross-border`), four `hard_rules`, three `threshold_rules`.
- **created** `backend/app/escalation/models.py` — `PipelineState`, `FiredRule`, `EscalationDecision`, `RuleType`. Placed here (not in the orchestrator package) so the dependency is one-directional.
- **created** `backend/app/escalation/policy.py` — `EscalationPolicy.load_from_yaml` (all I/O + schema validation at load) and `evaluate(state) -> EscalationDecision` (pure; OR semantics; fail-closed per-rule). `PolicyDocument`'s Literal-typed fields reject an unknown rule name / threshold field / comparator at load. Monetary and confidence comparisons are exact `Decimal`.
- **modified** `backend/app/escalation/__init__.py` — exports the engine and shared types.

### Orchestrator

- **created** `backend/app/orchestrator/models.py` — `PipelineResult`, `PipelineStatus`, `FailingAgent`, the six-member `PipelineEvent` union, `EventEmitter`; re-exports the escalation types.
- **created** `backend/app/orchestrator/event_bus.py` — `PipelineEventBus` (per-correlation `asyncio.Queue`, buffered late-subscriber delivery, terminal-driven teardown after a grace period, thread-safe `publish_threadsafe`).
- **created** `backend/app/orchestrator/pipeline.py` — `PipelineOrchestrator`; `run(...)` as named helper calls; the abort matrix; agent collaborators typed as Protocols; three pipeline-level audit entries under `agent="orchestrator"`.
- **created** `backend/app/orchestrator/__init__.py` — public surface.

### API

- **created** `backend/app/api/pipeline.py` — the two endpoints, the lazy `get_orchestrator` dependency, the thread→loop emit bridge, the pre-flight claim check.
- **modified** `backend/app/api/__init__.py` — mounts the pipeline router under `/api`.
- **modified** `backend/app/main.py` — `lifespan` (loads policy fail-fast, builds the event bus; orchestrator built lazily); `create_app` stashes settings on `app.state`.

### Settings + packaging

- **modified** `backend/settings.py` — `PipelineSettings` (`event_grace_period_s`, `event_queue_maxsize`) with named-constant defaults; `EscalationSettings` docstring notes superseded fields.
- **modified** `backend/settings.yaml.template` — `pipeline:` block; escalation comment refreshed.
- **modified** `pyproject.toml` — version `0.3.0 → 0.4.0`; `sse-starlette>=2.1`; ruff `extend-immutable-calls = ["fastapi.Depends"]`.
- **modified** `uv.lock` — `sse-starlette` 3.4.4.

### Tests

- **created** `backend/tests/test_escalation_policy.py` (20), `test_pipeline_event_bus.py` (8), `test_pipeline_orchestrator.py` (10), `test_api_pipeline.py` (6), `test_pipeline_scenarios.py` (3 + 1 gated).

### Docs

- **modified** `CLAUDE.md` — Current Status → "Phase 4 complete; Phase 5 next".
- **created** the plan, this report; build-log entry appended.

---

## Test counts and pass rates

| Area | Tests |
|---|---|
| Escalation policy engine | 20 |
| Pipeline event bus | 8 |
| Pipeline orchestrator | 10 |
| Pipeline API | 6 |
| Integration scenarios | 3 (+1 gated real-call) |
| **Phase 4 new total** | **47 passing + 1 gated** |

Repository: **225 backend passing, 6 skipped** (the Phase-1 embedding test + five `RUN_LLM_E2E_TESTS=1` gated tests) + **2 frontend passing** = **227 passing, 6 skipped, 0 failing**. `uv run ruff check .` clean; `uv run mypy backend` clean (81 source files).

---

## Deviations from the plan, with reasons

1. **Shared escalation types live in `escalation/models.py`, not `orchestrator/models.py`.** The plan sketched `PipelineState` / `EscalationDecision` / `FiredRule` in the orchestrator package, but the escalation engine consumes `PipelineState` and produces the decision types — defining them in the orchestrator package would make the escalation engine import back from the orchestrator (a cycle). They live in `escalation/models.py` and are re-exported from the orchestrator for a single import surface. No shape change.
2. **Timestamps are stamped in the orchestrator, not at the API edge.** The plan suggested the edge emitter stamp event timestamps to keep the orchestrator "clock-agnostic". In practice the orchestrator already stamps `completed_at`, and every existing agent stamps its own `created_at` via `datetime.now(UTC)` — so the orchestrator stamps event timestamps inline too, consistent with the codebase. Tests assert on event order and payload, not timestamps.
3. **The orchestrator is built lazily, not at startup.** The plan's lifespan built the orchestrator eagerly. `Validator.with_defaults` cold-loads the 50 MB embedder, which would penalise every app startup (health probes, CI). The lifespan loads only the cheap policy (still fail-fast) and event bus; the orchestrator is built on first pipeline request and cached. The policy "load once at startup" requirement is preserved.
4. **Ruff config gained `extend-immutable-calls`.** FastAPI's `Depends()` is designed to be called in argument defaults; B008 flags every endpoint. One config line (`extend-immutable-calls = ["fastapi.Depends"]`) keeps the endpoints idiomatic without per-line `# noqa`. It does not relax B008 for any other call.

No other deviations. The `PipelineResult`, `EscalationDecision`, SSE event payloads, and the two endpoint shapes match the approved plan.

---

## Guard clauses added (each with a triggering test asserting on message content)

- `EscalationPolicy.load_from_yaml` — missing file, non-mapping YAML, bad `version`, unknown hard-rule name, unknown threshold field, bad comparator, unparseable threshold value.
- `EscalationPolicy.evaluate` — fail-closed: a per-rule evaluation error (e.g. a `PipelineState` built via `model_construct` with a hole) escalates with a synthetic fired rule rather than crashing or silently passing.
- `PipelineEventBus.__init__` — negative grace period, zero queue maxsize.
- `PipelineEventBus._put` — full-queue overflow is dropped and logged, never raised into the run.
- `PipelineOrchestrator` abort matrix — doc-parser/validator/adjuster throw → `aborted` naming the agent; guardrail throw → `awaiting_human` (fail-closed).
- API — unknown claim_id → 404 (pre-flight, so no `pipeline_started`/`pipeline_aborted` pair is written for a bad request); malformed path UUID → 422.

---

## Guard clauses added that were not in the spec

- The `PipelineEventBus._put` full-queue drop-and-log (the spec mentioned a maxsize cap; the explicit non-raising drop is an added safety so a runaway event volume can never fail the pipeline itself).
- The fail-closed branch in `EscalationPolicy.evaluate` wraps *every* rule, not only the documented missing-field case — any unexpected per-rule error escalates rather than aborting.

---

## Optional enhancements recommended for follow-on work

Carried forward (still deferred): retry via `tenacity`; pricing-table population for `cost_usd`; real PII redactor; prompt golden-text fixtures.

New for Phase 4 (labelled, not built):

1. **Per-agent timeout** in the orchestrator (each `evaluate` under a deadline) — guards a hung provider beyond the per-call `request_timeout_s`.
2. **Idempotent re-run protection** on `POST /run` (reject a second run for a claim already `settled`) — likely Phase 5 territory, needs a claim-status write.
3. **Promote the internal `_AgentFailure` / `_GuardrailFailure` to a public exception module** if Phase 5 needs to catch them across the event boundary.
4. **SSE heartbeat** — only if a live run risks Render's proxy timeout (it does not at current latencies).
5. **Consolidate the superseded `EscalationSettings` numeric fields** — delete them once nothing else reads them, leaving `policy.yaml` as the sole source.

---

## Outstanding items requiring architect involvement

1. **Verify the Render redeploy completes and `/health` reports `version=0.4.0`** after this commit lands on `main`.
2. **Exercise `POST /api/pipeline/run/{claim_id}`** against a seeded claim from the deployed backend; confirm the three demo scenarios behave correctly live.
   - **Reproducibility note:** scenarios 1 and 2 (auto-approve, threshold) are reproducible from the seeded fixtures alone — the seeded $85k water-damage and $850k fire claims drive `settled` and threshold-`awaiting_human` respectively, given normal model output. **Scenario 3 (guardrail escalation) is not reproducible from the seeded fixtures alone in this phase**: it depends on the Guardrail flagging a hallucinated endorsement, which in turn depends on the Adjuster's live reasoning actually surfacing one. The seeded $1.4M storm claim narrative *mentions* an unlisted endorsement, but whether the live Adjuster echoes it and the live Guardrail flags it is non-deterministic. In the integration test this is forced deterministically by mocking the Guardrail's LLM flag. For a reliable live demo of scenario 3, a small prompting nudge (or a fixture Adjuster reasoning) may be needed — flagged for Phase 7 demo polish.
3. **Open the SSE stream** against a known correlation_id (`curl -N "$BACKEND/api/pipeline/stream/<uuid>"`) while triggering `POST /run/<claim_id>?correlation_id=<uuid>`, and confirm the event sequence matches the locked schema (`pipeline_started` → `agent_started`/`agent_completed` ×4 → `escalation_decision` → `pipeline_completed`).

No new env vars are required (`MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` already cover Phase 4). No CI changes.
