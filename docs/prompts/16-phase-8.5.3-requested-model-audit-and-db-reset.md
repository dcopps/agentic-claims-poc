# Phase 8.5.3 — Record `requested_model` in agent audit payloads; reset the deployed DB

## Context

Phase 8.5.2 pinned the Validator and Adjuster defaults to `mistral-large-2512` and deployed as `0.8.5.2`. The deployed verification run (`11f97ae8-7dc6-4b41-9b8e-16c85d4bd073`, 14 September 2026) aborted at the Validator with the same `403 tier_not_allowed` as before the pin.

The `coverage_check` audit row for that run could not settle the obvious question — *which model string did the runtime actually send?* — because on the error path the `llm_call` block records only `provider`, `latency_ms`, and (since Phase 8.3) `prompt`. Phase 5's truthful-model extension sources `llm_call.model` from `response.model`, the model that *answered*; on a 403 there is no response, so there is no `model` key. The answer had to be reached by eliminating every other settings path (pinned default deployed per `/health`; no `settings.yaml` on Render; no CLI flags in the start command; no `LLM__MISTRAL__*` env var). That elimination is sound, but the audit-log-as-trusted-record property is supposed to make it unnecessary: *the audit log alone is sufficient to reconstruct and explain any past decision* — including a decision that failed.

This phase closes that gap so the next verification run answers the question conclusively from the audit row, and resets the deployed database so that run starts clean.

Two parts. Part A is code. Part B is an operational step, not code.

## Part A — `llm_call.requested_model` on every agent audit payload

Add `requested_model: str` to the `llm_call` block of all four agent audit payloads (`doc_extract`, `coverage_check`, `settlement_estimate`, `output_check`), on **both** the success path and the error path. The value is the model identifier the agent passed to `provider.complete(model=…)` — i.e. the resolved settings value at call time (`self._settings.llm.anthropic.*_model` or `self._settings.llm.mistral.*_model`).

Properties this must have:

- **Present whenever a call was attempted**, regardless of outcome. Success path: alongside the existing `model` (responding). Error path: alongside `provider` and `latency_ms`.
- **Absent when no call was attempted.** The Adjuster's demo-fixture path (Phase 7) sends no request, so it emits no `requested_model` — the same truthfulness rule Phase 8.3 applied to `prompt`. A missing key means "no request was made", never "we forgot to record it".
- **Captures variant overrides correctly.** `variant_factory.py` overrides `cfg.llm.mistral.validator_model` on a per-variant settings copy; because `requested_model` is read from the settings the agent actually used at call time, a `v2_haiku_validator` run will record `requested_model = "claude-haiku-4-5-20251001"`. This is the desired behaviour — the audit records what the variant asked for.
- **Additive.** Nested under the existing `llm_call` block. All existing keys (`provider`, `model`, `prompt_tokens`, `completion_tokens`, `latency_ms`, `prompt`) unchanged. Same shape of extension as Phase 8.3's `prompt`.

A mismatch between `requested_model` and `model` on a success path is itself diagnostic (an alias resolving to a different dated release than expected). That is a feature, not something to suppress.

## Part B — reset the deployed database before the verification run

Today's failed submissions left the deployed Neon database with four `Northwood Manufacturing Inc` rows and several claims stuck in `extracted`. Before the Phase 8.5.3 verification run, reset it:

```
uv run python -m backend.data.seed_claims --allow-truncate
```

against the **Neon** `DATABASE_URL`. This is the same procedure Claude Code ran on 3 August 2026 during the Phase 8.4 repopulation. Requirements, in order:

1. **Confirm target before running.** Echo the *hostname only* of the resolved `DATABASE_URL` (never the full URL, never the password). It must end in `.neon.tech`. If it does not, stop and ask.
2. **Acknowledge what TRUNCATE CASCADE clears.** `claims` and, via the FK cascade, `audit_log` — including today's diagnostic runs `26a9bf4e-…` and `11f97ae8-…`, which the Phase 8.5.2 build-log entry references by correlation id. Those references will point at rows that no longer exist. This is acceptable — the build log records the *finding*, and the audit rows are demo data on a prototype — but it must be a conscious choice, stated in the report, not a side effect. `policy_chunks` is **not** touched by `seed_claims`; do not re-run `index_policy` (the retrieval in run `11f97ae8` proved the index is intact: three chunks, fire peril ranked first at 0.589).
3. **Verify the count afterwards.** `SELECT COUNT(*) FROM claims` must be exactly 9; the three scripted scenarios (`auto_approve`, `threshold_escalation`, `guardrail_escalation`) must be present with status `received`.
4. **Do this after the code is deployed, immediately before the verification run** — not before the commit. The reset and the verification should be one operational sequence.

The Phase 8.5 pytest guard is `conftest.py`-only and does not apply here; `seed_claims` is a deliberate operator action against the deployed DB.

## Plan-first

Before writing any code, produce a written plan in `docs/prompts/16-phase-8.5.3-requested-model-audit-and-db-reset-plan.md` covering:

