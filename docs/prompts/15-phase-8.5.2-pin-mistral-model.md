# Phase 8.5.2 — Pin Mistral model to `mistral-large-2512`

## Context

The Validator agent aborted the pipeline in production on 14 September 2026 (run `26a9bf4e-44ce-49c9-bc99-aeaed33c9f8f`) with:

> `LLMProviderError — MistralProvider: SDKError: API error occurred: Status 403. Body: {"object":"error","message":"This model is not available in your subscription tier","type":"tier_not_allowed","param":null,"code":"1910","raw_status_code":"403"}`

Diagnosis confirmed against Mistral's admin console (`admin.mistral.ai/subscription` and `admin.mistral.ai/limits`):

- The Mistral account is on the **Free** tier. No payment method attached. €0.00 credits. Auto-recharge disabled.
- The current settings send `mistral-large-latest` — a moving alias that Mistral resolves server-side to whichever version they currently designate as *latest*.
- Mistral has re-tiered `mistral-large-latest` since May 2026 (when the key was last confirmed working against it, per `docs/prompts/03-phase-2-llm-gateway-and-validator.md:35`). The alias now points at a newer Mistral Large release that requires a paid tier.
- The specific pinned version `mistral-large-2512` (December 2025 release) is still on the account's accessible models list per the Limits page (`admin.mistral.ai/limits`), at 250,000 tokens/minute and 1.00 requests/second.

The 403's `tier_not_allowed` (rather than 401 `unauthorized`) is definitional evidence that the API key itself is valid and the failure is at the model-access gate, not at authentication. Diagnostic details are in the session transcript that led to this prompt.

**Fix chosen:** pin the model identifier from the moving alias `mistral-large-latest` to the specific version `mistral-large-2512`, in both the Validator and Adjuster settings. This is the cheapest of three options considered (the other two being *add a payment method to Mistral* and *route Validator + Adjuster through Claude via the LLM Gateway variant mechanism*).

## Plan-first

Before writing any code, produce a written plan in `docs/prompts/15-phase-8.5.2-pin-mistral-model-plan.md` covering:

1. **Files-to-modify sweep.** Grep the repo for every occurrence of `mistral-large-latest`. Categorise each occurrence as one of:

   - **Must update** — an assertion about production behaviour, a settings default, or a value that drives runtime lookups.
   - **Can stay** — sample data / mock input in a test fixture that's independent of the production default, or documentation that talks about the historical state.

   Document the list with per-occurrence verdicts. Known starting points from the pre-planning grep:

   - `backend/settings.py:211-212` — the `validator_model` and `adjuster_model` defaults (must update).
   - `backend/settings.yaml.template:62-63` — the template values (must update).
   - `backend/tests/test_settings_phase1.py:53-54` — asserts the default equals `mistral-large-latest` (must update).
   - `backend/tests/test_settings_phase2.py:115,118` — the pricing map key (must update if the app looks up pricing by model ID at runtime; otherwise document why the pricing entry stays as `mistral-large-latest`).
   - `backend/tests/test_api_logger.py:34` — sample data (likely can stay; verify).
   - `backend/tests/test_llm_provider_mistral.py` multiple sites (27, 82, 120, 148, 174) — sample data for provider tests (likely can stay; verify).
   - `backend/tests/test_variants.py:159,170` — references the default in variant-override tests; verify whether the specific string matters or whether the test is model-string-agnostic.
   - Any occurrence under `docs/` — documentation, not runtime; leave with an optional one-line note about the pin if useful, otherwise leave untouched.

   The plan must state, for every occurrence found, the verdict and the reasoning.

2. **Interface stability acknowledgement.** The model identifier appears in audit-log payloads at `llm_call.model`. Changing the default from `mistral-large-latest` to `mistral-large-2512` means newly-written audit rows will carry the new value in that field. Existing rows are unchanged. Confirm the JSON shape and field names are unchanged — this is a value change within an existing field, not a contract change — but explicitly flag it as observably different in the audit log for anyone comparing pre-pin and post-pin runs. No consumer of the audit log should be pattern-matching on the string `mistral-large-latest` (that would be a bug in the consumer), so this is a value change with no downstream break; document that reasoning in the plan.

3. **Locked architectural decision preservation.** `CLAUDE.md`'s *"Mistral Large (Validator, Adjuster)"* locked decision remains truthful — `mistral-large-2512` is a Mistral Large model. No edit to the *Architectural Decisions (Locked)* section is required. Do add a Current-Status entry explaining the pin and the reason (Free tier no longer includes the alias target). The pin is an operational decision, not an architectural one.

4. **Version treatment.** Point release: `0.8.5.1 → 0.8.5.2`. Bump `pyproject.toml`. `/health` resolves the version through `importlib.metadata.version("agentic-claims-poc")` (`backend/app/api/health.py:44`), so the `pyproject.toml` bump is the only source-of-truth change needed. `test_health.py` asserts only that the version string is non-empty, so it stays green.

