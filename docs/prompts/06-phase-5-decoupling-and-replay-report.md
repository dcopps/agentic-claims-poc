# Report 06 — Phase 5: Decoupling and Replay

## Summary

**Recap.** Phase 5 decouples submission from processing (a claim is persisted before any agent fires), writes the claim-status lifecycle as the pipeline runs, adds a configured replay variant whose runs are reconstructed side-by-side from the audit_log, and wires a functional (unpolished) React frontend to all of it. Next: Phase 6 — frontend polish.

**Completed at:** 2026-06-14T17:33:00Z
**Phase:** 5 — Decoupling and replay
**Status:** Complete (no deferrals; optional enhancements carried forward, labelled)

**Links**

- Prompt: [`docs/prompts/06-phase-5-decoupling-and-replay.md`](06-phase-5-decoupling-and-replay.md)
- Plan (approved): [`docs/prompts/06-phase-5-decoupling-and-replay-plan.md`](06-phase-5-decoupling-and-replay-plan.md) — approved 2026-06-14T16:14:04Z (two amendments)
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 5 entry)
- Repository: pushed to `main` after this commit lands; Render auto-redeploys.

**CI status.** Unchanged. The frontend Vitest runner was already present. No new gated categories; the one new gated `RUN_LLM_E2E_TESTS=1` replay-shaped real-call test joins the existing gated tests (none run in CI).

---

## Files created and modified, by tier

### Agents (audit extensions — the two approved amendments)
- **modified** `backend/app/agents/adjuster.py` — full `reasoning` added to the audit `output` block alongside `reasoning_excerpt` (amendment 1).
- **modified** `backend/app/agents/validator.py` — audit `llm_call.provider` reports `self._provider.vendor` (amendment 2); additive `user_template_name` constructor param.
- **created** `backend/app/prompts/user/validator_strict.md` — the strict user template.

### Claims domain
- **created** `backend/app/claims/models.py` — `ClaimStatus`, `ClaimType`, `ScenarioTag`, `ClaimSubmission` (defensive validators), `ClaimRecord`.
- **created** `backend/app/claims/repository.py` — `ClaimsRepository` (insert/get/list_claims/update_status), connection-scoped.
- **created** `backend/app/claims/__init__.py`.

### Runs domain
- **created** `backend/app/runs/models.py` — `RunStatus`, `RunSummary`, `DiffSummary`, `RunComparison`.
- **created** `backend/app/runs/repository.py` — `RunsRepository` (pure-read reconstruction) + `compute_diff`, `RunNotFoundError`, `RunClaimMismatchError`.
- **created** `backend/app/runs/__init__.py`.

### Variants
- **created** `backend/app/orchestrator/variants.yaml`, `variant_registry.py` (`VariantRegistry`, `VariantSpec`, `UnknownVariantError`), `variant_factory.py` (`resolve_validator_config`, `build_variant_orchestrator`).

### Orchestrator
- **modified** `backend/app/orchestrator/pipeline.py` — `run(...)` gains `variant`; injected `status_writer`; status writes per agent + finalisation, non-fatal.
- **modified** `backend/app/orchestrator/models.py` — additive `variant` on `PipelineStartedEvent`.

### API
- **created** `backend/app/api/claims.py`, `backend/app/api/runs.py`.
- **modified** `backend/app/api/pipeline.py` — `replay` endpoint; `run` gains `?variant=` + active-run guard; orchestrator construction routed through `get_orchestrator_factory`.
- **modified** `backend/app/api/__init__.py`, `backend/app/main.py` (lifespan loads the variant registry).

### Settings + packaging
- **modified** `backend/settings.py`, `backend/settings.yaml.template` — `PipelineSettings.variants_path`.
- **modified** `pyproject.toml` — version `0.4.0 → 0.5.0`.

### Frontend
- **created** `api/{types,client}.ts`, `copy/tooltips.ts`, `fixtures/demoClaims.ts`, `hooks/{useClaims,useRunStream}.ts`, `components/{Tooltip,ClaimForm,ClaimList,ProgressStrip,CompareView}.tsx`, plus tests; **modified** `App.tsx` and `App.test.tsx`.

---

## Test counts and pass rates

| Area | Tests |
|---|---|
| ClaimsRepository + submission | 13 |
| VariantRegistry + factory | 11 |
| RunsRepository reconstruction | 11 |
| Claims/runs/replay API | 12 |
| Orchestrator status + variant (added) | 4 |
| Integration (submit→run→replay→compare) | 1 |
| **Backend new** | **52** |
| Frontend (Vitest) | 13 total (+11) |

