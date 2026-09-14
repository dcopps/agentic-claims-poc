# Phase 8.5.3 — Report: record `requested_model` in agent audit payloads; reset the deployed DB

Report for `docs/prompts/16-phase-8.5.3-requested-model-audit-and-db-reset.md`.
Plan: `docs/prompts/16-phase-8.5.3-requested-model-audit-and-db-reset-plan.md` (approved as written, 2026-09-14).
Date: 2026-09-14. Version: `0.8.5.2 → 0.8.5.3`.

## Status

- **Part A (code): complete.** Committed and pushed.
- **Part B (deployed DB reset): pending** — runs after the Render redeploy, immediately before the verification run.
- **Deployed verification: pending** — outcome to be appended below in a follow-up commit.

## Design decision — the prompt's preference was overridden deliberately

The prompt stated a preference for threading the requested model to
`_build_audit_payload` as **an explicit parameter alongside `prompt`**. That
preference was **not** followed. The plan proposed, and Dermot approved, widening
the Phase 8.3 capture object instead:

- `CapturedPrompt(system, user)` → `CapturedRequest(system, user, model)`
- `attach_prompt(llm_call, prompt)` → `attach_request(llm_call, request)`, which
  writes `prompt` **and** `requested_model` when a request exists, and neither
  when it is `None`.
- Each `_invoke_llm` reads the settings model once into the request and calls
  `provider.complete(model=request.model)`.

Why, for the next reader:

1. **Zero lines added to the oversized builders — decisive.** Three of the four
   `_build_audit_payload` functions were already over the 50-line hard limit, and
   the prompt's own rule was "if adding a key pushes one over, extract rather than
   annotate". Under this design the change inside every builder is a one-token
   rename; a parallel parameter would have added a signature line and a key line
   to each, forcing either an extraction refactor into this phase or a limit
   breach.
2. **Single read by construction — a genuine improvement.** The provider call and
   the audit read the *same* field, so the recorded value is the sent value, not a
   second settings read that is merely expected to agree with the first.
3. **The omit-when-no-call rule is inherited, not re-implemented.** A separate
   `requested_model: str | None` next to `prompt: CapturedPrompt | None` would be
   two optionals that must always be `None` together, an invariant the types would
   not enforce. One object makes "no request" a single `None`.
4. **The builders stay pure** — the value still arrives as a parameter.

The rename is internal: `CapturedPrompt` / `attach_prompt` were referenced only in
the five `backend/app/agents/` files. The **audit key** `prompt` is unchanged.

## Files modified

| File | Change |
|---|---|
| `backend/app/agents/_shared.py` | `CapturedRequest` (adds `model`), `attach_request` (adds `requested_model`); docstrings rewritten. |
| `backend/app/agents/doc_parser.py` | Model captured into the request from `llm.anthropic.doc_parser_model`; call uses `request.model`; `attach_request`. |
| `backend/app/agents/validator.py` | Same, from `llm.mistral.validator_model`. |
| `backend/app/agents/adjuster.py` | Same, from `llm.mistral.adjuster_model`; fixture branch sets `request = None` and `_llm_call_block` returns before `attach_request`, so neither key is emitted. |
| `backend/app/agents/guardrail.py` | Same, from `llm.anthropic.guardrail_model`. |
| `backend/tests/test_doc_parser.py`, `test_adjuster.py`, `test_guardrail.py` | +2 tests each (success, provider error). |
| `backend/tests/test_validator.py` | +3 tests (success, provider error, Haiku variant) and a local `_audit_llm_call` helper used by those three. |
| `backend/tests/test_demo_fixture.py` | `assert "requested_model" not in llm_call`. |
| `pyproject.toml`, `uv.lock` | `0.8.5.3`. |
| `CLAUDE.md` | Locked-extension bullet; Current Status (adds a *Demo status: blocked* line). |
| `docs/build-log.md` | Phase 8.5.2 entry amended with *Deployed verification outcome*; Phase 8.5.3 entry. |
| `docs/BACKLOG.md` | See *Backlog* below. |
| `docs/prompts/16-…-plan.md`, `16-…-report.md` | Plan, this report. |

