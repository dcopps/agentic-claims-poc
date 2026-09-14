# Phase 8.5.3 — Plan: record `requested_model` in agent audit payloads; reset the deployed DB

Plan produced in response to `docs/prompts/16-phase-8.5.3-requested-model-audit-and-db-reset.md`.
Date: 2026-09-14. Version: `0.8.5.2 → 0.8.5.3`.

## 1. Where the requested model is threaded from

### Decision: widen the Phase 8.3 capture object, not a new parameter

Every agent's `_invoke_llm` already builds a `CapturedPrompt(system, user)`
*before* the provider call and returns it on every path, including the
provider-exception path; the Adjuster fixture path carries `None`; and
`attach_prompt` turns `None` into "key absent". That is exactly the lifecycle
`requested_model` needs. So rather than thread a second, parallel value, the plan
widens the existing object:

- `_shared.py`: `CapturedPrompt` → **`CapturedRequest(system, user, model)`** —
  "what the agent sent to the provider for one call". Docstring updated to say so.
- `attach_prompt` → **`attach_request(llm_call, request)`**: when `request` is not
  `None`, sets `llm_call["prompt"] = {system, user}` (unchanged shape) **and**
  `llm_call["requested_model"] = request.model`. When `None`, touches nothing.
- In each `_invoke_llm`, the model is read from settings **once**, into the
  captured request, and the provider call uses `model=request.model`.

Why this over the prompt's preferred "explicit `requested_model` parameter
alongside `prompt`":

1. **The recorded value is the sent value by construction.** The provider call
   and the audit both read `request.model`; there is no second read of settings
   that could, even in principle, diverge from what `complete()` received.
2. **The omit-when-no-call rule is inherited, not re-implemented.** A separate
   `requested_model: str | None` parameter would sit next to `prompt:
   CapturedPrompt | None` as two optionals that must always be `None` together —
   an invariant the types would not enforce. One object makes "no request" a
   single `None`.
