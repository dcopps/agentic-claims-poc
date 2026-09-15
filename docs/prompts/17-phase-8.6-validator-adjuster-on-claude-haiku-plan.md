# Phase 8.6 — Plan: Validator and Adjuster default to Claude Haiku; Mistral path retained as a variant

**Date:** 15 September 2026
**Prompt:** `docs/prompts/17-phase-8.6-validator-adjuster-on-claude-haiku.md`
**Baseline (re-run at plan time):** 347 passed, 0 failed, 7 skipped (354 collected), version `0.8.5.3`.

---

## 0. Findings that shape the plan

Reading the code turned up four facts the prompt does not mention. Each one changes the work.

- **F1 — The Adjuster's audit hardcodes `provider: "mistral"`.** `backend/app/agents/adjuster.py:91` sets `_PROVIDER_LABEL = "mistral"`, and `_llm_call_block` writes it on every live-call path. Only the Validator got Phase 5's truthful-provider fix (`self._provider.vendor`). If the wiring changes and nothing else does, every Haiku `settlement_estimate` row would record `provider: "mistral"`. The audit log would then contradict the model id sitting right next to it. **Doc-Parser (`doc_parser.py:80`) and Guardrail (`guardrail.py:88`) hardcode `"anthropic"` the same way.** With a uniform per-agent selector those two rows would also be wrong whenever a selector points elsewhere. **The plan extends Phase 5's truthful-provider rule to all four agents** (§7). The payload shape is unchanged. Only the value becomes truthful.
- **F2 — The audit entry count is seven for all three scenarios, not six for auto-approve.** `PipelineOrchestrator.run` writes `pipeline_started`. Each agent writes exactly one entry (`AuditWriter(conn).append` appears once per agent module). `_finalise` always writes `escalation_decision` plus a terminal step (`pipeline_settled` or `pipeline_awaiting_human`). No branch skips `escalation_decision` for a non-escalating run, so the count is 1 + 4 + 2 = **7** in every case. The guardrail scenario also gets 7: the Guardrail *returns* `passed: false`, which is not the throw path, so it goes through `_finalise` like the others.
- **F3 — The *Re-process* button cannot reach the Mistral variant.** `frontend/src/pages/ClaimsPage.tsx:12` hardcodes `REPLAY_VARIANT = 'v2_strict_validator'`. Step 4 of the verification therefore uses the endpoint the button calls, `POST /api/pipeline/replay/{claim_id}?variant=v1_mistral`, and views the result in the UI. This plan makes no frontend change (see §3 and the optional suggestions).
- **F4 — The "proven JSON-on-Haiku path" is the Guardrail only.** Since Phase 8.2 the Doc-Parser asks for `response_format="text"` and returns prose. The Guardrail also passes `"text"` but parses a JSON object via `extract_json_block`, so it is the real precedent. I found **no recorded live run of the Validator on Haiku** in `docs/build-log.md`: the only `v2_haiku_validator` evidence is the Phase 8.5.3 unit test. The README's statement that the variant "has been exercised" has no build-log entry behind it. This phase's deployed verification will be the first recorded live Validator-on-Haiku run.

---

## 1. Where the providers are wired, and what changes at each

