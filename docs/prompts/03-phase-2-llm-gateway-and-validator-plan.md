# Plan 03 — Phase 2: LLM Gateway and Validator Agent

## Goal

Stand up the abstraction layer the rest of the agents will sit on top of, plus the first agent end-to-end. By the end of this phase the system contains:

- An `LLMProvider` interface with two implementations (`AnthropicProvider`, `MistralProvider`) that mediate every LLM call. Both raise on any non-recoverable failure (no silent fallback). System / user message separation is enforced at the interface — providers translate to vendor SDK shapes internally.
- An `APILogger` that writes one structured JSON record per LLM call (provider, model, prompts, response, tokens, cost, latency, correlation ID, agent, step), gated by a new `LoggingSettings.api_log_enabled` flag.
- A `PromptLoader` that loads externalised prompts from `backend/app/prompts/system/` and `backend/app/prompts/user/`. No inline f-string prompts in any source file.
- The **Validator agent** running end-to-end against the seeded claims: load claim → embed narrative via the same `bge-small-en-v1.5` model used at indexing time → retrieve top 3 chunks from `policy_chunks` via pgvector cosine distance → assemble augmented prompt via `PromptLoader` → call Mistral Large via the Gateway with system / user separation → parse the structured response → write a complete audit-log entry under a correlation ID → return a typed `ValidatorResult`.

No other agents (Doc-Parser, Adjuster, Guardrail, Orchestrator). No pipeline, no UI changes, no decoupled trigger flow. Phase 3 brings the remaining agents; Phase 4 wires the orchestrator. Every interface introduced in Phase 2 (`LLMProvider`, `ValidatorResult`, `APICallRecord`, validator-step audit payload) becomes a contract those later phases depend on.

Plus two small preamble fix-ups bundled into the same Phase 2 commit (per the prompt):

- Bump `pyproject.toml` version `0.0.1` → `0.2.0`. Per-phase versioning makes the `/health` `version` field a useful traceability signal.
- Tighten `render.yaml`'s `buildCommand` from `uv sync` to `uv sync --no-dev`. Dev dependencies don't belong in the production container.

## Files and directories I will create or modify

### LLM Gateway (new top-level area)

- `backend/app/llm/__init__.py` — re-exports `LLMProvider`, `ProviderResponse`, `LLMProviderError`, `get_provider`.
- `backend/app/llm/provider.py` — the interface and shared types.
  - `LLMProvider` — abstract base class (Python `abc.ABC`). Single method `complete(...)` (signature below).
  - `ProviderResponse` — frozen dataclass: `text: str`, `model: str`, `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int`, `latency_ms: int`, `raw: dict[str, Any]`. The `raw` field is the SDK's serialised response, kept for the audit log.
  - `LLMProviderError` — exception type wrapping any provider-side failure (auth, network, malformed response). All provider impls raise this on failure; callers catch one type at the API boundary.
- `backend/app/llm/anthropic_provider.py` — `AnthropicProvider(LLMProvider)`. Constructor takes `api_key: SecretStr` (required) and `default_max_tokens: int`. `complete(...)` calls `anthropic.Anthropic(api_key=...).messages.create(...)` with `system` as the top-level parameter and `messages=[{"role":"user","content":user}]`. Token counts from `response.usage.input_tokens` / `output_tokens`. Latency timed via `time.perf_counter()` either side of the call. Raises `LLMProviderError` on `anthropic.APIError`, empty response content, or unexpected response shape.
- `backend/app/llm/mistral_provider.py` — `MistralProvider(LLMProvider)`. Same shape. Calls `mistralai.Mistral(api_key=...).chat.complete(model=..., messages=[{"role":"system","content":system},{"role":"user","content":user}], max_tokens=..., temperature=..., response_format=...)`. Mistral takes the system message as the first message in the list rather than a top-level parameter; the provider does the translation internally so the interface contract (separate `system` and `user` arguments) stays consistent. Token counts from `response.usage`. Same error wrapping.
- `backend/app/llm/factory.py` — `get_provider(settings: Settings, vendor: Literal["anthropic", "mistral"]) -> LLMProvider`. Cached via `functools.lru_cache` on the `(id(settings), vendor)` key — a single Settings object yields a single provider per vendor. Validates the API key is present on construction; raises `ValueError` with a clear message if not. Phase 2's first call to a provider triggers construction; tests bypass via direct instantiation with stub settings.