5. **Test strategy.** After the pin lands, `uv run pytest` against the local test DB should show **338 passed, 0 failed, 7 skipped** — identical count to the Phase 8.5.1 baseline. The default-assertion tests updated in step 1 continue to assert the (now-changed) default. No new tests required for this change — the pin is a configuration change, and the existing suite already covers the settings-load and pricing-map lookup paths.

6. **Post-deploy verification.** Once Render redeploys, the verification steps are:

   1. `curl https://agentic-claims-poc-backend.onrender.com/health` — confirm `0.8.5.2`.
   2. Submit or process a threshold-escalation claim (the seeded Northwood $850k fire, or an equivalent scenario) on the deployed frontend.
   3. Confirm the Validator agent completes (no 403), the pipeline reaches its natural terminal state (`awaiting_human` for the threshold scenario), and all four agent expand panels show filled prompts and JSON responses with no `Audit entry not found` banners.
   4. Open the audit log for the run and confirm the `coverage_check` entry's `llm_call.model` reads `mistral-large-2512` (previously `mistral-large-latest`). This is the observable proof that the pin took effect on the runtime path, not just in the config.

Wait for explicit confirmation of the plan before writing any code.

## Deliverables (after plan is approved)

1. `backend/settings.py` — pinned default (`mistral-large-latest` → `mistral-large-2512` for both `validator_model` and `adjuster_model`).
2. `backend/settings.yaml.template` — pinned template values.
3. Any test files identified in step 1 as *must update* — the default-assertion tests, and the pricing-map key if that drives runtime lookups.
4. `pyproject.toml` — version bump to `0.8.5.2`.
5. `docs/build-log.md` — Phase 8.5.2 entry documenting:
   - Root cause: Free tier re-tiering of the `mistral-large-latest` alias since May 2026.
   - Fix: pin to `mistral-large-2512`, which remains Free-tier accessible per the Limits page.
   - Caller-sweep result: full enumeration with per-occurrence verdicts.
   - Interface-stability note: audit-log `llm_call.model` value change, no contract change.
   - Why this is an operational decision, not an architectural one — Mistral Large remains the model family per the locked decision; only the version alias is being pinned to a specific known-working release.
   - Deployed verification outcome (once the redeploy completes).
6. `docs/prompts/15-phase-8.5.2-pin-mistral-model-plan.md` — the plan produced in step 1 above.
7. `docs/prompts/15-phase-8.5.2-pin-mistral-model-report.md` — the standard post-execution report.
8. `CLAUDE.md` Current Status — bumped date, phase `8.5.2`, version `0.8.5.2`, a *what works* line explaining the pin and its rationale (Free tier alias re-tiered), and a *what's next* line covering: deploy and verify, still-pending Phase 8.4 deployed audit-persistence verification, and a pointer to the new backlog item for the eventual tier-upgrade decision.
9. `docs/BACKLOG.md` — add an item under *Future work* named *"Mistral tier upgrade path"*. Body: *"The pin to `mistral-large-2512` works today because that specific version is still on the Free tier's accessible list. Mistral will eventually deprecate 2512 (they've deprecated Large versions on ~12-month cycles historically). When that happens, the options are: (a) pin forward to whichever Mistral Large version is then on the Free tier — same fix pattern, low cost, but chasing a moving target; (b) add a payment method on Mistral and switch back to `mistral-large-latest` — small monthly cost, unlimited horizon; or (c) route Validator + Adjuster through Claude via the LLM Gateway variant mechanism — architecturally strongest (demonstrates DORA Article 28 substitutability in action), no Mistral dependency at all. Decide when the pin ages out, not before."*

## Constraints

- **Do not add a payment method to the Mistral account.** That's a Dermot-side decision, not one for this phase to make.
- **Do not modify the LLM Gateway variant mechanism.** The route-through-Claude alternative is a *future option*, not part of this fix.
- **Do not touch any production code path beyond the model identifier defaults.** No behaviour changes, no logic changes, no interface changes beyond the audit-log value.
- **Do not commit until the local test suite passes.** If any of the 338 tests fail after the pin, halt and surface the failure — that would indicate a test that was implicitly coupled to the `latest` alias in a way the plan's caller sweep missed.

## Standing conventions

Honour `CLAUDE.md`'s standing instructions throughout — defensive ordering (sanitise → validate → abort → execute), no silent fallbacks, function size limits (30-line prompt to reconsider, 50-line hard limit), settings hierarchy, externalised prompts, system/user separation, frequent commits with descriptive messages, push after every logical unit of work, security discipline (no secrets in code), dependency discipline (no new dependencies without flagging in the plan), interface stability acknowledgement.

## Save this prompt

This prompt is being pre-saved to `docs/prompts/15-phase-8.5.2-pin-mistral-model.md` by the drafter. The plan goes to `docs/prompts/15-phase-8.5.2-pin-mistral-model-plan.md`. The execution report appends to `docs/prompts/15-phase-8.5.2-pin-mistral-model-report.md` and a Phase 8.5.2 heading is appended to `docs/build-log.md`.