| Site | Today | After |
|---|---|---|
| `backend/app/orchestrator/pipeline.py` `PipelineOrchestrator.with_defaults` (the cached default orchestrator built by `api/pipeline.py::get_orchestrator_factory`) | `validator` and `adjuster` get `get_provider(settings, "mistral")`; doc-parser and guardrail get `"anthropic"` | Each agent gets `get_provider(settings, settings.llm.<agent>_provider)`. With default settings, **no `MistralProvider` is built**, so the default path no longer needs `MISTRAL_API_KEY`. |
| `backend/app/orchestrator/variant_factory.py` `build_variant_orchestrator` | Resolves the Validator override only. The Adjuster is always Mistral; `_DEFAULT_VALIDATOR_PROVIDER = "mistral"` is a module constant | Resolves the variant into a **deep-copied `Settings`** (selectors and model ids overridden) and builds all four agents from it, using the same selector logic as the default. The module constant is removed: the default provider now comes from settings. |
| `backend/app/api/agents_test.py` (agent test bench) | Adjuster hardcoded to `"mistral"` and ignores `?variant=`; doc-parser and guardrail hardcoded to `"anthropic"`; Validator follows the variant | All four endpoints resolve the provider from the variant-resolved settings, so `?variant=v1_mistral` really sends the Adjuster test to Mistral. This is a behaviour change for the test bench's Adjuster under a variant. The HTTP shape is unchanged. |
| `scripts/verify-demo-scenarios.py` | Calls the deployed HTTP API only; builds no providers | **No change.** It checks the terminal status and fired rule, which apply to either provider. |
| `backend/tests/test_pipeline_scenarios.py:429` (gated live E2E, `RUN_LLM_E2E_TESTS=1`) | Hand-wires Validator and Adjuster on `"mistral"` | Wires from the settings selectors, so the gated live test tracks the real default. It stays skipped in CI. |
| `backend/tests/test_validator.py:633`, `test_adjuster.py:653` (gated live provider tests) | `get_provider(..., "mistral")` | **No change.** These are Mistral-provider live tests and the provider is retained. |

**Provider cache.** `get_provider` memoises on `id(settings)`. Variant runs deep-copy `Settings`. If providers were keyed on the copy, every replay would add a cache entry, and a garbage-collected copy's reused `id` could return a stale provider. **Providers are therefore always looked up on the shared `Settings`; only the agents receive the copy.** Provider construction reads only keys, logging and pricing, and no variant overrides those. The current `build_variant_orchestrator` already does this implicitly. This plan keeps it and adds a comment explaining why.

---

## 2. Settings shape — option (a), uniform across all four agents

```yaml
llm:
  # Per-agent provider selector. One of: anthropic, mistral.
  doc_parser_provider: anthropic
  validator_provider: anthropic
  adjuster_provider: anthropic
  guardrail_provider: anthropic
  anthropic:
    orchestrator_model: claude-sonnet-4-6
    doc_parser_model: claude-haiku-4-5-20251001
    guardrail_model: claude-haiku-4-5-20251001
    validator_model: claude-haiku-4-5-20251001     # new
    adjuster_model: claude-haiku-4-5-20251001      # new
  mistral:
    validator_model: mistral-large-2512            # pin + pin-by-policy comment stay here
    adjuster_model: mistral-large-2512
    # doc_parser_model / guardrail_model: unset — see below
```

**Design decisions**

- **Selectors are `Literal["anthropic", "mistral"]`** on `LLMSettings`, and every default is `anthropic`. An unknown value such as `openai` fails at `Settings()` construction with a Pydantic validation error naming the field and the allowed values. Startup refuses it; nothing falls back.
- **Model resolution is one method, `LLMSettings.model_for(agent) -> str`.** It reads `<agent>_provider`, then that provider block's `<agent>_model`, through an explicit mapping rather than `getattr` string-building. All four agents switch to it (`settings.llm.model_for("validator")` and so on). No agent names a provider block any more. `provider_for(agent)` is its companion, and the wiring sites use it. Because the agent and the wiring both read the same `Settings`, the provider an agent holds and the model it requests agree by construction.
- **`llm.mistral.doc_parser_model` and `guardrail_model` are added as `str | None = None`.** A uniform selector needs a place for those ids. Guessing a default for combinations nobody has verified would be a silent assumption. Instead, an `LLMSettings` model validator **refuses at startup** any selector whose chosen block has no model for that agent (for example `doc_parser_provider: mistral` with `mistral.doc_parser_model` unset), naming both fields in the message. `model_for` re-checks at call time, because a variant's deep copy bypasses validation.
  - *Alternative considered:* leave those two fields out and refuse `mistral` for doc-parser and guardrail outright. That is simpler, but the selector would no longer be uniform, which defeats the prompt's purpose. Not chosen.