Repository: **277 backend passing, 6 skipped** + **13 frontend passing** = **290 passing, 6 skipped, 0 failing**. `ruff` clean; `mypy backend` clean (95 source files); frontend `tsc -b --noEmit` and `eslint .` clean.

---

## Deviations from the plan, with reasons

1. **`get_orchestrator` replaced by `get_orchestrator_factory`.** Routing both default and variant runs through one overridable factory gives the tests a single seam and lets `run` and `replay` share the default/variant logic. The Phase 4 API tests were updated to override the factory.
2. **`ClaimsRepository.list` named `list_claims`.** Avoids shadowing the builtin and reads clearly; the prompt's `list` was indicative.
3. **`RunsRepository.compare` lives in the repository (as specced) and raises typed errors** (`RunNotFoundError` → 404, `RunClaimMismatchError` → 400) that the API maps; the diff itself is a pure `compute_diff`.
4. **Runs tests use real agents with mock providers, not stubs.** Reconstruction reads the *agent-step* audit entries, which stub agents never write — so the round-trip is only meaningful against real agents.

No interface deviations: the `ClaimSubmission`/`ClaimRecord`/`RunSummary`/`RunComparison` shapes, the endpoint contracts, the variants schema, the status lifecycle, and the additive `variant`/`reasoning`/provider extensions all match the approved plan.

---

## Guard clauses added (each with a triggering test)

- `ClaimSubmission` — reversed dates, whitespace-only text fields, non-positive amount.
- `ClaimsRepository.update_status` — unknown status value; claim-not-found (zero rows).
- `ClaimsRepository.list_claims` — out-of-range limit.
- `VariantRegistry.load_from_yaml` — missing file/non-mapping/malformed YAML/missing `default`/unknown provider/unknown agent key (Literal + `extra="forbid"`).
- `RunsRepository.compare` — missing run (404), different claims (400).
- API — claim 404 (claims get/runs, replay, run pre-flight); unknown variant 404; no-prior-run 409; active-run 409; malformed UUID 422; submission 422.

## Guard clauses added that were not in the spec

- `update_status` value validation as a clean `ValueError` before the DB CHECK backstop (the spec described "reject illegal transitions"; the value check is the concrete, testable interpretation).
- The runs reconstruction synthesises an `EscalationDecision` for a guardrail-throw run (which has no `escalation_decision` audit entry) from the terminal entry's `fired_rule_names`, rather than nulling it.

---

## Optional enhancements recommended for follow-on work

Carried forward: retry via `tenacity`; pricing-table population; real PII redactor; prompt golden fixtures; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings` fields. New for Phase 5: introduce TanStack Query in Phase 6 (the prompt assumed it present; it is not); a `claim_status_history` table for ops; per-agent variant audit extension; a public `is_run_active` helper on the demo UI.

---

## Outstanding items requiring architect involvement

1. **Verify the Render redeploy completes and `/health` reports `version=0.5.0`.**
2. **Submit a new claim through the live UI; run it; replay it with `v2_strict_validator`; open the comparison view.** Confirm the diff fields make sense for the variant (the strict template typically lowers validator confidence, which can trip the confidence floor and escalate where the original auto-approved).
3. **Open the SSE stream during a replay** (`curl -N "$BACKEND/api/pipeline/stream/<uuid>"` while triggering `POST /api/pipeline/replay/<claim_id>?variant=v2_strict_validator&correlation_id=<uuid>`) and confirm the `variant` field appears on the `pipeline_started` event.
4. **Audit-payload extensions made for reconstruction — addendum to Phase 4's interface-stability list:**
   - The Adjuster `settlement_estimate` audit `output` block gains an **additive** `reasoning` field (full, alongside `reasoning_excerpt`). Amendment 1.
   - The Validator `coverage_check` audit `llm_call.provider`/`model` now report the **actual** provider/model in use (same keys, truthful values), not a hardcoded `"mistral"`. Amendment 2.
   - The `pipeline_started` audit payload and SSE event gain an **additive** `variant` field (default `"default"`).
   These are additive/value-only changes; existing keys are unchanged, so the Phase 3/4 audit-assertion tests continue to hold. They belong on the locked-interfaces list going forward.

No new env vars are required (`MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` already cover Phase 5). No CI changes.
