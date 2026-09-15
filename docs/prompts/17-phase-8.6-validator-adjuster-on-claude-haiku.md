# Phase 8.6 — Validator and Adjuster default to Claude Haiku; Mistral path retained as a variant

## Context

The prototype has been undemonstrable since Mistral withdrew Mistral Large from its Free tier. Phase 8.5.2 pinned the model to `mistral-large-2512`; Phase 8.5.3 proved from the audit row (run `56a0d5b2-a90d-43f3-866b-b5d35bd7f900`) that the deployed backend requests exactly that and Mistral refuses it with `403 tier_not_allowed`. The decision recorded in `docs/BACKLOG.md` → *Mistral tier decision* was between adding a payment method (option 1) and defaulting the two Mistral-backed agents to Claude Haiku (option 3). **Dermot chose option 3 on 14 September 2026.**

This phase makes the prototype's *default* pipeline run all four agents on Anthropic — Validator and Adjuster on Claude Haiku — while keeping the Mistral provider path fully intact, tested, and reachable through the variant mechanism, so that the day a Mistral payment method is added the switch back is configuration, not code.

This changes a **locked architectural decision** (`CLAUDE.md` → *Models*). That is deliberate and must be recorded honestly, with the distinction made explicit between *what the prototype runs by default* and *what the production architecture targets*. The production target (`docs/architecture-stack-reference.md`, `diagrams/4-production-architecture.mmd`) is unchanged: Mistral Large with a LoRA adapter for the Adjuster remains the design. What changes is the deployed prototype's default wiring.

## What this phase must achieve

1. **Default pipeline runs end-to-end on Anthropic.** All three scripted scenarios reach their expected terminal states in production with no Mistral call on the default path.
2. **Mistral path retained, not removed.** `MistralProvider`, its tests, the `mistral-large-2512` pin and its pin-by-policy comment all stay. A variant (name for the plan to choose — `mistral` or `v1_mistral` or similar) runs Validator and Adjuster through Mistral, so the substitution story remains demonstrable in code and re-enableable in one config change.
3. **Every document that describes what the prototype runs is truthful.** Every document that describes the production target is left describing the production target.
4. **The demo script says it out loud.** One or two sentences in `docs/walkthrough.md` explaining that the default runs on Claude, that the Mistral path exists as a variant, and why — this is a strength when stated (provider substitution exercised under real conditions), a weakness when discovered.

## Plan-first

Before writing any code, produce a written plan in `docs/prompts/17-phase-8.6-validator-adjuster-on-claude-haiku-plan.md` covering:

1. **Where the production providers are wired.** This is a *provider* swap, not only a model-string swap. Each agent holds `self._provider` (an `LLMProvider`) and reads a model id from settings; the Validator and Adjuster are currently constructed with a `MistralProvider`. Find every place the default Validator and Adjuster are built with their provider — the app factory / dependency wiring, `variant_factory.py`'s default path, any scripts (`verify-demo-scenarios.py`), and the agent test bench (`api/agents_test.py`) — and state what changes at each.

2. **Settings shape — decide and justify.** Today the ids live at `llm.mistral.validator_model` / `llm.mistral.adjuster_model`, and the `v2_haiku_validator` variant writes a Haiku id *into the mistral field* — workable for a variant, misleading as a default. Options: (a) add `llm.anthropic.validator_model` / `llm.anthropic.adjuster_model` (default `claude-haiku-4-5-20251001`), leave the `llm.mistral.*` fields in place with the 2512 pin for the Mistral variant, and add a per-agent provider selector (e.g. `llm.validator_provider: anthropic|mistral`, same for adjuster) that the wiring reads; or (b) something simpler the plan can defend.

   **Make the selector uniform across all four agents**, not just the two that change in this phase. Every agent sits behind the same LLM Gateway; the settings shape should say so — `doc_parser_provider` and `guardrail_provider` exist with default `anthropic` even though their behaviour does not change. That is the design `docs/design-decisions.md` §3 claims, and a selector that exists for only two of four agents undercuts it. Caveat to state plainly in the plan and in CLAUDE.md: only two combinations are *verified* — the all-Anthropic default and the Validator+Adjuster-on-Mistral variant. Doc-Parser or Guardrail on Mistral is structurally possible but untested; do not add tests for those combinations in this phase.

   **The vector index is unaffected and must not be touched.** Provider selection changes which LLM *reads* the retrieved policy chunks (as text in the prompt); it has no bearing on how they were *embedded* or *retrieved*. The embedding model (`BAAI/bge-small-en-v1.5`) is the one-way door named in CLAUDE.md and is not part of this phase. Whatever is chosen: new settings appear in both `settings.py` and `settings.yaml.template` (standing instruction), defaults resolve to the Anthropic path with no env vars set, and the settings hierarchy still applies (so a Render env var could flip an agent back to Mistral without a deploy — say so in the plan, and note that the pin-by-policy comment must move with or stay next to whichever field holds the Mistral id).