- **Only two combinations are verified:** the all-Anthropic default, and Validator plus Adjuster on Mistral (`v1_mistral`). Doc-Parser or Guardrail on Mistral is structurally possible, fails loud if half-configured, and is **untested**. No tests are added for it. This caveat goes into the plan, `CLAUDE.md` and `settings.yaml.template`.
- **The settings hierarchy still applies.** Setting `LLM__VALIDATOR_PROVIDER=mistral` and `LLM__ADJUSTER_PROVIDER=mistral` as Render env vars flips both agents back to Mistral **without a code deploy** (Render restarts the service on an env change). The model ids come from the pinned `llm.mistral.*` defaults, so no model env var is needed. That is two variables, not one, and the docs will say so.
- **The pin-by-policy comment stays on `MistralProviderSettings.validator_model` and `adjuster_model`**, since those fields do not move. One pointer inside it changes: it cites `docs/BACKLOG.md, "Mistral tier upgrade path"`, an item this phase removes, so it will point to the new *Re-enable Mistral as default* item. The comment's substance is not edited.
- **Vector index untouched.** Provider selection only changes which LLM reads the retrieved chunk text. `EmbeddingSettings`, `policy_chunks` and `index_policy` are out of scope, and verification does not re-run `index_policy`.
- **Template parity.** Every new field appears in `settings.yaml.template` with a comment. The header comment claiming the model ids follow "the locked architectural decisions (… Mistral Large for validator and adjuster)" is rewritten to describe prototype default versus variant.
- **Where the `Literal` lives.** `settings.py` cannot import from `backend/app` (the dependency runs the other way), so it declares its own `LLMProviderName` literal. Three copies of the same literal already exist (`llm/factory.py`, `variant_registry.py`, `logging/api_logger.py`). Consolidating them is listed as an optional suggestion, not done here.

---

## 3. Variant mechanism

**Resulting `variants.yaml`:**

```yaml
variants:
  default:
    description: "Baseline — each agent on the provider and model its settings select (all Anthropic by default)."
  v1_mistral:
    description: "Validator and Adjuster on Mistral Large — the pre-Phase-8.6 default wiring."
    validator: { provider: mistral }
    adjuster:  { provider: mistral }
  v2_strict_validator:
    description: "Validator uses the strict prompt template; same model and provider."
    validator:
      prompt_template: "validator_strict.md"
```

- **Name: `v1_mistral`.** The existing `v2_*` prefix means "a revision of the baseline". The Mistral wiring *is* the original baseline (Phases 2–8.5), so `v1` is the accurate prefix. The variant sets no `model`, so it uses the pinned `llm.mistral.*` ids. The pin keeps a single source of truth in `settings.py`, and moving it moves the variant too.
- **`v2_haiku_validator`: retire it (recommended).** Under the new default it would do nothing, and its description ("instead of Mistral") would be false. It would also put two identical configurations into the compare view. Keeping it as a no-op alias preserves nothing useful.
  - *Cost of retiring:* for a historical run recorded under that variant, `GET /api/agents/validator/prompt?variant=v2_haiku_validator` returns 404. The expand panel only calls that endpoint when the audit row has no `llm_call.prompt`, which means pre-8.3 runs. The Neon reset in verification removes all such runs from the deployed database. **Dermot to confirm: retire, or keep as an alias.**
- **Schema (additive):** `VariantSpec` gains `adjuster: ProviderOverride | None`, where `ProviderOverride` is `{model, provider}` with `extra="forbid"`. `AgentOverride` (the Validator slot) extends it with `prompt_template`. The Adjuster has no user-template hook, so a `prompt_template` under `adjuster:` **fails at registry load** instead of being silently ignored. No slots are added for doc-parser or guardrail (§2 caveat; adding them later is additive).
- **Resolution becomes settings-based.**
  - `resolve_variant_settings(settings, spec) -> Settings` is pure. It deep-copies and, for each override, sets `<agent>_provider` if given, then writes `model` into the *resolved* provider block's `<agent>_model` if given.
  - `resolve_validator_template(spec) -> str` handles the template.
  - Together these replace `ResolvedValidatorConfig` and `resolve_validator_config`, whose `provider_name` default was the hardcoded `"mistral"`.
  - The callers are `variant_factory.py`, `api/agents_test.py` and the tests. These are internal Python names, not HTTP or JSON contracts.
- **`v2_strict_validator` stays provider-independent.** It overrides only the user template, so on the new default it runs the strict template on Haiku. A unit test confirms this, and it is exercised live the first time *Re-process* is used after deploy. It is not a verification step (see optional suggestions).
- **What *Re-process with v2* does now:** it replays the claim with the Validator on the strict template, on the default Haiku wiring. It still produces a genuinely different second run, side by side in the audit vault and comparable in the compare view. No UI change.

