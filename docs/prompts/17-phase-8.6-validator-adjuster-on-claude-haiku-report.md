# Phase 8.6 — Report: Validator and Adjuster default to Claude Haiku; Mistral path retained as a variant

**Date:** 15 September 2026
**Prompt:** `17-phase-8.6-validator-adjuster-on-claude-haiku.md` · **Plan:** `17-phase-8.6-validator-adjuster-on-claude-haiku-plan.md` (approved as written, 15 September 2026)
**Version:** `0.8.5.3` → `0.8.6`

## Summary

The prototype's default pipeline now runs all four agents on Anthropic. The Validator and Adjuster run on Claude Haiku, and no Mistral provider is built on the default path. The Mistral path is retained:

- `MistralProvider` and its tests
- the `mistral-large-2512` pin and its pin-by-policy comment
- a new `v1_mistral` variant that routes the Validator and Adjuster back to Mistral

Each agent's provider is now a settings selector, so switching back is configuration, not code. Every document that describes what the prototype runs now says so. Production-target text is unchanged, apart from dated notes.

**Suite: 366 passed, 0 failed, 7 skipped (373 collected)**, up from 347 / 0 / 7 (354). `ruff` and `mypy` are clean.

**The deployed verification is pending.** This report is completed with its outcome in the follow-up commit.

## Decisions (Dermot, 15 September 2026)

1. `v2_haiku_validator`: **retired**.
2. Mistral variant name: **`v1_mistral`**.
3. Truthful `llm_call.provider` for all four agents: **locked-interface extension**, recorded in `CLAUDE.md`.
4. Version **`0.8.6`**; UI polish renumbered **Phase 8.7** (`0.8.6 → 0.9.0`).
5. `architecture-stack-reference.md`: **dated note**, table not edited.

Three items folded into scope:
- the stale `0.7.0` in `walkthrough.md`
- one live `v2_strict_validator` replay during verification
- the stale correlation-id comment in `Validator._invoke_llm`

## Files

**Modified — code:**
- `backend/settings.py`, `backend/settings.yaml.template`
- `backend/app/agents/{validator,adjuster,doc_parser,guardrail}.py`
- `backend/app/orchestrator/{pipeline,variant_factory,variant_registry}.py`, `backend/app/orchestrator/variants.yaml`
- `backend/app/api/agents_test.py`
- `pyproject.toml`, `uv.lock`

**Modified — tests:**
- `test_adjuster.py`, `test_doc_parser.py`, `test_guardrail.py`, `test_validator.py`
- `test_variants.py`, `test_pipeline_scenarios.py`

**New — tests:**
- `backend/tests/test_settings_providers.py`
- `backend/tests/test_agent_wiring.py`

**Modified — docs:**
- `CLAUDE.md`, `README.md`
- `docs/design-decisions.md`, `docs/dora-third-party-register.md`, `docs/architecture-stack-reference.md`, `docs/walkthrough.md`
- `diagrams/README.md`, `docs/BACKLOG.md`, `docs/build-log.md`

**New — docs:** the plan and this report.

**Not touched:**
- `MistralProvider` and its tests
- prompts
- embedding and vector index
- `diagrams/*.mmd`
- frontend
- Mistral account settings

**Dependencies:** none.

## Tests

| | Before | After |
| --- | --- | --- |
| Collected | 354 | **373** |
| Passed | 347 | **366** |
| Failed | 0 | 0 |
| Skipped | 7 | 7 |

**The wiring discriminator is `test_agent_wiring.py::test_default_wiring_builds_without_a_mistral_key` (plan test 12).**
- It builds the default orchestrator with no Mistral key. `get_provider(..., "mistral")` raises without a key, so the test passes only if the default path builds no Mistral provider at all.
- **Proven:** I temporarily re-wired the default Validator to `get_provider(settings, "mistral")`. The test failed with `ValueError: get_provider: MISTRAL_API_KEY is not set` (as did `test_default_wiring_routes_every_agent_to_anthropic_haiku`). With the wiring restored, both pass.

**Existing tests that stay green unchanged:**
- `test_llm_provider_mistral.py`
- `test_api_logger.py`
- the Mistral pin assertions in `test_settings_phase1.py`
- the gated live Mistral provider tests
- every `MockProvider`-based orchestrator and agent test, apart from the provider-label and `requested_model` assertions listed below

**Existing tests that were misleadingly green.** `test_adjuster.py` asserted `provider == "mistral"` against a `MockProvider`. It passed only because of the hardcoded label, and it now asserts `mock_provider.vendor`.

**Count: 19 new tests, against 16 planned.**
- One extra settings test: `provider_for` re-checks an unknown selector value on a mutated copy. That is a second call-time guard, added so an invalid copied value cannot silently resolve against the Mistral block.
- Two guard tests for `_set_provider` / `_set_model`, whose `else` branches refuse agents with no variant slot.

Every new guard has a test that checks its error message.

## Design decisions that differ from the plan

- **The `ResolvedValidatorConfig` / `resolve_validator_config` replacement** is exactly as planned: `resolve_variant_settings` plus `resolve_validator_template`. Its signature changed, so `_build_validator` now takes `settings` and `user_template_name` directly. Its callers are internal (the factory, the test bench and the tests).
- **README production column.** The plan said to leave the production column of the "LLMs" row. Its text read "Same models via Azure AI Foundry private endpoints". Once the prototype column changed, "same models" would have read as Haiku-only, so it now reads "Anthropic + Mistral models via Azure AI Foundry private endpoints". The meaning is unchanged; flagging it because it touches production-target text.
- **Walkthrough sentence placement.** The demo-script sentences sit in the threshold scene, after the Validator card is expanded (the explainability line). That is where the audit entry's model is naturally on screen.
- **`docs/prompts/README.md` index is not updated.** It has not been maintained past prompt 04; adding only row 17 would be inconsistent. Logged in `CLAUDE.md` → *Known debt*.

## Guard clauses added beyond the spec

- `LLMSettings.provider_for` re-checks the selector value at call time (see Tests above).
- `_set_provider` / `_set_model` in `variant_factory.py` refuse the Doc-Parser and Guardrail, which have no variant slot. The registry schema already prevents this, so these are defence in depth.

## Function size

- New functions are all under 30 lines. `build_variant_orchestrator` is about 40 lines including its docstring (roughly 20 of code).
- **Known debt, not fixed here:** the Validator, Adjuster and Guardrail `_build_audit_payload` builders were already over 50 lines. The Doc-Parser, Adjuster and Guardrail builders each gained a `provider_label` parameter plus docstring lines; the Validator already had one. This makes the backlog item *Split the oversized audit-payload builders* slightly more pressing.

## Deployed verification

*Pending — completed in the follow-up commit.* The sequence is in the plan §10 and in `docs/BACKLOG.md` → *Pending verifications*. The halt rule stands: a wrong terminal state stops the phase, with no prompt or token retuning.

## Suggestions for follow-on work

- **A variant selector for *Re-process*** instead of the hardcoded `v2_strict_validator` (Phase 8.7), so `v1_mistral` can be demoed from the UI once Mistral is paid.
- **Consolidate the `Literal["anthropic", "mistral"]` definitions.** There are now four: `settings.py`, `llm/factory.py`, `variant_registry.py`, `logging/api_logger.py`.
- **Update the *Startup model-access probe* item** (already noted in the backlog) to probe the model each selector resolves to (`model_for`), not every configured id.