1. **Where the requested model is threaded from.** Each agent's `_invoke_llm` reads the model from settings when it calls `provider.complete(model=…)`. Decide how that value reaches `_build_audit_payload` — as an explicit parameter alongside `prompt` (preferred: keeps the payload builder pure and testable), or by reading settings inside the builder. Note that `_build_audit_payload` is a module-level function in at least `guardrail.py`, so it cannot read `self._settings` without a parameter change anyway. If a `_shared.py` helper in the style of `attach_prompt` keeps the four agents consistent, propose it; if it is a one-liner that a helper would over-abstract, say so and inline it. Either is acceptable; the plan should choose and justify.
2. **The four agents, one by one.** For each of `doc_parser.py`, `validator.py`, `adjuster.py`, `guardrail.py`: which settings field is the source, where `_invoke_llm` reads it, where the payload builder is called on the success and error paths, and confirmation that the Adjuster fixture branch omits the key.
3. **Interface stability acknowledgement.** Additive key under `llm_call` on all four agent payloads. Existing keys, shapes, columns, HTTP responses, SSE events unchanged. Existing audit rows and the hash chain unaffected. Requires a new bullet in `CLAUDE.md` → *Locked interface extensions since Phase 4*, phrased like the Phase 8.3 bullet, including the omit-when-no-call rule.
4. **Test design.** Mirror Phase 8.3's per-agent prompt-capture tests: one test per agent asserting `requested_model` equals the configured model on the **success** path, and one per agent on the **error** path (provider raises `LLMProviderError`; the audit row is still written — Phase 3 — and must carry `requested_model`). Extend `test_demo_fixture.py` with `assert "requested_model" not in llm_call` alongside the existing `assert "prompt" not in llm_call`. Add one variant test: run the Validator under the `v2_haiku_validator` variant and assert `requested_model` is the Haiku id. Expected count: **338 → 347** (8 per-agent + 1 fixture-absence assertion inside an existing test may not add a test; state the exact expected number after reading the fixtures). Any deviation from the stated count must be explained.
5. **Frontend.** No change. The Audit page's JSON viewer renders the raw payload, so the new key appears automatically. `AgentCard` does not need to surface it. State this explicitly so it is a decision, not an omission.
6. **Version treatment.** Point release: `0.8.5.2 → 0.8.5.3`. This continues the 8.5.x series that began with the Mistral incident. Bump `pyproject.toml`.
7. **Part B sequencing.** Confirm the reset happens *after* commit/push/redeploy and *immediately before* the verification run, per Part B step 4, and that the hostname check is the first thing that happens.
8. **Deployed verification (this phase's proof).** The Mistral tier decision has *not* been made; the Validator will still 403. That is expected. The verification for this phase is narrower than a full seven-entry run:
   1. `/health` → `0.8.5.3`.
   2. Part B reset; confirm 9 claims.
   3. Process the seeded `threshold_escalation` claim (it is fresh again after the reset).
   4. The run aborts at the Validator — expected.
   5. Open the audit log for that run. Expand `coverage_check`. **`llm_call.requested_model` must read `mistral-large-2512`.** That is the conclusive evidence Phase 8.5.2 could not produce. Also confirm `doc_extract`'s `llm_call` carries both `requested_model` and `model` (success path), and that they match (`claude-haiku-4-5-20251001`).
   6. Record the result in the build log and report. This also lets the Phase 8.5.2 entry be amended with a definitive statement rather than an elimination argument.

Wait for explicit confirmation of the plan before writing any code.

## Deliverables (after plan is approved)

1. `backend/app/agents/doc_parser.py`, `validator.py`, `adjuster.py`, `guardrail.py` — `requested_model` threaded into the `llm_call` block on success and error paths; Adjuster fixture path omits it.
2. `backend/app/agents/_shared.py` — helper, if the plan chose one.
3. Tests per plan step 4.
4. `CLAUDE.md` — new bullet under *Locked interface extensions since Phase 4*; Current Status updated (date, phase 8.5.3, version, what works, what's next).
5. `pyproject.toml` — `0.8.5.3`.
6. `docs/build-log.md` — Phase 8.5.3 entry. **Also amend the Phase 8.5.2 entry** with a short *"Deployed verification outcome"* paragraph: failed on 14 September, 2512 gated on Free tier, the Limits-page premise was wrong, conclusive `requested_model` evidence to follow from 8.5.3. Link to the corrected understanding in `docs/BACKLOG.md` → *Mistral tier decision*.
7. `docs/BACKLOG.md` — remove the *Record `requested_model` on the error-path `llm_call`* item from *Future work* (it is being built). Leave *Mistral tier decision* as is; it is still open. Note the reset in *Pending verifications* as done once Part B completes.
8. `docs/prompts/16-phase-8.5.3-requested-model-audit-and-db-reset-plan.md` and `…-report.md`.
9. Commit and push the code. Then, with Dermot, run Part B and the verification, and append the outcome to the build log and report in a follow-up commit.

## Constraints

- **Do not make the Mistral tier decision.** Do not add a payment method, do not change any default to a Claude model, do not touch the variant mechanism. The Validator 403 is expected in this phase's verification.
- **Do not run `seed_claims --allow-truncate` before the code is committed and deployed.** Part B is the last step before verification, not the first step of the phase.
- **Do not re-run `index_policy`.** The vector index is intact.
- **Do not print or log the `DATABASE_URL`** — hostname only, for the target check.
- **Halt on any test failure** before commit.

## Standing conventions

Honour `CLAUDE.md` throughout — defensive ordering, no silent fallbacks, function size limits (30-line prompt to reconsider, 50-line hard limit — the four `_build_audit_payload` functions are already substantial; if adding a key pushes one over, extract rather than annotate), settings hierarchy, externalised prompts, frequent commits, security discipline, dependency discipline, interface stability acknowledgement.

## Archive

This prompt is pre-saved at `docs/prompts/16-phase-8.5.3-requested-model-audit-and-db-reset.md`. Plan and report go alongside it with the `-plan.md` and `-report.md` suffixes.