---

## 4. Prompt compatibility on Haiku

- **No prompt change planned.** `system/validator.md:23` and `system/adjuster.md:32` already require "**only** a JSON object, no preamble, no Markdown fencing". Neither prompt mentions Mistral (the `grep` of `backend/app/prompts` returns nothing).
- **JSON handling.** Both agents pass `response_format="json"`. `AnthropicProvider.complete` accepts that argument for interface symmetry and then discards it (`anthropic_provider.py:84–89`, documented). JSON is enforced by the system prompt and by the parser, where `extract_json_block` tolerates fences or surrounding prose before `json.loads` and strict Pydantic validation. The Guardrail already runs exactly this path on Haiku (F4). Parse failures raise and are audited, with no fallback.
- **Token budget risk (noted; no change).** `adjuster_max_tokens = 768` must hold the JSON plus a reasoning field of up to 2,000 characters (about 500 tokens). If Haiku is more verbose, a truncated response fails JSON parsing and aborts the run visibly. `validator_max_tokens = 1024`. These settings are **not** tuned pre-emptively.
- **Halt rule.** If any scenario lands in the wrong state, including a parse abort, I stop, report the audit rows, and do not iterate on prompts or token settings. That becomes a separate decision.

---

## 5. Scenario outcomes under Haiku — the real risk

All three scenarios run on the **deployed** app. A wrong terminal state halts the phase. Checked fields per scenario:

| | Auto-approve ($85k water) | Threshold ($850k fire) | Guardrail ($1.4M storm) |
|---|---|---|---|
| Terminal status | `settled` | `awaiting_human` | `awaiting_human` |
| Fired rules (`escalation_decision.fired_rules`) | **none** | includes `settlement_over_ceiling` | includes `guardrail_failed` |
| Audit entries / chain | 7 / verified | 7 / verified | 7 / verified |
| Agent panels | 4 filled, no *Audit entry not found* | same | same |
| `coverage_check.llm_call` | `provider="anthropic"`, `requested_model = model = claude-haiku-4-5-20251001`, `prompt` present | same | same (the Validator runs live) |
| `settlement_estimate.llm_call` | `provider="anthropic"`, `requested_model = model =` Haiku id, `prompt` present; `demo_fixture=false` | same | `demo_fixture=true`, `provider="demo_fixture"`, **no** `prompt` / `requested_model` |
| `doc_extract` / `output_check.llm_call.provider` | `anthropic` | `anthropic` | `anthropic` |
| Model-dependent conditions | `validator.confidence ≥ 0.65`, `adjuster.confidence ≥ 0.75`, `guardrail.passed = true`; settlement is structurally ≤ $200k (range 50k–200k) | settlement is structurally ≥ $500k (range 500k–1.5M), so the ceiling rule fires whatever Haiku picks | the fixture forces the hallucinated endorsement |

**Where it can go wrong.** The only scenario whose outcome depends on the model is **auto-approve**. It needs both confidences above their floors *and* a clean Guardrail pass over reasoning written by Haiku. Phase 8 fix #5 taught the Guardrail prompt that market vocabulary is not a citation, but that was tuned against Mistral's phrasing, and `guardrail_rules.py` also runs deterministic checks on the reasoning text. A Haiku Adjuster that writes something like "per Section 4.2" could trip `hallucinated_citation`. The threshold scenario could additionally fail only through a parse abort. If either happens: halt and report (§4).

---

## 6. Documentation sweep — per-occurrence verdicts

`grep -rn -i mistral` across `README.md`, `CLAUDE.md`, `docs/`, `diagrams/`, `frontend/src`, `backend/app/prompts`:

