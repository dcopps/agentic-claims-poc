# Report 03 — Phase 2: LLM Gateway and Validator Agent

## Summary

**Recap.** Phase 2 lands the abstraction layer the rest of the agents will sit on top of — the `LLMProvider` interface with concrete Anthropic and Mistral implementations, the structured `APILogger` that records every LLM call, the `PromptLoader` that reads externalised prompts, and the Validator agent that runs the full RAG-driven coverage decision end-to-end against a real Mistral Large call. Phase 3 next adds the remaining three agents (Doc-Parser, Adjuster, Guardrail) on top of the same plumbing.

**Completed at:** 2026-05-11T11:49:47Z
**Phase:** 2 — LLM Gateway and Validator agent
**Status:** Complete (no deferrals)

**Links**

- Prompt: [`docs/prompts/03-phase-2-llm-gateway-and-validator.md`](03-phase-2-llm-gateway-and-validator.md)
- Plan (approved): [`docs/prompts/03-phase-2-llm-gateway-and-validator-plan.md`](03-phase-2-llm-gateway-and-validator-plan.md) — approved 2026-05-11T11:18:07Z
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 2 entry)
- Repository: pushed to `main` after this commit lands; Render redeploys automatically once `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` are set on the service.

**CI status.** Unchanged from Phase 1. The pgvector service container, Alembic upgrade step, ruff / mypy / pytest pipeline, and advisory `pip-audit` step all remain. No new CI dependencies. The gated `RUN_LLM_E2E_TESTS=1` Validator real-call test does not run in CI.

---

## Files created

### LLM Gateway