The `complete(...)` signature on `LLMProvider`:

```python
def complete(
    self,
    *,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    temperature: float,
    response_format: Literal["text", "json"] = "text",
    timeout_s: float = 60.0,
) -> ProviderResponse: ...
```

Notes on the signature:

- Keyword-only arguments. No positional — call sites become self-documenting.
- `system` and `user` are separate strings. Providers cannot collapse them. This is the global system/user-separation rule encoded in the type system.
- `response_format="json"` requests JSON-mode if the SDK supports it (Mistral does via `response_format={"type": "json_object"}`; Anthropic does not have a true JSON mode and the prompt itself enforces format — Phase 2's Validator uses Mistral so this is sufficient).
- `timeout_s` is per-call. Default 60s is comfortable for the prototype's prompt sizes.
- Returns a typed `ProviderResponse`, never a raw SDK object.
- No retry logic in the interface. Retries are an optional enhancement (`tenacity`) and are not added in Phase 2 — every transient failure surfaces to the caller, who decides. Documented under "Optional enhancements" below.

### API logger

- `backend/app/logging/__init__.py` — re-exports `APILogger`, `APICallRecord`.
- `backend/app/logging/api_logger.py` — the structured logger.
  - `APICallRecord` — Pydantic model with the JSON contract:
    - `correlation_id: UUID`
    - `agent: AgentName` (reused from `audit.event`)
    - `step: str`
    - `provider: Literal["anthropic", "mistral"]`
    - `model: str`
    - `system_prompt_excerpt: str` (first N chars; full text is in the audit log)
    - `user_prompt_excerpt: str`
    - `response_excerpt: str`
    - `prompt_tokens: int`
    - `completion_tokens: int`
    - `total_tokens: int`
    - `cost_usd: float | None` — populated only if a pricing rate is configured for the model (see below); otherwise null. Phase 2 ships with no rates so the field is consistently null and the consumer can treat null as "rate not configured".
    - `latency_ms: int`
    - `started_at: datetime` (UTC, tz-aware)
    - `completed_at: datetime`
    - `error: dict[str, str] | None` — class name and message for failures; null on success.
  - `APILogger` — class. Constructor takes `enabled: bool`, `excerpt_chars: int`, `redactor: Callable[[str], str]`, `sink: Callable[[str], None]`. Method `log_call(record: APICallRecord)` serialises to canonical JSON via `json.dumps(record.model_dump(mode="json"), sort_keys=True, default=str)` and pushes to the sink. The `redactor` is the identity by default; a Phase 6+ enhancement could install a PII redactor.
  - The Gateway providers call into the logger from their `complete(...)` implementation in a try/finally so failures are recorded too. The error path constructs an `APICallRecord` with `error` set and excerpts truncated to whatever is available.
- The default sink is a stdlib `logging.Logger` named `backend.app.logging.api`, configured at app startup to write JSON records to stdout. Render captures stdout; that's the deployed-side path. The optional `LoggingSettings.api_log_path` (a file path) is honoured if set — useful for local development when you want to grep call records without scrolling the server log.
- Excerpt budget (`excerpt_chars`) defaults to 2000 — enough to read most prompts, small enough that a noisy call doesn't flood the log. Configurable via `LoggingSettings`.

### Prompt loader and externalised prompts

- `backend/app/prompts/loader.py` — `PromptLoader` class.
  - Constructor: `PromptLoader(base_path: Path | None = None)`. Defaults to the directory of `loader.py` itself (= `backend/app/prompts/`).
  - Method `system(name: str) -> str` — loads `<base>/system/<name>.md` verbatim (no formatting). Raises `PromptNotFoundError` on missing file; `ValueError` on empty file or oversized file.
  - Method `user(name: str, **kwargs: object) -> str` — loads `<base>/user/<name>.md` and formats with `.format_map(_StrictMapping(kwargs))`. The strict mapping raises on any unfilled placeholder (so a typo in a placeholder name is a hard error, not a silent empty substitution).
  - Defensive guards on `name`: rejects values containing `/`, `\`, `..`, or any character outside `[A-Za-z0-9_-]`. Path-traversal guard. Tested.
  - Sanitise → validate → abort → execute throughout.
  - File contents cached at module level via `functools.lru_cache` keyed on `(kind, name)`. Cache is invalidated on test setup via a `clear_cache()` classmethod so test edits to prompt files take effect.
  - Maximum prompt file size: 64 KB (named constant). A genuinely larger prompt is a smell; raising loudly forces the writer to think.
- `backend/app/prompts/system/validator.md` — first system prompt. Defines the validator persona ("You are a coverage validator for commercial property claims..."), the strict JSON output schema, and the citation rules (must cite chunk IDs from the provided context; must not invent endorsements or sub-limits not present in the chunks).
- `backend/app/prompts/user/validator_template.md` — first user template. Placeholders: `{claim_narrative}`, `{retrieved_chunks}`. The `retrieved_chunks` placeholder is filled with a formatted block (one chunk per paragraph, prefixed with chunk ID and section name).

The two `.gitkeep` files under `backend/app/prompts/system/` and `backend/app/prompts/user/` are removed once the real files land.

### Validator agent

- `backend/app/agents/__init__.py` — package marker.
- `backend/app/agents/validator.py` — the `Validator` class and supporting types.
  - `Validator(LLMProvider, embedding_model, prompt_loader, audit_writer, api_logger, settings).evaluate(claim_id: UUID, correlation_id: UUID) -> ValidatorResult` is the entry point.
  - Constructor takes the collaborators by injection — every test can swap the LLM, the embedding model, the audit writer, the API logger, and the settings independently. Production wiring (Phase 4) will use a small factory.
- `backend/app/agents/validator_models.py` — Pydantic types:
  - `RetrievedChunk { chunk_id: UUID, section: str, content: str, similarity: float }`
  - `CitedChunk { chunk_id: UUID, section: str }` — what the model returns; we re-resolve the similarity from the retrieved set so the model can't fabricate numbers.
  - `ValidatorVerdict { covered: bool, confidence: float (0..1), reasoning: str (min length 1), policy_basis: str (min length 1), cited_chunks: list[CitedChunk] (1..3 items) }`. This is the JSON shape Mistral is asked to return; a Pydantic validator parses it.
  - `ValidatorResult { claim_id: UUID, correlation_id: UUID, verdict: ValidatorVerdict, retrieved_chunks: list[RetrievedChunk], model: str, latency_ms: int }`. This is the function's return type, locked at end-of-phase.

The `evaluate(...)` flow, decomposed into named helpers (each ≤30 lines):

1. `_load_claim(claim_id)` — fetches `narrative` from `claims` for the given id; raises `ValueError` if not found, with the id quoted in the message.
2. `_embed_narrative(narrative)` — sanitises (rejects empty/whitespace), embeds via `embedding_model.encode(...)` with `normalize_embeddings=True`, returns a `numpy.ndarray` of shape `(384,)`. Validates the dimension matches `settings.embedding.dimension` and re-raises with a clear message on mismatch.
3. `_retrieve_top_chunks(query_vector, k=3)` — opens a connection, runs `SELECT chunk_id, section, content, 1 - (embedding <=> %s) AS similarity FROM policy_chunks WHERE source_path = %s ORDER BY embedding <=> %s LIMIT %s`, returns `list[RetrievedChunk]`. Raises `ValueError` if the result is empty (an unindexed deployment is a configuration bug). Cosine *distance* is `<=>`; cosine *similarity* is `1 - distance` and is stored in the `RetrievedChunk` (matches what the diagram calls a "similarity score").
4. `_build_user_prompt(narrative, chunks)` — formats `{claim_narrative}` and `{retrieved_chunks}` via `PromptLoader.user("validator_template", ...)`. The chunks block uses the format `"[chunk_id={uuid}, section={section}]\n{content}"`, joined with two blank lines.
5. `_call_provider(system, user)` — calls `provider.complete(system=..., user=..., model=settings.llm.mistral.validator_model, max_tokens=settings.llm.validator_max_tokens, temperature=settings.llm.validator_temperature, response_format="json")`. Returns `ProviderResponse`. Latency captured here.
6. `_parse_verdict(response_text, retrieved_chunks)` — defensively extracts JSON: strip leading/trailing whitespace, locate the outermost `{...}` if the model wrapped in prose, parse via `json.loads`, validate via `ValidatorVerdict.model_validate(...)`. Then cross-checks: every `cited_chunks[].chunk_id` must be in the retrieved set; otherwise raise `ValueError` with both the cited and retrieved id sets in the message. The cross-check is the anti-hallucination guard at this layer.
7. `_audit_log(correlation_id, claim_id, retrieved, response, verdict, latency_ms)` — constructs the validator-step audit event. Payload shape locked at end-of-phase:

```json
{
    "agent": "validator",
    "step": "coverage_check",
    "input": {
        "claim_id": "<uuid>",
        "narrative_excerpt": "<first 500 chars>"
    },
    "retrieval": {
        "top_k": 3,
        "chunks": [
            {"chunk_id": "<uuid>", "section": "...", "similarity": 0.82, "content_excerpt": "..."}
        ]
    },
    "llm_call": {
        "provider": "mistral",
        "model": "mistral-large-2512",
        "prompt_tokens": 523,
        "completion_tokens": 187,
        "latency_ms": 1340
    },
    "verdict": {
        "covered": true,
        "confidence": 0.83,
        "reasoning": "...",
        "policy_basis": "...",
        "cited_chunks": [{"chunk_id": "...", "section": "..."}]
    }
}
```

Defensive guards in `evaluate(...)`, each with a triggering test that asserts on message content:

- Claim id not in `claims` → `ValueError`
- Narrative empty / whitespace → `ValueError`
- `policy_chunks` empty (no rows for the configured `source_path`) → `ValueError`
- Embedding model returns wrong dimension → `ValueError`
- Mistral returns non-JSON text → `ValueError` with response excerpt
- Mistral returns JSON that fails `ValidatorVerdict` validation → `ValueError` chaining the Pydantic error
- Verdict cites a chunk id not in the retrieved set → `ValueError` with both id sets quoted
- Provider raises `LLMProviderError` → audit log entry written *first* with `error` populated, then re-raised. The audit chain captures the failure as a record, not a gap.

### Settings extensions

- `backend/settings.py` — extended in place.
  - New `LoggingSettings` sub-model:
    - `api_log_enabled: bool = True`
    - `api_log_excerpt_chars: int = 2000` (`ge=100, le=20000`)
    - `api_log_path: Path | None = None` (None = stdout sink only)
  - New fields on `LLMSettings` for per-call defaults:
    - `validator_max_tokens: int = 1024`
    - `validator_temperature: float = 0.1` (`ge=0.0, le=1.0`)
    - `request_timeout_s: float = 60.0` (`ge=1.0, le=600.0`)
  - New optional pricing block on `LLMSettings.pricing: dict[str, tuple[Decimal, Decimal]] = {}` — key is model name; value is `(input_per_million_tokens, output_per_million_tokens)` in USD. Empty default keeps `cost_usd` null. Documented as "populate to opt into cost tracking; recommended for Phase 6+ polish".
  - New `policy_source_path: Path = Path("backend/data/sample_policy.txt")` on a small `RetrievalSettings` sub-model — the validator filters `policy_chunks` by `source_path` so retrieval is scoped to the indexed corpus rather than blindly searching the whole table. Mirrors the indexing script's path.
- `backend/settings.yaml.template` — extended with matching `logging`, `retrieval`, and additional `llm` blocks. Every field commented. Pricing block included as a commented-out example so a future operator can opt in without re-deriving the shape.

### Tests

All under `backend/tests/`. Existing tests remain green (no changes to existing files except for the conftest extensions noted below). New files:

- `backend/tests/test_settings_phase2.py` — sub-model defaults; bounds checks on the new numeric fields; pricing dict shape; logging path override. ~8 tests.
- `backend/tests/test_prompt_loader.py` — load existing system/user; missing file raises `PromptNotFoundError`; empty file raises `ValueError`; oversized file raises `ValueError`; path-traversal `name` rejected; user template missing placeholder raises a clear error; cached load returns the same string instance until `clear_cache()`. ~9 tests.
- `backend/tests/test_api_logger.py` — successful call writes one canonical-JSON record to the sink with all fields populated; disabled logger writes nothing; failure path includes `error` field; redactor applied to prompt fields; excerpts truncated to `excerpt_chars`. ~6 tests.
- `backend/tests/test_llm_provider_anthropic.py` — provider construction rejects missing API key; `complete()` translates `system`/`user` into the SDK's `system` parameter and `messages=[{user}]`; the wrapper raises `LLMProviderError` on `anthropic.APIError`; empty content raises. ~5 tests. Uses a `unittest.mock.patch` over the SDK client so no network call.
- `backend/tests/test_llm_provider_mistral.py` — same shape for Mistral. Verifies the system message is placed first in the messages list (not as a top-level parameter, since Mistral's API uses message-role conventions). ~5 tests. Mocked SDK.
- `backend/tests/test_validator.py` — unit tests with the LLM provider, embedding model, audit writer, and API logger all stubbed:
  - happy path: known retrieved chunks → known model JSON → `ValidatorResult` with the expected shape; audit-log entry written with the locked payload shape.
  - claim not found.
  - empty narrative.
  - empty `policy_chunks` table for the configured source path.
  - embedding model returns wrong dimension.
  - model returns non-JSON.
  - model returns JSON that violates `ValidatorVerdict` (e.g. `confidence` > 1).
  - model cites a chunk id not in the retrieved set.
  - provider raises → audit log entry has `error`; the exception propagates.
  - real-call test (skipped by default; gated by `RUN_LLM_E2E_TESTS=1`) — exercises the full flow against Mistral with a single seed claim. Asserts on shape, not on content. Documented in the report.
  - ~12 tests total (10 unit + 1 integration + 1 e2e gated).
- `backend/tests/test_validator_prompts.py` — golden-text test: the system prompt and the formatted user prompt for a known claim render to a known string. Catches accidental edits to the prompt files. ~2 tests.

`backend/tests/conftest.py` — extended with three new fixtures:

- `prompt_loader` — a `PromptLoader` rooted at `backend/app/prompts/`, with cache cleared on each test.
- `embedding_model` (session-scoped) — loads the real `bge-small-en-v1.5` model once. Available to the integration tests; unit tests don't take this dependency and use `stub_embedder` instead.
- `stub_embedder` — a callable returning a fixed 384-dim vector for unit tests; deterministic.
- `mock_provider` — a callable returning a stub `LLMProvider` whose `complete()` returns a configured `ProviderResponse`. Used pervasively in the validator tests.

### Repo-root and docs

- `pyproject.toml` — version bumped `0.0.1 → 0.2.0`. Two new runtime deps: `anthropic>=0.40`, `mistralai>=1.5`. No new dev deps.
- `uv.lock` — regenerated by `uv add`.
- `render.yaml` — `buildCommand: uv sync` → `buildCommand: uv sync --no-dev`.
- `.env.example` — already has the two API key placeholders from Phase 0; no changes needed.
- `docs/build-log.md` — appended with the Phase 2 entry per the standard format.
- `docs/prompts/03-phase-2-llm-gateway-and-validator-report.md` — the report (written at end of phase per Step 5).
- `CLAUDE.md` — Current Status block updated to "Phase 2 complete; Phase 3 next" with the right one-liners.

## Validator output schema (locked at end of phase)

The exact JSON Mistral is asked to return:

```json
{
    "covered": true,
    "confidence": 0.83,
    "reasoning": "The water-damage narrative aligns with named-perils language for sprinkler leakage and water damage from plumbing systems.",
    "policy_basis": "Named Perils Covered, Sub-Limits",
    "cited_chunks": [
        {"chunk_id": "<uuid>", "section": "Named Perils Covered"},
        {"chunk_id": "<uuid>", "section": "Sub-Limits"}
    ]
}
```

Constraints enforced by `ValidatorVerdict`:

- `covered: bool`
- `confidence: float`, `0.0 <= x <= 1.0`
- `reasoning: str`, min length 1
- `policy_basis: str`, min length 1
- `cited_chunks: list[CitedChunk]`, length 1–3
- Cross-validation: every `chunk_id` in `cited_chunks` must appear in the retrieved top-3 set (the anti-hallucination guard).

## LLM Gateway construction model

- **Lazy via factory.** `get_provider(settings, vendor)` is `functools.lru_cache`-cached on `(id(settings), vendor)`. First call constructs (and validates the API key); subsequent calls reuse the same instance. Tests bypass the cache by instantiating providers directly with stub settings.
- **Not a singleton.** Different settings → different providers. This matters for integration tests that pin a configuration without polluting the global instance.
- **No app-startup init.** Providers are constructed on first use. The `/health` endpoint stays free of LLM concerns; Render's startup probe doesn't call out to Anthropic/Mistral.

## API logger integration with the Gateway

The provider implementations own the timing and the logging. Each `complete(...)` body has the shape:

```python
started_at = datetime.now(UTC)
t0 = time.perf_counter()
record_kwargs = { ... excerpts and metadata ... }
try:
    sdk_response = self._client.messages.create(...)  # or chat.complete(...)
    response = self._coerce_to_provider_response(sdk_response)
    record = APICallRecord(..., **response_metrics(response), error=None)
    return response
except (anthropic.APIError, mistralai.SDKError) as exc:
    record = APICallRecord(..., error={"type": type(exc).__name__, "message": str(exc)})
    raise LLMProviderError(...) from exc
finally:
    record_kwargs["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    record_kwargs["completed_at"] = datetime.now(UTC)
    self._api_logger.log_call(APICallRecord(**record_kwargs))
```

Sketch only; final code splits into helpers to stay under the function-size cap. The API logger is injected, not a global — same testability principle as elsewhere.

## Embedding model loading strategy

- Module-level cache in `backend/app/agents/validator.py`: `@functools.lru_cache(maxsize=1)` on a private `_load_embedding_model(model_name: str) -> SentenceTransformer`. Keyed on the model name so a hypothetical (but-not-supported) model swap doesn't return a stale instance.
- The model is loaded on first `Validator.evaluate(...)` call. Cost: ~3 seconds and ~50MB RAM the first time.
- For unit tests, the `Validator` constructor takes a callable `embedder: Callable[[str], np.ndarray]` rather than a `SentenceTransformer` instance. The default factory wires the real model; tests pass a stub. Same testability principle.
- For the gated end-to-end test, the real model is used via the session-scoped `embedding_model` fixture — load cost is paid once across the test session, not per test.

## Testing strategy — concrete recommendation

**Recommendation: pure-Python mocks at the `LLMProvider` boundary plus one opt-in real-call test.**

- The `Validator` takes its provider by injection. Unit tests pass a stub provider whose `complete()` returns a configured `ProviderResponse`. No SDK invoked, no HTTP traffic, no recording overhead.
- For the provider implementations themselves (`AnthropicProvider`, `MistralProvider`), tests `unittest.mock.patch` the SDK client so the wrapper logic is exercised without a real API key. ~5 tests per provider.
- One end-to-end test (`test_validator_real_call`) gated by `RUN_LLM_E2E_TESTS=1` and a present `MISTRAL_API_KEY`. Skipped by default; documented in the README and the report. Runs locally during development to confirm the live integration; not in CI.

**Why not VCR-style cassettes (`vcr.py` / `respx`):**

- We own the interface boundary in pure Python. The whole point of the `LLMProvider` abstraction is that you can mock at that level. Recording HTTP traffic then replaying it adds complexity without a corresponding fidelity gain — the wire shape is already encoded in the SDK, which we don't own and don't want our tests to depend on.
- Cassettes drift silently when the provider's API evolves. Pure mocks at our own interface don't have that problem.
- No new test-only dependency.

**CI implications:** none. The pgvector service container from Phase 1 stays. The `bge-small-en-v1.5` model is already a CI-installed dep from Phase 1. No new CI deps. The end-to-end test is gated and never runs in CI.

## CI changes

None. The pgvector service container, the migration step, the lint / type-check / test pipeline, and the advisory `pip-audit` step all remain. Embedding tests stay gated by `RUN_EMBEDDING_TESTS=1` (Phase 1 decision); the new validator unit tests do not require the real model and run in CI by default.

## New dependencies — flagged

Two required:

- `anthropic>=0.40` — Anthropic Python SDK. Confirmed ergonomics in 0.40+: `client.messages.create(system=..., messages=[{"role":"user","content":...}], model=..., max_tokens=..., temperature=...)`.
- `mistralai>=1.5` — Mistral Python SDK. The 1.x API uses `client.chat.complete(model=..., messages=[...])`. JSON mode via `response_format={"type": "json_object"}`.

Not added in Phase 2 (called out so we don't silently smuggle them):

- `tenacity` — would underwrite retry-with-backoff. Phase 2 ships without retries; transient failures raise immediately. Adding `tenacity` is an optional enhancement tied to a real production-readiness phase, not the prototype.
- `respx` / `vcr.py` — cassette/mocking; not needed because of the in-process-mocking strategy above.

## Risks and downstream impacts

The interfaces locked at end of Phase 2 — these become contracts Phases 3+ depend on, so any change after this phase is an interface-stability event that requires re-acknowledgement:

1. **`LLMProvider.complete(...)` signature.** All future agents will call this. Adding parameters is fine if defaulted; removing or renaming requires explicit review.
2. **`ProviderResponse` shape.** Audit-log entries and the API logger both consume it.
3. **`ValidatorResult` shape.** Phase 4's orchestrator passes this to the escalation engine.
4. **`ValidatorVerdict` JSON shape.** Mistral's response contract; changing it requires re-baselining the prompts and any captured fixtures.
5. **`APICallRecord` JSON shape.** Anyone parsing the api-log stream depends on the field names and types.
6. **Validator-step audit-log payload.** Phase 4's escalation engine reads `payload.verdict.confidence` and `payload.retrieval.chunks[].similarity` to evaluate the threshold rules. Changes ripple.
7. **Settings additions** (`logging`, `retrieval`, new `llm` fields). Adding fields with defaults is non-breaking; renaming or removing is.

Operational risks during execution:

- **Mistral SDK version drift.** Pin a known-good version (`mistralai>=1.5`) in pyproject; verify locally before pushing. The provider wrapper isolates the rest of the codebase from SDK-shape changes.
- **`anthropic` 0.40 vs older APIs.** Same — the wrapper isolates the surface.
- **Embedding model load on first-validator-call latency.** ~3 seconds the first time. For Phase 2's unit tests this is irrelevant; for the gated e2e test it's a one-off. Document in the report.
- **Cosine-distance vs cosine-similarity confusion.** pgvector's `<=>` returns *distance* (0 = identical). The diagram and the audit-log payload speak in *similarity* (1 = identical). The retrieval helper does the conversion; tested explicitly so the convention can't drift.
- **JSON mode availability.** Mistral 1.x supports `response_format={"type": "json_object"}` on Mistral Large. Verify against the live API as part of the gated e2e test before claiming the contract is satisfied.

## Deployment steps requiring architect involvement

Same shape as Phase 1:

1. After plan approval, paste both `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` into the chat. They will be:
   - Written to the local `.env` (already gitignored).
   - Used to run the gated `test_validator_real_call` test once locally to confirm the end-to-end flow.
   - Forwarded back to you as instructions to add on Render's Environment tab so the deployed backend has them.
   - Never committed; never echoed in logs; never written to memory.
2. After the Phase 2 commit lands and pushes:
   - Set `MISTRAL_API_KEY` and `ANTHROPIC_API_KEY` on Render's Environment tab. Render auto-redeploys.
   - Confirm the redeploy goes Live without errors (Render service logs show "Application startup complete.").
   - Optionally hit the public `/health` endpoint and confirm `version` reads `0.2.0` — that's the per-phase signal.

## Optional enhancements (clearly labelled — delivered separately, never silently)

These are recommendations for follow-on phases. Phase 2 ships the spec only.

1. **Retry with exponential backoff** via `tenacity`. Wrap the SDK call inside `complete(...)` with `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APITimeoutError, ...)))`. Maps cleanly into the existing `LLMProviderError` boundary. Recommend Phase 6 (demo polish) — by then the API rates and limits matter.
2. **Streaming responses.** The SSE transport from the locked architecture wants tokens-as-they-come. Phase 4's orchestrator is the natural integration point; defer.
3. **Pricing table.** Populate `LLMSettings.pricing` with current rates so `cost_usd` lights up in the API log. Trivial; defer to Phase 6 when the demo wants to show cost.
4. **PII redactor.** A real `redactor` callable on the `APILogger` for production-grade scrubbing. Synthetic data makes this unnecessary in the prototype; Phase 7 documentation flags the hook.
5. **Validator prompt golden-tests as fixture files.** Right now I propose two inline string asserts. A nicer pattern is one `.golden` file per case; bigger setup, smaller test bodies. Defer.
6. **`verify_audit_chain` CLI** (carried over from Phase 1) — still recommended; still Phase 5/6.
7. **Promote `pip-audit` from advisory to blocking** (carried over from Phase 1) — still recommended once the dep tree is stable.

## Definition of done

- Validator runs end-to-end against any seeded claim, returns a typed `ValidatorResult`, writes a complete audit log entry under a correlation ID. The auto-approve seed claim returns `covered=true` with high confidence; the threshold-escalation seed claim also returns `covered=true` (coverage is fine — the *threshold* is the escalation reason, which Phase 4 evaluates downstream).
- `LLMProvider` interface and both impls in place. Construction fails fast on missing API key.
- `APILogger` writes one JSON record per LLM call to stdout (and optionally a file). Disabled flag suppresses output.
- `PromptLoader` loads externalised prompts. No inline f-string prompts anywhere in source.
- All new code defensively guarded; every guard has a triggering test that asserts on message content.
- `pyproject.toml` is `0.2.0`. `render.yaml` build is `uv sync --no-dev`. `/health` reports `version=0.2.0` after deploy.
- Backend tests pass in CI (lint, type-check, pytest). Frontend untouched.
- Build-log entry appended; report saved; CLAUDE.md updated.
- Phase 2 commit pushed to `main`; Render auto-deploy goes Live.

## Step 1 — Approval gate

This is the canonical plan. Once you approve (any reply along the lines of "yes", "go ahead", "approved", or similar), I will append an `## Approval` footer to this file with the timestamp, then proceed to Step 2 of the prompt — request the API keys and execute Phase 2.