| File : line | Content | Verdict |
|---|---|---|
| `CLAUDE.md:24` | Tech stack lists `mistralai` SDK | **Leave** (the dependency is retained) |
| `CLAUDE.md:132–137` | Current Status (Mistral blocker) | **Prototype → update** (8.6 status; *Demo status* cleared only after verification passes) |
| `CLAUDE.md:161` | Externalised prompts "Claude API and Mistral API" | **Leave** (both providers remain callable) |
| `CLAUDE.md:175` | Locked *Models* decision | **Prototype → rewrite**: prototype default (all Anthropic; Validator and Adjuster on Haiku, from 15 September 2026, reason: Mistral Large withdrawn from Free tier) vs production target (Mistral Large; Adjuster LoRA, unchanged); `v1_mistral` restores it. Plus a new locked-interface-extension bullet (§7) and the §2 verified-combinations caveat. |
| `README.md:15–16` | Headline sequence diagram `Validator [Mistral Large]`, `Adjuster [Mistral Large]` | **Prototype → update** labels to `[Claude Haiku]` with a line under the diagram naming the `v1_mistral` variant (the README describes the running prototype; the `diagrams/*.mmd` keep the target) |
| `README.md:41` | Tiered model strategy | **Design claim → leave**, add one clause: prototype default runs single-vendor; see design-decisions §3 |
| `README.md:47`, `:161` | "a replay variant has been exercised that swaps the Validator from Mistral to Claude Haiku" | **Prototype → update** to the truthful 8.6 statement (default on Haiku, `v1_mistral` routes Validator and Adjuster to Mistral, audit records the actual provider), citing the Phase 8.6 verification as evidence (F4) |
| `README.md:77`, `:97` | `MISTRAL_API_KEY` required for live runs | **Prototype → update**: required only for the `v1_mistral` variant |
| `README.md:162` | "Why Mistral *and* Claude?" | **Design rationale → leave**, add a dated note sentence |
| `README.md:188–189` | Prototype vs production table: "Anthropic + Mistral public APIs" | **Prototype column → update** ("Anthropic public API by default; Mistral public API via `v1_mistral`"); production column **leave** |
| `docs/design-decisions.md:30` | Gateway has both providers | **Leave** |
| `docs/design-decisions.md:36–40` | §2 *Evidence it works* cites `v2_haiku_validator` | **Prototype → update** to `v1_mistral` and the now all-agent truthful provider audit |
| `docs/design-decisions.md:46–58` | §3 tiered strategy | **Leave the argument**, append a dated note (single-vendor default after the Free-tier withdrawal; Mistral retained as a variant; this is itself substitutability in practice) |
| `docs/dora-third-party-register.md:9, 22–23, 25–31, 67–68` | Substitution exercised via `v2_haiku_validator`; Mistral on the PII path | **Prototype → update** the variant references and "exercised" cells; **Mistral stays registered**; add a note that the default deployment exercises one provider (concentration posture in the prototype, not in the target) |
| `docs/architecture-stack-reference.md:35–36, 94, 108` | *Prototype* column/paragraph says Mistral Large via the public API | **Prototype claim inside a production-target document.** Constraint: notes, not rewrites. **Add one dated note** after the table and at §94. The rest of the document (lines 98, 150–160, 208, 222) is production target → **leave**. |
| `docs/change-governance.md:60–61` | Illustrative production variant YAML | **Production illustration → leave** |
| `docs/walkthrough.md` | No hits | **Add** the one-to-two-sentence demo script line (auto-approve or threshold scene): *"All four agents run on Claude by default. The Validator and Adjuster were designed for Mistral Large, and that path is still wired in as a variant. When Mistral's free tier dropped the model, switching was a configuration change, not a rewrite, which is the substitutability the gateway exists for."* |
| `docs/BACKLOG.md` | Mistral tier decision; 8.4/8.5.2 pending verification; Phase 8.6 UI polish; `Agent card stuck` (Mistral 403 observation); model-access probe (`llm.mistral.*_model`) | Tier decision → **remove** (reasoning moves to build-log); pending verification → **discharged** by this phase's verification and moved to build-log; UI polish → **renumber 8.7**; card-stuck observation → **leave** (historical observation, still a valid bug); probe → **leave** (still accurate); **add** *Re-enable Mistral as default*; *Split the oversized builders* → **carry unchanged** |
| `diagrams/1-headline-agent-flow.mmd:6–7`, `2-rag-zoom.mmd:4, 29`, `4-production-architecture.mmd:26, 42` | Mistral in target diagrams | **Leave**, with a note in `diagrams/README.md` that the `.mmd` files show the target architecture and the prototype default runs Validator and Adjuster on Haiku (`v1_mistral` restores Mistral) |
| `diagrams/README.md:39–40, 100, 125, 231, 247` | Embedded copies of the same diagrams | **Leave**; the note above covers them |
| `docs/build-log.md`, `docs/prompts/*` | Historical | **Leave** |
| `docs/learning/*` | Dated learning snapshots (`STATE.md`, walkthroughs) | **Historical/archived → leave** |
| `frontend/src` | **No hits** (`agent-descriptions.ts` is provider-neutral; no Agents-page label names a provider) | **No change** |
| `backend/app/prompts` | **No hits** | **No change** |
| Code docstrings/comments: `validator.py:12, 477`, `adjuster.py:13, 89–91`, `doc_parser.py:17, 78`, `guardrail.py:14, 86`, `settings.yaml.template:50–53`, `variant_factory.py` module docstring, `variants.yaml` header | "Call Mistral Large…", "routes through Mistral per the architectural decisions" | **Code → handled in §1–3**; rewritten to "the provider its settings select" so no comment encodes the retired default (per the stale-contract-cleanup convention) |