3. **Variant mechanism.** Today: default = Mistral, `v2_haiku_validator` = Haiku Validator. After: default = Anthropic for all four. Decide the fate of `v2_haiku_validator` (redundant with the new default — retire, or keep as a no-op alias with a note?) and define the new Mistral variant(s). `v2_strict_validator` is a user-template override, provider-independent — confirm it still works on the Haiku default. `variants.yaml` and `test_variants.py` updated accordingly. The *Re-process with v2* control in the UI must still do something meaningful; state what it will now do.

4. **Prompt compatibility on Haiku.** The Validator and Adjuster system/user prompts were written and tuned against Mistral Large (Phase 2/3, JSON via Mistral's `response_format`). Doc-Parser and Guardrail already run JSON-returning prompts on Haiku through `AnthropicProvider`, so the path is proven. State whether the Validator and Adjuster prompts need any change for Haiku, and check the `AnthropicProvider` JSON handling (`response_format="json"`) is what the Validator/Adjuster calls already use. **Do not retune prompts in this phase** unless a scenario fails in verification; if it does, halt and report rather than iterating on prompt wording.

5. **Scenario outcomes under Haiku — the real risk.** Phase 8 fix #5 tuned the Guardrail for the *Mistral* Adjuster's market vocabulary. Haiku's Adjuster output may phrase reasoning differently. The three scenarios must still land: auto-approve ($85k water damage — settlement under $250k, both confidences above floor, Guardrail clean), threshold escalation ($850k fire — `settlement_over_ceiling` fires), guardrail escalation ($1.4M storm — Adjuster is the Phase 7 fixture, so unaffected). The plan must state that verification runs all three on the deployed app and that a wrong terminal state halts the phase. List the specific fields to check per scenario.

6. **Documentation sweep with per-occurrence verdicts.** `grep -rn -i "mistral"` across `README.md`, `CLAUDE.md`, `docs/`, `diagrams/`, `frontend/src`, `backend/app/prompts`. For each hit, one of: *prototype claim → update*, *production-target claim → leave*, *historical/archived (build-log, docs/prompts) → leave*, *code/tests → handled in steps 1–3*. Known ones to address explicitly:
   - `CLAUDE.md` → *Architectural Decisions (Locked)* → *Models*: rewrite to distinguish prototype default from production target, with the date and the reason, and the variant name that restores Mistral.
   - `README.md` — any line stating the running model per agent.
   - `docs/design-decisions.md` §3 (*Mistral and Claude — a tiered, diverse model strategy*): add a dated note that the deployed default runs single-vendor after the Free-tier withdrawal, the Mistral path is retained as a variant, and that this is itself a demonstration of the substitutability the section argues for. Do not rewrite the section's argument.
   - `docs/dora-third-party-register.md` — Mistral stays registered (the path is retained); note that the default deployment exercises one provider.
   - `docs/walkthrough.md` — the demo-script sentence(s) from *What this phase must achieve* item 4.
   - `diagrams/1-headline-agent-flow.mmd` labels Validator/Adjuster as Mistral — decide: leave as the production-target diagram with a note in `diagrams/README.md`, or update. Prefer leave-plus-note; the `.mmd` files describe the target architecture.
   - Frontend: any agent description copy (`frontend/src/copy/agent-descriptions.ts`) or Agents-page label naming Mistral.

7. **Interface stability.** Audit payload *shapes* are unchanged. *Values* change: `coverage_check` and `settlement_estimate` rows will now carry `llm_call.provider = "anthropic"`, `model` / `requested_model` = the Haiku id. Phase 5's truthful-provider extension was built for exactly this. Any new settings fields are additive. If the variant name in `pipeline_started.variant` changes for the default, say so (it should stay `"default"`).

8. **Tests.** Existing Mistral-provider tests stay and stay green (the provider is retained). Agent tests that construct a Validator/Adjuster with `MockProvider` are provider-agnostic and should be unaffected — confirm. New tests: default wiring resolves Validator and Adjuster to an `AnthropicProvider` with the Haiku id; the Mistral variant resolves them to `MistralProvider` with `mistral-large-2512`; a settings test for any new fields and their defaults; the 8.5.3 `requested_model` variant test updated for the new variant names. State the expected count from the 347 / 0 / 7 baseline.

9. **Version and numbering.** This changes a locked architectural decision — larger than a point release. Propose `0.8.5.3 → 0.8.6` and call the phase **8.6**, renumbering the UI-polish phase in `docs/BACKLOG.md` to **8.7** (its version base becomes `0.8.6 → 0.9.0`). If you think this should stay in the 8.5.x incident series instead, argue it in the plan; Dermot decides.

10. **Deployed verification** — this finally discharges the Phase 8.4 / 8.5.2 seven-entry check that has been carried since June:
    1. `/health` → `0.8.6`.
    2. Reset Neon (hostname gate; `seed_claims --allow-truncate`; 9 claims; the 8.5.3 run left Northwood at `extracted`). Do not re-run `index_policy`.
    3. Run **all three** scripted scenarios from the Claims page. For each: expected terminal status; all four agent panels filled, no *Audit entry not found*; audit log entry count (seven for threshold and guardrail, six for auto-approve — confirm the exact expectation from the orchestrator code); chain verified; `coverage_check` and `settlement_estimate` show `provider = "anthropic"`, `requested_model` = `model` = Haiku id (guardrail scenario: `settlement_estimate` has `demo_fixture: true`, no `llm_call.prompt` / `requested_model`).
    4. Run the Mistral variant once via *Re-process* on any claim and confirm it aborts with the 403 and `coverage_check.requested_model = "mistral-large-2512"`, `provider = "mistral"` — proving the retained path is wired and reachable, and that the default is not accidentally still on Mistral.
    5. Record all of it in the build log and report.

Wait for explicit confirmation of the plan before writing any code.

## Deliverables (after plan is approved)

- Code: wiring, settings (`settings.py` + `settings.yaml.template`), `variants.yaml`, `variant_factory.py`, tests.
- `CLAUDE.md`: *Models* locked decision rewritten (prototype default vs production target, dated, variant named); Current Status; *Demo status* line cleared once verified.
- `README.md`, `docs/design-decisions.md`, `docs/dora-third-party-register.md`, `docs/walkthrough.md`, `diagrams/README.md`, frontend copy — per the sweep.
- `docs/build-log.md` — Phase 8.6 entry, including the three-scenario verification table and the Mistral-variant abort proof.
- `docs/BACKLOG.md` — *Mistral tier decision* resolved (remove; the decision and reasoning live in build-log); UI polish renumbered to 8.7 if agreed; add a *Future work* item *Re-enable Mistral as default* describing the one-config-change path once a payment method exists; carry over the *Split the oversized builders* item unchanged.
- `pyproject.toml` → `0.8.6`.
- `docs/prompts/17-…-plan.md`, `17-…-report.md`.
- Commit + push the code; then the reset + verification with Dermot; follow-up commit with the outcome.

## Constraints

- **Do not delete `MistralProvider`, its tests, the 2512 pin, or the pin-by-policy comment.** Retained path, not removed path.
- **Do not retune prompts.** If a scenario lands in the wrong state under Haiku, halt and report with the audit rows; that is a separate decision.
- **Do not touch the production-target documents' architecture** (`architecture-stack-reference.md`, the `.mmd` diagrams' content). Notes, not rewrites.
- **Do not add a Mistral payment method or change any Mistral account setting.**
- **Anonymisation and secrets rules apply** to every new line of prose.
- **Halt on any test failure** before commit.

## Standing conventions

Honour `CLAUDE.md` throughout — plan first; defensive ordering; no silent fallbacks (a provider selector with an unknown value must fail loud at startup, not fall back); function size limits; settings hierarchy and template parity; externalised prompts; commit frequently; security; dependency discipline (none expected); interface stability acknowledgement.

## Archive

This prompt is pre-saved at `docs/prompts/17-phase-8.6-validator-adjuster-on-claude-haiku.md`. Plan and report alongside with `-plan.md` / `-report.md`.
