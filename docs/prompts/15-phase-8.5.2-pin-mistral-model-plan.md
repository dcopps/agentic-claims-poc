# Phase 8.5.2 — Plan: pin Mistral model to `mistral-large-2512`

Plan produced in response to `docs/prompts/15-phase-8.5.2-pin-mistral-model.md`.
Date: 2026-09-14. Version: `0.8.5.1 → 0.8.5.2`.

## Supporting evidence found during the sweep

`docs/prompts/03-phase-2-llm-gateway-and-validator.md:35` records that on
2026-05-09 the key was confirmed working against `mistral-large-latest`
**"(resolves to `mistral-large-2512`)"**. So in May the alias *was* 2512. Pinning
to 2512 therefore restores exactly the model the prototype was built, tuned and
demoed against — it is a return to known-good behaviour, not a move to an
untested model. The 403 is Mistral re-pointing the alias at a newer release
gated to a paid tier.

## 1. Files-to-modify sweep

Command: `grep -rn "mistral-large"` across the repo (excluding `.git`,
`.venv`, `node_modules`, `dist`). Every hit is listed below; `frontend/`,
`README.md`, `diagrams/`, `docs/build-log.md` and
`docs/architecture-stack-reference.md` have **no** occurrences.

### Must update

| Location | Why |
|---|---|
| `backend/settings.py:211` `validator_model` default | Drives the runtime model sent to Mistral for the Validator. The fix itself. |
| `backend/settings.py:212` `adjuster_model` default | Same, for the Adjuster. The Adjuster would hit the identical 403 once the Validator stops aborting first. |
| `backend/settings.yaml.template:62-63` | Template must mirror `settings.py` defaults (standing instruction). An operator copying the template to `settings.yaml` would otherwise reinstate the broken alias with higher precedence than the default. |
| `backend/settings.yaml.template:92` — commented `pricing` example key | **Not in the prompt's starting list.** Runtime pricing is looked up by *exact* model string (`api_logger.py:202`, `pricing.get(model)`). An operator who uncomments this example would get a rate keyed on `mistral-large-latest` that never matches `mistral-large-2512` — `cost_usd` silently null for every Validator/Adjuster call. Update the example so it is copy-paste-correct. Comment-only change. |
| `backend/tests/test_settings_phase1.py:53-54` | Asserts the default equals the alias; must assert the new pinned default. |
| `backend/tests/test_settings_phase2.py:115,118` | The prompt's condition is met — the app *does* look up pricing by model ID at runtime. Note, honestly, that this test is itself string-agnostic (it builds its own `LLMSettings` and reads back its own key; it never touches the default), so leaving it would not break anything. Updating it keeps the one pricing-map example in the test suite aligned with the key an operator actually needs. Cosmetic alignment, zero behavioural coupling. |

### Can stay

| Location | Why |
|---|---|
| `backend/tests/test_api_logger.py:34` | `_record()` builder input for `APICallRecord` validation tests. No assertion on the string; sibling tests in the same file use `model="anything"` and `model="m"`, confirming the file is model-string-agnostic. |
| `backend/tests/test_llm_provider_mistral.py:82,120,148,174` | `model=` argument to `provider.complete()` against a monkeypatched `chat.complete`. The fake client ignores it and nothing asserts on it. Arbitrary mock input independent of the production default. |
| `backend/tests/test_llm_provider_mistral.py:27` | Already `mistral-large-2512` (fake *response* model — mirrors what the alias resolved to in May). No change. |
| `backend/tests/test_variants.py:159,170` | **No literal occurrence.** Line 159 captures `original_model` dynamically from `db_settings`; line 168 asserts the override is `claude-haiku-4-5-20251001`; line 170 compares against the captured value. Fully string-agnostic — survives the pin untouched. |
| `docs/prompts/02-phase-1-data-layer-plan.md:37` | Archived historical plan. The prompt archive is a verbatim build record; rewriting it would falsify history. |
| `docs/prompts/03-phase-2-llm-gateway-and-validator.md:35` | Archived historical prompt (and the evidence cited above). Leave. |
| `docs/prompts/03-phase-2-llm-gateway-and-validator-plan.md:136` | Archived; already shows `mistral-large-2512` as an example audit value. Leave. |
| `docs/prompts/15-phase-8.5.2-pin-mistral-model.md` | This phase's own prompt. Leave. |
| `docs/change-governance.md:60` `mistral-large-ft-claims-v3` | Not the alias — a hypothetical production LoRA fine-tune identifier in the change-governance example. Unrelated. Leave. |