---

## 7. Interface stability — explicit acknowledgement

- **Audit payload shapes: unchanged.** No key is added, removed or renamed.
- **Audit values change:**
  - `coverage_check` and `settlement_estimate` now carry `provider = "anthropic"` and `model` / `requested_model` = the Haiku id.
  - **Extension of the Phase 5 locked rule (F1):** `llm_call.provider` becomes `self._provider.vendor` for **all four agents**, not only the Validator. On the default wiring, `doc_extract` and `output_check` values are identical to today (`anthropic`). The Adjuster's value becomes truthful. The demo-fixture path still records `"demo_fixture"`.
  - This is recorded as a new bullet under CLAUDE.md → *Locked interface extensions*.
- **Settings (additive):** four selectors, two Anthropic model fields, two optional Mistral model fields. The `llm.mistral.validator_model` and `adjuster_model` defaults are unchanged. **Behaviour change for anyone who set `LLM__MISTRAL__VALIDATOR_MODEL`:** it now only takes effect when the selector is `mistral`. Render has no such variable (confirmed 14 September).
- **`variants.yaml` schema (additive):** new `adjuster` slot. **Registered names change:** `v1_mistral` added; `v2_haiku_validator` removed pending Dermot's decision (§3). `GET /api/runs` and `compare` accept any recorded variant string, so they are unaffected.
- **`pipeline_started.variant`:** stays `"default"` for the default run.
- **HTTP shapes:** unchanged. The test bench's Adjuster now honours `?variant=` (§1).
- **Deployment requirement relaxed:** the default path no longer requires `MISTRAL_API_KEY`. Keep it set on Render so `v1_mistral` stays reachable.

---

## 8. Tests

**Existing tests that stay green unchanged:**
- `test_llm_provider_mistral.py`
- `test_api_logger.py`
- the Mistral pin assertions in `test_settings_phase1.py:53–54`
- the gated live Mistral provider tests
- the orchestrator and agent tests that inject `MockProvider`. These are provider-agnostic, **except** the provider-label assertions listed next.

**Existing tests updated:**
- `test_adjuster.py:217` `== "mistral"` becomes `== mock_provider.vendor == "mock"`, matching the Validator's existing assertion. It currently passes only *because* the label is hardcoded.
- `test_doc_parser.py:172` and `test_guardrail.py:198` `== "anthropic"` become `== mock_provider.vendor`.
- `test_variants.py`: the real-file names become `[default, v1_mistral, v2_strict_validator]`. The default and strict resolution tests now assert `anthropic` plus the Haiku id. The Haiku resolution test becomes a `v1_mistral` resolution test.
- `test_variants.py::test_build_validator_applies_model_override_without_mutating_settings` switches to a **synthetic `tmp_path` registry**, because no shipped variant sets `model` any more. This keeps the model-override code path covered.
- `test_validator.py::test_haiku_variant_records_overridden_requested_model` is rewritten as a `v1_mistral` test: `requested_model == "mistral-large-2512"`, and the shared settings still hold the Haiku default.
- `test_pipeline_scenarios.py` gated live E2E is wired from the selectors (still skipped).