- `backend/app/llm/__init__.py` — public surface (`LLMProvider`, `ProviderResponse`, `LLMProviderError`, `AnthropicProvider`, `MistralProvider`, `get_provider`, `ResponseFormat`).
- `backend/app/llm/provider.py` — `LLMProvider` ABC with keyword-only `complete(...)` enforcing `system` / `user` separation. `ProviderResponse` frozen dataclass. `LLMProviderError` is the single funnel exception every provider raises on failure.
- `backend/app/llm/anthropic_provider.py` — wraps `anthropic.Anthropic`. Passes `system` at the top level; user content in `messages[0]`. Coerces token usage from `usage.input_tokens` / `usage.output_tokens`. Empty content / non-text first block refused. Empty API key refused at construction.
- `backend/app/llm/mistral_provider.py` — wraps `mistralai.client.Mistral`. Places the system message as the first list entry (Mistral's SDK convention). Native JSON mode via `response_format={"type":"json_object"}` when the caller asks for it. Empty content / empty choices refused. Empty API key refused at construction.
- `backend/app/llm/factory.py` — `get_provider(settings, vendor)` keyed by `(id(settings), vendor)` against a module-level cache dict. (Not `lru_cache` because `Settings` is mutable / unhashable.) Constructs a fresh `APILogger` per Settings, passes the pricing table through. `clear_provider_cache()` exposed for tests.

### Structured logging

- `backend/app/logging/__init__.py` — public surface (`APICallRecord`, `APILogger`, `compute_cost_usd`).
- `backend/app/logging/api_logger.py` — Pydantic `APICallRecord` with the locked JSON shape. `APILogger` class with enabled-flag gating, configurable excerpt budget, optional `redactor` hook, default stdlib-logger stdout sink, and optional sidecar file sink. `compute_cost_usd` consults the Settings pricing dict; null when no rate is configured. Module helpers `make_excerpt` and `coerce_error` are exposed so provider code can build excerpts and error payloads without instantiating a logger.

### Prompt loader and externalised prompts

- `backend/app/prompts/__init__.py` — extended to re-export `PromptLoader`, `PromptNotFoundError`, `PromptFormatError`.
- `backend/app/prompts/loader.py` — `PromptLoader` with strict placeholder substitution (missing placeholders raise `PromptFormatError`), `[A-Za-z0-9_-]+` name regex, path-traversal guard after `resolve()`, 64 KB file size cap, module-level content cache, `clear_cache()` class method for tests.
- `backend/app/prompts/system/validator.md` — first externalised system prompt. Defines the persona, the strict JSON output shape, and the anti-hallucination citation rule.
- `backend/app/prompts/user/validator_template.md` — first externalised user template with `{claim_narrative}` and `{retrieved_chunks}` placeholders.

### Validator agent

- `backend/app/agents/__init__.py` — public surface.
- `backend/app/agents/validator_models.py` — `RetrievedChunk`, `CitedChunk`, `ValidatorVerdict`, `ValidatorResult`. Bounds (`confidence` 0..1, `cited_chunks` length 1..3) enforce the schema at the Pydantic boundary.
- `backend/app/agents/validator.py` — `Validator` class with collaborator injection. `evaluate(...)` orchestrates load → embed → retrieve → format → call → parse → audit → return. Helpers each ≤ 30 lines. Embedding model lazy-loaded via module-level `lru_cache(maxsize=1)`; the `default_embedder` factory returns a callable that closes over the cached model.

### Tests

- `backend/tests/conftest.py` — extended with the Phase-2 fixtures (`prompt_loader`, `stub_embedder`, `mock_provider`, `null_api_logger`) plus the `MockProvider` / `MockProviderCall` dataclasses.
- `backend/tests/test_settings_phase2.py` — 13 tests.
- `backend/tests/test_prompt_loader.py` — 11 tests.
- `backend/tests/test_api_logger.py` — 13 tests.
- `backend/tests/test_llm_provider_anthropic.py` — 5 tests via `monkeypatch.setattr` on the SDK client.
- `backend/tests/test_llm_provider_mistral.py` — 5 tests via `monkeypatch.setattr` on the SDK client.
- `backend/tests/test_validator.py` — 9 unit tests using the real `clean_db` fixture + mocked provider + stub embedder, plus 1 gated `test_validator_real_call` (skipped unless `RUN_LLM_E2E_TESTS=1` and `MISTRAL_API_KEY` are set).
- `backend/tests/test_validator_prompts.py` — 3 golden-shape tests for the externalised prompts.

## Files modified

- `pyproject.toml` — version `0.0.1 → 0.2.0`; added `anthropic>=0.40` and `mistralai>=1.5` runtime deps; mypy override for `mistralai.*` (no `py.typed`).
- `uv.lock` — regenerated; resolved `anthropic 0.100.0`, `mistralai 2.4.5`.
- `render.yaml` — `buildCommand: uv sync → uv sync --no-dev`. CI still uses plain `uv sync`.
- `backend/settings.py` — added `LoggingSettings`, `RetrievalSettings`; new `LLMSettings` fields (`validator_max_tokens`, `validator_temperature`, `request_timeout_s`, `pricing`). Bounds enforce typo-protection at config time.
- `backend/settings.yaml.template` — extended with matching `logging` and `retrieval` blocks; pricing example commented out.
- `backend/app/prompts/__init__.py` — re-exports the loader surface (replaced the placeholder file).
- Removed `backend/app/prompts/system/.gitkeep` and `backend/app/prompts/user/.gitkeep` now that real prompt files exist.
- `CLAUDE.md` — Current Status updated.

## Tests — counts and pass rates

| Module | Tests |
|---|---|
| `test_settings.py` (Phase 0, unchanged) | 6 |
| `test_health.py` (Phase 0, unchanged) | 1 |
| `test_settings_phase1.py` (Phase 1, unchanged) | 11 |
| `test_audit_canonical.py` (Phase 1, unchanged) | 7 |
| `test_audit_chain.py` (Phase 1, unchanged) | 8 |
| `test_audit_writer.py` (Phase 1, unchanged) | 7 |
| `test_audit_verify.py` (Phase 1, unchanged) | 4 |
| `test_seed_claims.py` (Phase 1, unchanged) | 8 |
| `test_index_policy.py` (Phase 1, unchanged) | 8 (+1 conditional, skipped by default) |
| `test_schema.py` (Phase 1, unchanged) | 5 |
| `test_settings_phase2.py` (Phase 2) | 13 |
| `test_prompt_loader.py` (Phase 2) | 11 |
| `test_api_logger.py` (Phase 2) | 13 |
| `test_llm_provider_anthropic.py` (Phase 2) | 5 |
| `test_llm_provider_mistral.py` (Phase 2) | 5 |
| `test_validator.py` (Phase 2) | 9 (+1 conditional, skipped by default) |
| `test_validator_prompts.py` (Phase 2) | 3 |
| **Backend total** | **122 passing, 2 skipped, 0 failing** |
| Frontend (`vitest`) | 2 passing |
| **Repository total** | **124 passing, 2 skipped, 0 failing** |

`uv run ruff check .` — clean. `uv run mypy backend` — clean (53 source files).

The gated `test_validator_real_call` was run once locally with `RUN_LLM_E2E_TESTS=1` and `MISTRAL_API_KEY` populated. It completed in 7.35 s including the live Mistral round-trip and returned a typed `ValidatorVerdict` that survived the anti-hallucination citation cross-check.

## Deviations from the plan, with reasons

1. **`get_provider` uses a module-level dict, not `functools.lru_cache`.** The plan proposed `lru_cache` keyed on `(id(settings), vendor)`; mypy / Python rejected this at runtime because `Settings` is a mutable Pydantic model (unhashable). Functionally equivalent — same `(id, vendor)` keying — but the cache is now an explicit `dict[tuple[int, ProviderVendor], LLMProvider]` with a `clear_provider_cache()` helper.
2. **pgvector cast added to the retrieval SQL.** The plan said `ORDER BY embedding <=> %s LIMIT 3`; that operator rejects `double precision[]` bindings, so the actual SQL is `embedding <=> %s::vector` in both places. Documented inline. No interface change for callers.
3. **`response_format="json"` is a no-op on `AnthropicProvider`.** Anthropic's SDK has no native JSON-mode flag; the parameter is accepted for interface symmetry with Mistral and the system prompt remains responsible for enforcing the format. Phase 2's Validator only uses Mistral, so this is forward-looking surface area rather than an immediate concern.
4. **`mistralai` import path is `mistralai.client.Mistral`**, not `mistralai.Mistral` as the plan implicitly suggested. The resolved 2.4.5 package re-exports nothing at the top level; everything lives under `mistralai.client` and `mistralai.client.errors`. Documented in the provider module header.
5. **`SentenceTransformer` return type is `Any`.** The library does not ship `py.typed`. The `_load_embedding_model` cache returns `Any` with a docstring note rather than a typed `SentenceTransformer` instance. Callers still receive the real object.

No other deviations.

## Guard clauses added

Every guard has a triggering test that asserts on the message content, not just on the exception type.

- `LoggingSettings.api_log_excerpt_chars` — `ge=100, le=20_000` rejects out-of-range budgets.
- `RetrievalSettings.top_k` — `ge=1, le=20` clamps zero / runaway values.
- `LLMSettings.validator_max_tokens` — `ge=1, le=8192`.
- `LLMSettings.validator_temperature` — `ge=0.0, le=1.0`.
- `LLMSettings.request_timeout_s` — `ge=1.0, le=600.0`.
- `PromptLoader._load` — empty name, name with path separators / `..`, kind outside `("system","user")`, resolved path that escapes the base directory — all rejected.
- `_read_prompt_file` — missing file (`PromptNotFoundError`), empty file, oversize file, non-regular file — all rejected.
- `_StrictMapping.__missing__` — unfilled placeholder raises a `PromptFormatError` naming the missing key and the supplied keys.
- `PromptLoader` constructor — `base_path` must be an existing directory.
- `APILogger.__init__` — `excerpt_chars` must be `>= 1`.
- `APICallRecord` — `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_ms` all `ge=0`; `step` non-empty; `model` non-empty.
- `compute_cost_usd` — negative rates rejected with a diagnostic message.
- `AnthropicProvider.__init__` — empty API key rejected with `ANTHROPIC_API_KEY` named in the message.
- `AnthropicProvider.complete` — empty `system`, empty `user`, empty `model` rejected.
- `_extract_text` (Anthropic) — empty `content` list, non-text first block rejected.
- `MistralProvider.__init__` — empty API key rejected with `MISTRAL_API_KEY` named in the message.
- `MistralProvider.complete` — empty `system`, `user`, `model` rejected; null SDK return rejected.
- `_extract_text` (Mistral) — empty `choices`, null `message`, non-string / empty `content` rejected.
- `Validator._load_narrative` — claim not found, narrative empty / non-string.
- `Validator._embed_narrative` — non-ndarray return, wrong dimension.
- `Validator._retrieve_top_chunks` — empty result set ("has the policy been indexed?").
- `_parse_verdict` — non-JSON response (no `{...}` block), JSON that is not an object, JSON that fails `ValidatorVerdict` validation.
- `_assert_citations_subset` — cited chunk id not in retrieved set ("anti-hallucination guard").

## Optional enhancements recommended for follow-on work

Flagged in the plan as optional; recommended for the phases noted.

1. **Retry with exponential backoff** via `tenacity` (recommended Phase 6). Wrap the SDK call inside `complete(...)`; map to the existing `LLMProviderError` boundary.
2. **Streaming SSE responses** through the provider interface (Phase 4 when the orchestrator wires SSE).
3. **Populate `LLMSettings.pricing` with current rates** so `cost_usd` lights up in the API log (Phase 6 polish).
4. **PII redactor for the APILogger** (Phase 7 documentation — flag the hook with a real implementation).
5. **Validator prompt golden-text fixtures as `.golden` files** (Phase 6 polish; cleaner than inline string asserts).

## Outstanding items requiring architect involvement

1. **Set `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` on Render's Environment tab** to the values supplied in chat. Render will auto-redeploy after the env-var changes. Confirm the redeploy goes Live without errors (Render service logs show "Application startup complete.").
2. **Verify the deployed backend reports `version=0.2.0`** at the `/health` endpoint after redeploy — that confirms the per-phase versioning signal is propagating.
3. **(Optional) Verify the deployed backend reaches the LLM providers.** Phase 2 does not expose a Validator endpoint yet (Phase 4 does), so the simplest live check is the Render service logs at startup — provider construction is lazy, so they will not run until the Validator endpoint lands. No action required for Phase 2.

That is the full residual list. The repository runs end-to-end locally without further architect input; the gated `RUN_LLM_E2E_TESTS=1` test confirmed the Mistral live integration.