## 2. Interface stability acknowledgement

- **What changes:** the *value* of `llm_call.model` in newly written
  `coverage_check` (Validator) and `settlement_estimate` (Adjuster) audit rows,
  and the `model` column in API-call log records: `mistral-large-latest` →
  `mistral-large-2512`.
- **What does not change:** JSON shape, field names, nesting, types, DB
  columns, CHECK constraints, HTTP response shapes, SSE event shapes. Existing
  audit rows are untouched (and the hash chain is unaffected — only new rows are
  written with the new value).
- **Observable difference, flagged explicitly:** anyone diffing a pre-pin run
  against a post-pin run will see the model value differ. This is intentional
  and is in fact the proof the pin reached the runtime path (verification step 4).
- **Why no downstream break:** `llm_call.model` is a free-form provenance
  string. A consumer pattern-matching on `mistral-large-latest` would be broken
  by design, since the alias's meaning already changed server-side without any
  change on our side. Arguably the pin *improves* the audit's trustworthiness: a
  moving alias never recorded which model actually answered, whereas a pinned
  version does — which matters for the "audit log alone reconstructs any past
  decision" property.
- The Phase 8.3 `llm_call.prompt` and Phase 5 truthful `provider`/`model`
  extensions are unaffected — the latter simply reports the new configured value.

## 3. Locked architectural decision preservation

`CLAUDE.md` → *Architectural Decisions (Locked)* → "Mistral Large (Validator,
Adjuster)" remains true: `mistral-large-2512` is a Mistral Large release. No edit
to that section. The pin is operational (which release of the locked family we
call), not architectural. Current Status gains the pin and its rationale.

## 4. Version treatment

`pyproject.toml` `version = "0.8.5.1"` → `"0.8.5.2"`. `/health` resolves via
`importlib.metadata`, so this is the only version source. `uv sync` (implicit in
`uv run`) refreshes the installed metadata so the local `/health` reflects it.
`test_health.py` asserts only non-empty, stays green.

## 5. Test strategy

- No new tests — configuration value change; the settings-load path is already
  covered by `test_llm_settings_defaults_match_locked_models`.
- Gate: `uv run pytest` against `agentic_claims_test` must show **338 passed,
  0 failed, 7 skipped** (345 collected). Any failure halts the phase before
  commit, per the prompt's constraint.
- Also run `uv run ruff check .` and `uv run mypy` (both clean at baseline).

## 6. Post-deploy verification

1. `curl https://agentic-claims-poc-backend.onrender.com/health` → `0.8.5.2`.
2. Process the seeded Northwood $850k fire (threshold-escalation scenario) on
   the deployed frontend.
3. Validator completes (no 403); pipeline reaches `awaiting_human`; all four
   agent expand panels show filled prompts and JSON responses with no
   `Audit entry not found` banners. (This also discharges the Phase 8.4
   deployed audit-persistence check if it passes cleanly — to be confirmed with
   you rather than assumed.)
4. `coverage_check` audit entry `llm_call.model` reads `mistral-large-2512`.

## Risks

1. **Render environment override (most important).** `Settings` uses
   `env_nested_delimiter="__"`, so an env var such as
   `LLM__MISTRAL__VALIDATOR_MODEL` on Render would outrank the new default and
   the pin would silently not take effect. The local `.env` sets only
   `ANTHROPIC_API_KEY`, `DATABASE_URL`, `MISTRAL_API_KEY`, and no
   `backend/settings.yaml` exists (gitignored, so none on Render either). I
   cannot see Render's env vars — please confirm no `LLM__MISTRAL__*` variable
   is set there. Verification step 4 catches this regardless.