**New tests:**

| # | Test | Guards |
|---|---|---|
| 1 | Default settings: four selectors == `anthropic` | defaults |
| 2 | Default `llm.anthropic.validator_model` / `adjuster_model` == Haiku id | defaults |
| 3 | `llm.mistral.doc_parser_model` / `guardrail_model` default `None` | defaults |
| 4 | `model_for` resolves all four agents to Haiku on defaults | resolution |
| 5 | `model_for("validator")` with `validator_provider="mistral"` → `mistral-large-2512` | resolution |
| 6 | Unknown selector value `openai` → validation error; message names the field and allowed values | guard |
| 7 | `doc_parser_provider="mistral"` with no `mistral.doc_parser_model` → error at construction; message names both fields | guard |
| 8 | `model_for` on an unknown agent name → `ValueError` with the expected names | guard |
| 9 | `model_for` when a deep copy bypassed validation and the model is `None` → `ValueError` | guard |
| 10 | `LLM__VALIDATOR_PROVIDER=mistral` env var flips the resolved provider (hierarchy) | hierarchy |
| 11 | `PipelineOrchestrator.with_defaults`: Validator and Adjuster hold `AnthropicProvider`, model resolves to Haiku; Doc-Parser and Guardrail hold `AnthropicProvider` | default wiring |
| 12 | `with_defaults` succeeds with **no `MISTRAL_API_KEY`**, proving the default path builds no Mistral provider (this test separates correct wiring from an accidental Mistral default) | default wiring |
| 13 | `build_variant_orchestrator("v1_mistral")`: Validator and Adjuster hold `MistralProvider` with `mistral-large-2512`; Doc-Parser and Guardrail stay Anthropic; shared `Settings` unmutated | variant wiring |
| 14 | `build_variant_orchestrator("v2_strict_validator")`: Validator on Anthropic/Haiku with template `validator_strict` | variant wiring |
| 15 | Registry load rejects `prompt_template` under `adjuster:` (schema) | guard |
| 16 | Adjuster `v1_mistral` records `requested_model == "mistral-large-2512"` (companion to the rewritten Validator test) | 8.5.3 audit |

The wiring tests (11–14) use obviously fake placeholder keys and monkeypatch `default_embedder` to skip the SentenceTransformer cold-load. Constructing the SDK clients makes no network call. No test covers Doc-Parser or Guardrail on Mistral (§2 caveat).

**Expected count:** 347 + 16 new = **≈ 363 passed, 0 failed, 7 skipped (≈ 370 collected)**. The exact figure goes in the report. Also required: `ruff` clean, `mypy` clean, and the frontend suite unchanged (no frontend edits). **Halt on any failure before commit.**

---

## 9. Version and numbering

**Agree:** `0.8.5.3 → 0.8.6`, phase **8.6**. This changes a locked architectural decision and the default runtime wiring, which is a design change rather than an incident fix, so it does not belong in the 8.5.x series. UI polish is renumbered **8.7** (version base `0.8.6 → 0.9.0`) in `docs/BACKLOG.md`, and the *Phase-numbering convention* working note is updated to match.

---

## 10. Deployed verification

This discharges the Phase 8.4 / 8.5.2 seven-entry check.

0. **Env check (Dermot, Render dashboard).** No `LLM__*` variables (in particular no `LLM__VALIDATOR_PROVIDER` / `LLM__ADJUSTER_PROVIDER`). `MISTRAL_API_KEY` stays set.
1. `/health` → `version = 0.8.6`.
2. **Reset Neon.** Hostname gate first (`.neon.tech`), then `uv run python -m backend.data.seed_claims --allow-truncate`. Expect 9 claims at `received`, `audit_log` cleared, `policy_chunks` (12) untouched. **Do not run `index_policy`.**
3. **Run all three scripted scenarios** from the Claims page (the seeded Harborline, Northwood and Coral Bay claims). Record every §5 field per scenario. **A wrong terminal state halts the phase.**
4. **Mistral variant proof.**
   - Choose a **non-scenario seeded claim** (`Background Claimant NN`), so the three scenario claims keep their terminal states for the demo.
   - Run it once on `default`: replay requires a prior terminal run (`_require_prior_terminal_run`, otherwise 409).
   - Then `POST /api/pipeline/replay/{claim_id}?variant=v1_mistral` (F3).
   - Expect `aborted`, failing agent `validator`, `403 tier_not_allowed`, `coverage_check.llm_call.provider = "mistral"`, `requested_model = "mistral-large-2512"`.
   - This proves the retained path is wired and reachable, and that the default is not still on Mistral. It will leave that background claim at `extracted`, which is harmless.