No files created in `backend/`. No new dependencies.

## Tests

| | Before | After |
|---|---|---|
| Collected | 345 | **354** |
| Passed | 338 | **347** |
| Failed | 0 | 0 |
| Skipped | 7 | 7 |

Matches the expected 347 / 0 / 7 exactly. `ruff check .` clean; `mypy` clean (108
source files). Frontend unchanged (36).

How the tests discriminate:

- **Success tests** assert `requested_model` equals the settings field, equals
  `mock_provider.calls[0].model` (what was actually sent), and **differs** from
  `llm_call["model"]`. `MockProvider` answers as `mock-model-latest`, so a bug that
  copied the responding model into `requested_model` fails.
- **Error tests** raise `LLMProviderError` from the provider and assert the audit
  row is still written, `requested_model` is present, and `model` is absent — the
  exact production 403 shape.
- **Variant test** builds the Validator through the real
  `variant_factory._build_validator` for `v2_haiku_validator` and asserts
  `claude-haiku-4-5-20251001` is recorded while the shared Settings keeps the
  Mistral default.
- **Mutation proof:** with the `requested_model` line temporarily removed from
  `attach_request`, all 9 new tests failed; restored, the full suite is green.

## Interface stability

Additive `llm_call.requested_model` on `doc_extract`, `coverage_check`,
`settlement_estimate`, `output_check`, present whenever a call was attempted
(success, parse failure, provider exception) and absent on the Adjuster
demo-fixture path. Existing `llm_call` keys, payload shape, DB columns, HTTP
responses and SSE events unchanged; existing audit rows and the hash chain
unaffected. Recorded in `CLAUDE.md` → *Locked interface extensions since Phase 4*.

## Differences from the spec

- **Threading design**: see above. Approved.
- **Function size**: the builders gained no lines, but each `_invoke_llm` gained
  four, because the `CapturedRequest(...)` constructor is now multi-line to carry
  `model` inside the 100-column limit. Those methods were already long; no new
  limit breach was introduced in the builders, which were the concern the prompt
  named.
- **Test helper**: `test_validator.py` gained a small `_audit_llm_call` helper for
  its three new tests; the other test files keep their existing inline
  `SELECT payload` pattern.

## Guard clauses added

None. The change adds no input-accepting branch.

## Frontend

No change, by decision. The Audit page's JSON viewer renders the new key
automatically; `AgentCard.extractPrompt` reads only `llm_call.prompt`, whose shape
is unchanged; nothing in `frontend/src` reads `llm_call.model`.

## Backlog

- **Removed** *Record `requested_model` on the error-path `llm_call`* (built here).
- **Added** *Split the oversized audit-payload builders*, noting that the `error`
  block is byte-identical across all four agents and belongs in `_shared.error_block`.
- **Added** *Record `requested_model` in `ProbeMetadata`*, flagged as an additive
  HTTP response-shape change for `/agents/test`.
- **Added** a *Pending verifications* entry for this phase, with the Part B reset
  marked pending.
- **Corrected** two cross-references that still pointed at the old section name
  *Mistral tier upgrade path* (renamed to *Mistral tier decision* in the
  uncommitted backlog edits that ride along in this commit).
- *Mistral tier decision* left as is, still open.

## Part B and deployed verification

*Pending — to be appended after the Render redeploy.*

## Suggestions for follow-on work

- The two backlog items above.
- `Validator._invoke_llm` carries a comment claiming the per-call correlation id
  "keeps a single ID across audit + log", while the code mints a fresh UUID — the
  comment contradicts `_shared.new_correlation_id`'s docstring. A stale-contract
  comment worth removing in the next pass over that file (not touched here, as it
  is unrelated to this phase's change).