3. **No tuple growth, no builder growth.** `_invoke_llm` stays a 5-tuple. The
   four `_build_audit_payload` functions (and the Adjuster's `_llm_call_block`)
   gain **zero lines** — `attach_prompt(...)` becomes `attach_request(...)`.
   This matters because several of those functions are already over the
   function-size limit (see *Pre-existing size overages* below); the prompt's
   rule is "if adding a key pushes one over, extract" — this design adds no key
   inside them.
4. **The builders stay pure and testable** — the value still arrives as a
   parameter (inside the request object); nothing reads `self._settings` inside a
   builder.

The rename is internal: `CapturedPrompt` / `attach_prompt` are used only in the
five `backend/app/agents/` files (verified by grep across `backend/` and
`frontend/src`). No test, API module or frontend file imports them. The *audit
key* stays `prompt`; only the Python type name changes, because a type holding a
model id is no longer just a prompt.

### Variant overrides

`variant_factory._build_validator` deep-copies `Settings` and sets
`cfg.llm.mistral.validator_model`. The Validator reads that field at call time
into `CapturedRequest.model`, so a `v2_haiku_validator` run records
`requested_model = "claude-haiku-4-5-20251001"`. No change to the variant
mechanism.

## 2. The four agents, one by one

| Agent | Settings source | Read in `_invoke_llm` | Payload builder call (success + error) |
|---|---|---|---|
| `doc_parser.py` | `llm.anthropic.doc_parser_model` | line 254 → moved into `CapturedRequest` at line 247 | `_build_audit_payload` `llm_call` at 405 — one `attach_request` covers both branches of the success/error conditional |
| `validator.py` | `llm.mistral.validator_model` | line 320 → into `CapturedRequest` at 310 | `_build_audit_payload` `llm_call` at 501 — same single call covers both branches |
| `adjuster.py` | `llm.mistral.adjuster_model` | line 313 → into `CapturedRequest` at 306 | `_llm_call_block` at 476 (success) and 486 (error) |
| `guardrail.py` | `llm.anthropic.guardrail_model` | line 273 → into `CapturedRequest` at 266 | `_build_audit_payload` `llm_call` at 497 — single call covers both branches |

**Parse-failure path** (response received but `_parse_*` raised `ValueError`)
also carries the request — it already carries `prompt` today — so
`requested_model` appears there too. That satisfies "present whenever a call was
attempted".

**Adjuster demo-fixture branch** (`adjuster.py:168-169`): sets `prompt = None`
(renamed `request = None`), and `_llm_call_block`'s `demo_fixture` branch returns
before any `attach_request` call. So the fixture block carries neither `prompt`
nor `requested_model`. Confirmed by the extended `test_demo_fixture.py`
assertion.

**Probe paths** (`parse`, `assess`, `estimate`, `check` — agent test bench) discard
the request as `_request`, same as `_prompt` today. No audit, no change.

### Pre-existing size overages (observed, not fixed here)

`Validator._build_audit_payload` (~67 lines), `Adjuster._build_audit_payload`
(~72) and `Guardrail._build_audit_payload` (~74) are already over the 50-line
hard limit, and `Adjuster.evaluate` is ~63 including its docstring. This phase
adds no lines to any of them. Refactoring them is out of scope; logged as an
optional suggestion below.

## 3. Interface stability acknowledgement

- **What changes:** every newly written `doc_extract`, `coverage_check`,
  `settlement_estimate` and `output_check` audit row gains
  `llm_call.requested_model: str` whenever a provider call was attempted —
  success, parse-failure and provider-exception paths alike.
- **Absent** when no call was attempted: the Adjuster demo-fixture path. A missing
  key means "no request was made".
- **Unchanged:** all existing `llm_call` keys (`provider`, `model`,
  `prompt_tokens`, `completion_tokens`, `latency_ms`, `prompt`, and the fixture's
  `note`) — names, types, nesting, values. Top-level payload shape, DB columns,
  CHECK constraints, HTTP response shapes, SSE events: unchanged. Existing audit
  rows are untouched and the hash chain is unaffected (only new rows carry the
  key).
- **`model` semantics unchanged:** it remains the *responding* model from
  `response.model` (Phase 5). On success the two will normally match; a mismatch
  is diagnostic and deliberately not suppressed.
- **CLAUDE.md** → *Locked interface extensions since Phase 4* gains a bullet
  phrased like the Phase 8.3 one:
  > **All four agents' audit payloads** gain `llm_call.requested_model: str` —
  > Phase 8.5.3. The model identifier the agent passed to `provider.complete(model=…)`
  > (the resolved settings value at call time, including any variant override),
  > recorded on success, parse-failure and provider-exception paths alike, so a
  > failed call still records what was asked for. `model` remains the responding
  > model. Additive; nested under `llm_call`, all existing keys unchanged. Absent
  > when no call was attempted: the Adjuster demo-fixture path emits no
  > `requested_model`, same rule as `prompt`.

## 4. Test design

Baseline: **338 passed, 0 failed, 7 skipped** (345 collected).

`MockProvider.response_model` is `"mock-model-latest"`, while the configured
settings models are real ids — so on the success path `requested_model` and
`model` naturally *differ* in tests. Each success test asserts all three of:
`requested_model == <settings field>`, `requested_model == mock_provider.calls[0].model`
(what was actually sent), and `requested_model != llm_call["model"]` (proves the
value is not copied from the response).

New tests (**9**):

| File | Test | Path |
|---|---|---|
| `test_doc_parser.py` | `test_evaluate_records_requested_model_on_success` | success |
| `test_doc_parser.py` | `test_provider_error_audit_records_requested_model` | `LLMProviderError`; asserts row written, `requested_model` present, `"model" not in llm_call` |
| `test_validator.py` | `test_evaluate_records_requested_model_on_success` | success |
| `test_validator.py` | `test_provider_error_audit_records_requested_model` | error |
| `test_validator.py` | `test_haiku_variant_records_overridden_requested_model` | Validator built via `variant_factory._build_validator` for `v2_haiku_validator` with the test connection factory; asserts `requested_model == "claude-haiku-4-5-20251001"` |
| `test_adjuster.py` | `test_evaluate_records_requested_model_on_success` | success (live path) |
| `test_adjuster.py` | `test_provider_error_audit_records_requested_model` | error |
| `test_guardrail.py` | `test_evaluate_records_requested_model_on_success` | success |
| `test_guardrail.py` | `test_provider_error_audit_records_requested_model` | error |

Placement of the variant test: `test_validator.py`, not `test_variants.py`. It
needs a claim row, seeded chunks and a DB connection — the `_insert_claim`,
`_seed_chunks` and `_conn_factory` helpers live in `test_validator.py`, while
`test_variants.py` is deliberately DB-free (its module docstring says so).

Extended (no new test): `test_demo_fixture.py::test_guardrail_escalation_reproduces_deterministically`
gains `assert "requested_model" not in row[0]["llm_call"]` beside the existing
`prompt` assertion.

**Expected: 347 passed, 0 failed, 7 skipped (354 collected).** The 7 skips are
the real-key-gated tests and are unaffected. Plus `ruff` and `mypy` clean. Any
failure halts before commit.

No new guard clauses are introduced (the change adds no input-accepting branch),
so no guard tests are owed.

## 5. Frontend

**No change — a decision, not an omission.** The Audit page's JSON viewer renders
the raw payload, so `requested_model` appears automatically. `AgentCard`'s
`extractPrompt` reads only `llm_call.prompt`, whose shape is unchanged, and
nothing in `frontend/src` reads `llm_call.model`. `AgentCard` does not surface
the new key.

## 6. Version treatment

Point release `0.8.5.2 → 0.8.5.3` in `pyproject.toml` (sole version source;
`/health` resolves via `importlib.metadata`). `uv.lock` updated if `uv` rewrites
the project entry.

## 7. Part B sequencing

The DB reset is **not** part of the code commit. Order:

1. Code + tests + docs → suite green → commit → push (triggers Render redeploy).
2. Wait for `/health` → `0.8.5.3`.
3. **First action of Part B — hostname check.** Resolve `DATABASE_URL` exactly as
   `seed_claims` does (via `Settings`) and print **only** `urlparse(...).hostname`.
   Must end in `.neon.tech`; otherwise stop and ask. Note: the Phase 8.5 split means
   the local `.env` `DATABASE_URL` may point at local `agentic_claims_dev` rather
   than Neon — if so, I stop and ask how you want the Neon URL supplied (e.g. a
   one-shot `DATABASE_URL=… uv run …` you run via `! …`), rather than editing `.env`.
4. Explicitly acknowledge: `TRUNCATE TABLE claims RESTART IDENTITY CASCADE` clears
   `claims` and, via FK cascade, `audit_log` — including runs `26a9bf4e-…` and
   `11f97ae8-…` referenced in the Phase 8.5.2 build-log entry. Conscious choice;
   the build log keeps the finding. `policy_chunks` untouched; `index_policy`
   **not** re-run.
5. Run `uv run python -m backend.data.seed_claims --allow-truncate`.
6. Verify `SELECT COUNT(*) FROM claims` = 9, and the three scenario tags present
   with status `received`.
7. Immediately proceed to §8 step 3.

## 8. Deployed verification

1. `/health` → `0.8.5.3`.
2. Part B reset (above); 9 claims confirmed.
3. Process the seeded `threshold_escalation` claim.
4. Run aborts at the Validator (`403 tier_not_allowed`) — expected; the Mistral
   tier decision is not made in this phase.
5. Audit log for that correlation id:
   - `coverage_check` → `llm_call.requested_model == "mistral-large-2512"`
     (conclusive evidence 8.5.2 could not produce); no `model` key.
   - `doc_extract` → `llm_call.requested_model` and `llm_call.model` both present
     and both `claude-haiku-4-5-20251001`.
6. Append the outcome to the Phase 8.5.3 build-log entry and the report; amend the
   Phase 8.5.2 entry's *Deployed verification outcome* with the definitive
   statement. Follow-up commit + push.

## Risks

1. **`.env` target for Part B** — see §7 step 3. The hostname check is the gate.
2. **Validator abort means the Adjuster and Guardrail do not run in the deployed
   verification**, so their `requested_model` is proven by tests only, not in
   production. Acceptable for this phase; the full seven-entry run returns once
   the tier decision lands.
3. **`doc_extract` match assumption.** Anthropic returns the dated id it was
   asked for, so `model == requested_model` is expected; if Anthropic ever returns
   a different string the verification would show a mismatch — which is exactly
   the diagnostic the key exists for, not a failure of this phase.

## Dependencies

None added.

## Deliverables (execution order)

1. `backend/app/agents/_shared.py` — `CapturedRequest`, `attach_request`.
2. `doc_parser.py`, `validator.py`, `adjuster.py`, `guardrail.py` — capture model
   into the request, call with `request.model`, `attach_request` in payloads.
3. Tests per §4; run pytest / ruff / mypy; halt on failure.
4. `pyproject.toml` → `0.8.5.3`.
5. `CLAUDE.md` — locked-extension bullet; Current Status.
6. `docs/build-log.md` — Phase 8.5.3 entry (verification pending); amend Phase
   8.5.2 entry with *Deployed verification outcome* paragraph linking to
   `docs/BACKLOG.md` → *Mistral tier decision*.
7. `docs/BACKLOG.md` — remove *Record `requested_model` on the error-path
   `llm_call`* from *Future work*; keep *Mistral tier decision*. (Your current
   uncommitted BACKLOG edits are preserved and go into this commit.)
8. `docs/prompts/16-…-plan.md` (this file) and `16-…-report.md`.
9. Commit + push. Then Part B + verification with you; follow-up commit.

## Optional suggestions (not in scope — not to be done in this phase)

- **Split the oversized audit-payload builders.** Extract `_input_block`,
  `_output_block`, `_error_block` helpers so each `_build_audit_payload` is under
  50 lines; the `error` block is identical across all four agents and could be a
  `_shared.error_block(error)`. Pure refactor, no payload change — a good small
  point release or part of any backend phase.
- **Record `requested_model` in `ProbeMetadata`.** The agent test bench shows the
  responding model only; on a probe failure the bench has the same blind spot the
  audit had. Would be an HTTP response-shape change (additive) for
  `/agents/test`, so it needs its own interface acknowledgement.