2. **Prove the Adjuster pin too, not just the Validator.** The threshold
   scenario calls the Adjuster live — the Phase 7 demo fixture is keyed only on
   `scenario_tag == "guardrail_escalation"` (`adjuster.py:98-100`). So a clean
   Northwood run exercises both pinned defaults. Proposed addition to step 4:
   also confirm the `settlement_estimate` entry's `llm_call.model` reads
   `mistral-large-2512`. (Do **not** use the $1.4M guardrail scenario for this —
   its Adjuster output is a fixture with no model call.)
3. **Pin ageing.** 2512 will eventually be deprecated — tracked by the new
   *Mistral tier upgrade path* backlog item.
4. **Rate limit.** 1.00 req/s on the Free tier. The pipeline makes at most two
   sequential Mistral calls per run, so a single demo run is well inside it;
   concurrent demo runs could 429. Pre-existing condition, not introduced here.

## Dependencies

None added.

## Deliverables (execution order)

1. `backend/settings.py` — both defaults pinned.
2. `backend/settings.yaml.template` — lines 62-63 pinned; line 92 example key updated.
3. `backend/tests/test_settings_phase1.py:53-54`, `backend/tests/test_settings_phase2.py:115,118`.
4. `pyproject.toml` → `0.8.5.2` (and `uv.lock` if `uv` rewrites the project version entry).
5. Run pytest / ruff / mypy; halt on any failure.
6. `docs/BACKLOG.md` — *Mistral tier upgrade path* under *Future work*, verbatim body from the prompt.
7. `docs/build-log.md` — Phase 8.5.2 entry (deployed-verification outcome marked pending until the redeploy).
8. `CLAUDE.md` Current Status — date, phase 8.5.2, version, what works, what's next.
9. `docs/prompts/15-phase-8.5.2-pin-mistral-model-report.md`.
10. Commit + push (triggers Render redeploy), then run post-deploy verification with you and append the outcome to the build log and report in a follow-up commit.

## Approval and amendments (2026-09-14)

Plan approved by Dermot with these amendments, all actioned:

- **Optional suggestion 2 taken** — pin-by-policy comment added to
  `MistralProviderSettings` in `settings.py` (template points at it). Same
  reasoning as the Phase 8.4 stale-contract cleanup: a comment stating the
  now-true contract stops a future session reverting the pins to `-latest`.
- **Optional suggestion 1 logged, not built** — *Startup model-access probe*
  added to `docs/BACKLOG.md` under *Future work*, with today's 403 as the
  motivating incident.
- **Risk 2 addition accepted** — verification step 4 confirms **both**
  `coverage_check` and `settlement_estimate` read `mistral-large-2512`, using
  the threshold scenario (never the $1.4M guardrail scenario, whose Adjuster
  is a fixture).
- **Verification step 2 changed** — submit a *fresh* claim via the form's
  *Threshold escalation ($850k fire)* template button rather than the seeded
  Northwood row, which was touched by today's failed run.
- **Risk 1 owned by Dermot** — the Render `LLM__MISTRAL__*` env-var check is
  confirmed before or alongside the redeploy.

## Optional suggestions (not in scope — not to be done in this phase)

- **Startup model-access probe.** A `/health`-adjacent check (or a one-off
  script) that calls Mistral's models-list endpoint and confirms the configured
  model IDs are accessible, so a re-tiering surfaces as a clear config error
  before a claim is processed rather than as a mid-pipeline abort.
- **Pin-by-policy note in `settings.py`.** A short comment on the Mistral
  defaults explaining *why* they are pinned versions not aliases (moving aliases
  break silently on tier changes and make the audit's `model` field
  non-reproducible). Tiny, and it would stop a future session "tidying" them
  back to `-latest`. Happy to fold this in if you want it — it is a comment, not
  behaviour.