5. Record everything in the build log (three-scenario table plus the abort proof) and the report, clear *Demo status* in `CLAUDE.md`, and make the follow-up commit.

---

## Files

**Modified — code**
- `backend/settings.py`
- `backend/settings.yaml.template`
- `backend/app/orchestrator/pipeline.py`
- `backend/app/orchestrator/variant_factory.py`
- `backend/app/orchestrator/variant_registry.py`
- `backend/app/orchestrator/variants.yaml`
- `backend/app/api/agents_test.py`
- `backend/app/agents/validator.py`, `adjuster.py`, `doc_parser.py`, `guardrail.py` (model via `model_for`; truthful provider label; comments)
- `pyproject.toml` (`0.8.6`)

**Modified — tests**
- `test_variants.py`, `test_validator.py`, `test_adjuster.py`, `test_doc_parser.py`, `test_guardrail.py`, `test_pipeline_scenarios.py`

**New — tests**
- `backend/tests/test_settings_providers.py` (tests 1–10)
- `backend/tests/test_agent_wiring.py` (tests 11–14)
- tests 15–16 go into `test_variants.py` and `test_adjuster.py`

**Modified — docs**
- `CLAUDE.md`, `README.md`
- `docs/design-decisions.md`, `docs/dora-third-party-register.md`, `docs/walkthrough.md`
- `docs/architecture-stack-reference.md` (dated notes only), `diagrams/README.md` (note)
- `docs/BACKLOG.md`, `docs/build-log.md`, `docs/prompts/README.md` (index)

**New — docs**
- this plan
- `17-…-report.md`

**Not touched:** `MistralProvider` and its tests, the 2512 pin and its comment's substance, prompts, the embedding and index, `diagrams/*.mmd` content, frontend, Mistral account settings.

**Dependencies:** none.

---

## Risks

1. **Auto-approve under Haiku** (§5): the one model-dependent outcome. Mitigation: halt and report; no retuning.
2. **Adjuster token budget** (§4): possible truncation leading to a parse abort. It fails loud; halt.
3. **Retiring `v2_haiku_validator`** breaks the prompt-source endpoint for pre-8.3 runs recorded under it. None remain after the Neon reset; local dev databases may have some.
4. **Local `backend/settings.yaml` overlays** (gitignored) that set `llm.mistral.*` keep working but no longer steer the default. Mentioned in the report.
5. **Single-vendor default.** The deployed default now has one provider. This is recorded honestly in the DORA register and design-decisions §3 rather than hidden.

---

## Decisions for Dermot

1. **`v2_haiku_validator`:** retire (recommended) or keep as a no-op alias?
2. **Variant name `v1_mistral`:** acceptable?
3. **Truthful provider label for all four agents** (F1, §7): confirm as a locked-interface extension.
4. **Version `0.8.6` / UI polish → 8.7:** confirm.
5. **`docs/architecture-stack-reference.md` prototype rows** (§6): a dated note (recommended) rather than editing the table.

---

## Optional suggestions (not in scope; not built)

- **Variant selector for *Re-process*** instead of the hardcoded `v2_strict_validator`, so `v1_mistral` is demoable from the UI once Mistral is paid. Fits Phase 8.7 (the backlog already questions that control's UX).
- **Consolidate the three duplicated `Literal["anthropic", "mistral"]` definitions** into one, re-exported from the gateway.
- **Stale version in `docs/walkthrough.md`** ("`/health` reports `version=0.7.0`"): correct it in the same edit as the demo-script sentence, if you want it; it is not model-related.
- **Also exercise `v2_strict_validator` live** during verification (one extra replay on the auto-approve claim), to evidence that the UI's *Re-process* works on the new default. That replay would also change the claim's latest run, so do it after the scenario table is recorded.