If you reject, I will rename this file to `03-phase-2-llm-gateway-and-validator-plan-rejected-NN.md`, add a `## Rejection` footer summarising your feedback, and produce a revised plan.

---

## Approval

**Approval message:** "Approved.

The eight-decision summary all accepted as proposed:
1. LLMProvider interface with keyword-only system/user args, ProviderResponse typed return, LLMProviderError wrapping — yes.
2. APILogger with APICallRecord shape, excerpts to log, full content to audit, try/finally pattern, optional file sink, nullable cost_usd — yes.
3. PromptLoader with path-traversal guard, strict mapping for placeholders, 64KB cap, cached loads — yes.
4. Validator decomposed into named helpers with collaborator injection, audit log entry written before exception re-raise, cross-validation of cited chunks against retrieved set — yes.
5. Settings extensions: LoggingSettings, new LLMSettings fields, empty pricing dict, RetrievalSettings.policy_source_path — yes.
6. Pure-Python mocks at the LLMProvider boundary, no VCR cassettes, real-call test gated by RUN_LLM_E2E_TESTS=1 — yes.
7. Two new runtime deps (anthropic>=0.40, mistralai>=1.5), no tenacity/respx/vcr — yes.
8. Both preamble fix-ups (pyproject.toml 0.0.1 -> 0.2.0, render.yaml uv sync --no-dev) — yes.

Retries deferred to Phase 6 — accepted; the small live-demo risk of a Mistral 429 is acknowledged.

Proceed to Step 2 (record the approval footer in the plan file with verbatim approval message and ISO 8601 UTC timestamp), then ask me for the API keys."

---

**Approved by:** Dermot Copps
**Approved at:** 2026-05-11T11:18:07Z
