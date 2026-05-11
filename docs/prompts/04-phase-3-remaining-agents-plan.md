# Plan 04 — Phase 3: Remaining Agents

## 1. Goal

Add the three remaining agents — **Doc-Parser** (Claude Haiku), **Adjuster** (Mistral Large), **Guardrail** (Claude Haiku) — each runnable in isolation against the seeded claims, each sitting on the Phase 2 plumbing (`LLMProvider`, `APILogger`, `PromptLoader`, `AuditWriter`). No orchestrator, no pipeline, no UI changes; Phase 4 wires them together.

Bundled preamble fix-up: bump `pyproject.toml` version `0.2.0 → 0.3.0` so the deployed `/health` confirms Phase 3 is live.

---

## 2. Cross-cutting design decisions

### 2.1 No shared base class (recommended)

After Phase 2 the agent shape — constructor injection → `evaluate(...)` → load → call provider → parse → audit → return — is well-established but the *contents* of each step differ enough that a `BaseAgent` abstraction would have to ship as a template-method skeleton with three or four abstract hooks (`_load_input`, `_call_provider`, `_parse_response`, `_build_audit_payload`). The result reads worse than independent files: a reader trying to understand any one agent has to bounce up to the base and back down to interpret each override.

**Recommendation: keep each agent independent**, matching Phase 2. The acceptable amount of duplication is small (audit-event construction, `_excerpt()` helper, `_clamp_unit()`); a small module-level `backend/app/agents/_shared.py` hosts the genuinely reusable helpers without enforcing inheritance.

Specifically `_shared.py` will host:

- `_excerpt(text: str, max_chars: int) -> str` — currently duplicated inline in `validator.py`. Move out, import from both validator and Phase 3 agents.
- `_clamp_unit(value: float) -> float` — same treatment.
- `_new_correlation_id() -> UUID` — same treatment.

This is a refactor of `validator.py` and shows up as a small follow-on diff. No interface change.

### 2.2 Market-data lookup table — `backend/data/market_data.yaml`

Three options weighed:

- **YAML file (recommended).** Declarative, editable by a non-engineer, parseable, version-controlled diff-friendly. A small loader module owns the schema and the lookup function.
- Python dict at module level. Refactorable, but harder to scan when extending.
- Postgres table. Overkill for a static 18-cell lookup; would also require migrations and seed scripts.

#### Shape

```yaml
# backend/data/market_data.yaml
#
# Market-data settlement ranges per (claim_type, severity) cell.
# Severity is derived deterministically from `reported_amount` using the
# `severity_bands` block under each claim_type. Ranges are inclusive on
# both ends. Currency is USD.

version: 1
claim_types:
  water_damage:
    severity_bands:
      minor:    {max_amount: 50000}
      moderate: {max_amount: 150000}
      severe:   {max_amount: null}    # null = unbounded upper
    ranges:
      minor:    {floor: 5000,   ceiling: 50000}
      moderate: {floor: 50000,  ceiling: 200000}     # contains $85k auto-approve scenario
      severe:   {floor: 200000, ceiling: 800000}
  fire:
    severity_bands:
      minor:    {max_amount: 100000}
      moderate: {max_amount: 500000}
      severe:   {max_amount: null}
    ranges:
      minor:    {floor: 20000,  ceiling: 120000}
      moderate: {floor: 120000, ceiling: 600000}
      severe:   {floor: 500000, ceiling: 1500000}    # contains $850k threshold-escalation scenario
  wind:
    severity_bands:
      minor:    {max_amount: 75000}
      moderate: {max_amount: 300000}
      severe:   {max_amount: null}
    ranges:
      minor:    {floor: 5000,   ceiling: 100000}
      moderate: {floor: 75000,  ceiling: 400000}
      severe:   {floor: 250000, ceiling: 1200000}
  theft:
    severity_bands:
      minor:    {max_amount: 30000}
      moderate: {max_amount: 100000}
      severe:   {max_amount: null}
    ranges:
      minor:    {floor: 2000,   ceiling: 40000}
      moderate: {floor: 25000,  ceiling: 150000}
      severe:   {floor: 100000, ceiling: 500000}
  flood:
    severity_bands:
      minor:    {max_amount: 60000}
      moderate: {max_amount: 250000}
      severe:   {max_amount: null}
    ranges:
      minor:    {floor: 10000,  ceiling: 80000}
      moderate: {floor: 50000,  ceiling: 300000}
      severe:   {floor: 200000, ceiling: 1000000}
  storm_complex:
    severity_bands:
      minor:    {max_amount: 150000}
      moderate: {max_amount: 600000}
      severe:   {max_amount: null}
    ranges:
      minor:    {floor: 25000,  ceiling: 200000}
      moderate: {floor: 150000, ceiling: 700000}
      severe:   {floor: 600000, ceiling: 1800000}    # contains $1.4M guardrail-escalation scenario
```

Six claim types (the five the prompt asked for, plus `storm_complex` to cover the demo scenario 3 narrative that already exists in the seed). Three severities each. Eighteen cells total.

#### Severity-derivation logic

**Severity is always derived inside the Adjuster from the reported amount** using the `severity_bands` block for that claim type. It is *not* an input from Doc-Parser (free-text severity extraction is unreliable) and *not* supplied at the call site (Phase 4's orchestrator should not carry a parameter the Adjuster can derive itself).

Algorithm: walk severity bands in declaration order (`minor → moderate → severe`); the first band whose `max_amount` is null or ≥ reported_amount wins. A reported amount of zero or negative is a guard violation.

#### Loader module — `backend/data/market_data.py`

A small module exposing:

```python
class MarketRange(BaseModel):
    claim_type: str
    severity: Literal["minor", "moderate", "severe"]
    floor: Decimal
    ceiling: Decimal

def load_market_data(path: Path) -> MarketDataTable: ...

class MarketDataTable:
    def lookup(self, *, claim_type: str, reported_amount: Decimal) -> MarketRange: ...
```

`MarketDataTable.lookup` does sanitise → validate → abort → execute:

1. Sanitise: lowercase + strip `claim_type`.
2. Validate: `claim_type` exists in the table; `reported_amount > 0`.
3. Abort: `ValueError` with the unknown type and the list of supported types (or with the negative amount).
4. Execute: derive severity from the bands, return `MarketRange`.

The loader is cached at module level keyed on the resolved path so repeated calls do not re-parse YAML.

### 2.3 `evaluate(...)` input shapes

The Validator's shape was `(claim_id, correlation_id)` — claim_id keys a DB row, narrative is loaded internally. For Phase 3 the Doc-Parser is structurally analogous (it has no upstream agent output to consume), but Adjuster and Guardrail are *not*: they consume in-memory results from upstream agents that have no persisted form yet (the orchestrator lands in Phase 4 and adds persistence). Hence the recommendation:

- **Doc-Parser.** `evaluate(claim_id: UUID, correlation_id: UUID) -> DocParserResult`. Loads the narrative from `claims` via the connection factory, matching the Validator. Doc-Parser does not depend on any prior agent.
- **Adjuster.** `evaluate(claim_id: UUID, correlation_id: UUID, parsed_claim: DocParserOutput, validator_verdict: ValidatorVerdict) -> AdjusterResult`. Takes the upstream outputs directly. `claim_id` and `correlation_id` are required for the audit-log entry only — no DB read needed (the parsed claim already carries everything).
- **Guardrail.** `evaluate(claim_id: UUID, correlation_id: UUID, adjuster_result: AdjusterResult, retrieved_chunks: list[RetrievedChunk]) -> GuardrailResult`. Same rationale. `retrieved_chunks` is passed through so the hallucinated-citation check has the authoritative chunk set; reading them back from the audit log would couple Guardrail to the audit JSON shape.

Rationale: the Validator owns its DB read because its input is canonical persisted state (the narrative). Adjuster and Guardrail input is *derived* state that lives between agents — passing it as typed Python objects is honest about that.

### 2.4 Pydantic output models — sketch

All live under `backend/app/agents/`. One file per agent (`doc_parser_models.py`, `adjuster_models.py`, `guardrail_models.py`) to match Phase 2's `validator_models.py` and keep each agent module self-contained. All models `extra="forbid"`; all strings `min_length=1` where non-empty is required; all floats bounded; all Decimal for currency.

#### `DocParserOutput` (LLM-produced JSON shape)

```python
class DocParserOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loss_date: date                                          # ISO 8601
    jurisdiction: str = Field(min_length=1, max_length=120)
    claim_type: str = Field(min_length=1, max_length=64)     # Loose; Adjuster validates against market_data
    claimed_amount: Decimal = Field(gt=Decimal("0"))         # USD
    claimant_identifier: str = Field(min_length=1, max_length=200)
    narrative_summary: str = Field(min_length=1, max_length=500)
```

`DocParserResult` wraps it with `claim_id`, `correlation_id`, `model`, `latency_ms` (analogous to `ValidatorResult`).

#### `AdjusterOutput` (LLM-produced JSON shape)

```python
class AdjusterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommended_settlement: Decimal = Field(gt=Decimal("0"))
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, max_length=2000)
```

`AdjusterResult` wraps it with: the `MarketRange` used (`claim_type`, `severity`, `floor`, `ceiling`), `claim_id`, `correlation_id`, `model`, `latency_ms`. Cross-validation in `AdjusterResult.model_validator(mode="after")` re-checks `floor ≤ recommended_settlement ≤ ceiling` — the model's value being inside the looked-up range is the contract Phase 4 depends on, not just the prompt's instruction.

#### `GuardrailOutput` and `GuardrailFlag`

```python
GuardrailFlagKind = Literal["pii", "bias", "hallucinated_citation"]

class GuardrailFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: GuardrailFlagKind
    detail: str = Field(min_length=1, max_length=300)
    source: Literal["rule", "llm"]                           # which detector raised it

class GuardrailOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    flags: list[GuardrailFlag] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _fail_closed(self) -> GuardrailOutput:
        if self.flags and self.passed:
            raise ValueError("GuardrailOutput: flags present but passed=True (fail-closed contract violated)")
        return self
```

`GuardrailResult` wraps it with `claim_id`, `correlation_id`, `model`, `latency_ms`.

### 2.5 Audit-log payload shapes — locked at end of phase

All payloads follow the Validator's shape (`input`, agent-specific blocks, `llm_call`, `output`, `error`). Locking at end of Phase 3 — Phase 4 may read these from the audit log to reconstruct a run.

**Doc-Parser** (`agent="doc_parser"`, `step="doc_extract"`):

```json
{
  "input": {
    "claim_id": "<uuid>",
    "narrative_excerpt": "<truncated to 1000 chars>"
  },
  "llm_call": {
    "provider": "anthropic",
    "model": "<resolved model>",
    "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0
  },
  "output": {
    "loss_date": "YYYY-MM-DD",
    "jurisdiction": "...",
    "claim_type": "...",
    "claimed_amount": "85000.00",
    "claimant_identifier": "...",
    "narrative_summary": "..."
  },
  "error": null
}
```

**Adjuster** (`agent="adjuster"`, `step="settlement_estimate"`):

```json
{
  "input": {
    "claim_id": "<uuid>",
    "parsed_claim_excerpt": { ... DocParserOutput JSON ... },
    "validator_verdict_excerpt": { "covered": true, "confidence": 0.88, "policy_basis": "...", "reasoning_excerpt": "<truncated>" }
  },
  "market_data": {
    "claim_type": "fire",
    "severity": "severe",
    "floor": "500000",
    "ceiling": "1500000"
  },
  "llm_call": { ... same shape as Validator ... },
  "output": {
    "recommended_settlement": "850000",
    "confidence": 0.82,
    "reasoning_excerpt": "<truncated to 1000 chars>"
  },
  "error": null
}
```

**Guardrail** (`agent="guardrail"`, `step="output_check"`):

```json
{
  "input": {
    "claim_id": "<uuid>",
    "adjuster_output_excerpt": { ... AdjusterOutput JSON, reasoning truncated ... },
    "retrieved_chunks_summary": [{"chunk_id": "<uuid>", "section": "..."}]
  },
  "rule_checks": {
    "pii_flags": [ {"pattern": "ssn", "match_excerpt": "***"} ],
    "hallucination_flags": [ {"phrase": "Endorsement A2025-CB", "candidate_kind": "endorsement"} ]
  },
  "llm_call": { ... same shape as Validator ... },
  "output": {
    "passed": false,
    "flag_count": 1,
    "summary": "..."
  },
  "error": null
}
```

All currency Decimals serialise as JSON strings to avoid float drift in the JSONB column.

---

## 3. Per-agent design

### 3.1 Doc-Parser — `backend/app/agents/doc_parser.py`

**Persona:** structured-extraction agent for first-notice-of-loss narratives. Reads a free-text narrative, returns a typed Pydantic structure.

**Constructor:**

```python
def __init__(
    self,
    *,
    provider: LLMProvider,
    prompt_loader: PromptLoader,
    settings: Settings,
    connection_factory: Callable[[], AbstractContextManager[psycopg.Connection]] | None = None,
) -> None
```

`with_defaults(cls, settings, *, provider) -> DocParser` mirrors the Validator's wiring helper.

**`evaluate(claim_id, correlation_id) -> DocParserResult`** decomposes into:

- `_load_narrative(conn, claim_id) -> str` — identical guards to Validator's helper (claim row missing, narrative empty / non-string).
- `_build_user_prompt(narrative) -> str` — via `prompt_loader.user("doc_parser_template", claim_narrative=narrative)`.
- `_call_provider(system, user, correlation_id) -> ProviderResponse` — Anthropic, `response_format="text"` (Anthropic has no JSON mode; the system prompt enforces the format).
- `_parse_output(response_text) -> DocParserOutput` — extracts the `{...}` block (reuse `_extract_json_block` from Validator via `_shared.py`), parses, validates via Pydantic, then post-validates:
  - `loss_date` must parse as ISO 8601 (Pydantic handles this).
  - `claimed_amount` must be `> 0`.
  - `narrative_summary` length cap enforced at the model.
- `_write_audit(...)` — same shape as Validator's `_write_audit`.

**Malformed JSON / bad date handling:** Haiku has no native JSON mode, so the policy is *fail fast, no retry-rescue*. If the response contains no `{...}` block, or the block isn't valid JSON, or the JSON fails Pydantic validation, raise `ValueError` with a 500-char excerpt of the response. The retry-with-backoff enhancement is deferred to Phase 6 (consistent with the deferral already locked in Phase 2). The audit-log entry records the failure path.

**Externalised prompts:**

- `backend/app/prompts/system/doc_parser.md` — persona, the strict JSON schema, format rules (no preamble, no Markdown fencing, ISO 8601 for `loss_date`, USD numeric for `claimed_amount` as a plain decimal string with no currency symbol).
- `backend/app/prompts/user/doc_parser_template.md` — single `{claim_narrative}` placeholder.

**Defensive guards** (every guard has a triggering test asserting on message content):

- `_load_narrative`: claim missing, narrative empty / non-string.
- `_extract_json_block`: no `{...}` block.
- `_parse_output`: non-JSON, non-object JSON, schema validation failure (each Pydantic field is its own micro-guard, exercised by passing bad payloads in tests).

### 3.2 Adjuster — `backend/app/agents/adjuster.py`

**Persona:** structured settlement estimator. Looks up `(claim_type, severity)` in the market-data table; instructs Mistral to pick a value *within* the range and justify in terms of damage scope; re-validates the value is in-range.

**Constructor:**

```python
def __init__(
    self,
    *,
    provider: LLMProvider,
    prompt_loader: PromptLoader,
    market_data: MarketDataTable,
    settings: Settings,
    connection_factory: Callable[..., ...] | None = None,
) -> None
```

`with_defaults(cls, settings, *, provider)` loads `MarketDataTable` from `settings.adjuster.market_data_path`.

**`evaluate(claim_id, correlation_id, parsed_claim, validator_verdict) -> AdjusterResult`** decomposes into:

- `_lookup_market_range(parsed_claim) -> MarketRange` — calls `market_data.lookup(claim_type=..., reported_amount=...)`. Guards: claim_type unknown (lists supported types), reported amount non-positive (already enforced by Pydantic but defended again at the boundary).
- `_build_user_prompt(parsed_claim, validator_verdict, market_range) -> str` — via `prompt_loader.user("adjuster_template", ...)` with placeholders `{claim_summary}`, `{validator_verdict}`, `{claim_type}`, `{severity}`, `{range_floor}`, `{range_ceiling}`.
- `_call_provider(...)` — Mistral, `response_format="json"`.
- `_parse_output(response_text, market_range) -> AdjusterOutput` — JSON parse, Pydantic validation, then the **range-enforcement guard**: `if not (range.floor <= output.recommended_settlement <= range.ceiling): raise ValueError(...)`. Out-of-bounds is a `ValueError` — the agent does not silently clamp. Demonstrates the constraint even if the model strays.
- `_write_audit(...)` — same shape.

**Adjuster prompt does not ask the model to cite policy.** The reasoning field is constrained to discuss damage scope, severity, and market-range positioning. The Guardrail still scans for hallucinated citations because the demo scenario 3 deliberately triggers the failure mode (the seed narrative mentions "an unlisted endorsement", and an under-constrained model occasionally echoes it).

**Externalised prompts:**

- `backend/app/prompts/system/adjuster.md` — persona, the within-range constraint (strong language: "your value MUST be between floor and ceiling inclusive"), the JSON schema, format rules.
- `backend/app/prompts/user/adjuster_template.md` — placeholders listed above.

**Defensive guards:**

- `_lookup_market_range`: unknown claim_type, non-positive amount.
- `_extract_json_block`, `_parse_output` JSON / schema guards (reusing `_extract_json_block` via `_shared.py`).
- Range-enforcement guard at parse time.
- `AdjusterResult.model_validator(mode="after")` re-checks the invariant — defence-in-depth in case a future caller constructs `AdjusterResult` directly.

### 3.3 Guardrail — `backend/app/agents/guardrail.py`

**Persona:** output-safety check on the Adjuster's structured response.

**Constructor:**

```python
def __init__(
    self,
    *,
    provider: LLMProvider,
    prompt_loader: PromptLoader,
    settings: Settings,
    rule_engine: GuardrailRuleEngine | None = None,
    connection_factory: Callable[..., ...] | None = None,
) -> None
```

`rule_engine` is injectable so tests can pin the regex set without monkeypatching module globals; `with_defaults` constructs the default engine from a small Python module (regexes need to compile; not a fit for YAML).

**`evaluate(claim_id, correlation_id, adjuster_result, retrieved_chunks) -> GuardrailResult`** decomposes into:

- `_run_rule_checks(adjuster_output, retrieved_chunks) -> list[GuardrailFlag]` — deterministic regex checks (see below). Source on every flag is `"rule"`.
- `_build_user_prompt(adjuster_output, retrieved_chunks, rule_flags) -> str` — via `prompt_loader.user("guardrail_template", ...)`. The rule flags are shown to the LLM as already-detected issues so it doesn't duplicate them.
- `_call_provider(...)` — Anthropic Haiku, `response_format="text"`.
- `_parse_llm_flags(response_text) -> list[GuardrailFlag]` — JSON parse, validate, source on every flag is `"llm"`.
- `_combine_and_decide(rule_flags, llm_flags) -> GuardrailOutput` — concatenate, set `passed = len(flags) == 0` (fail-closed), build summary.
- `_write_audit(...)` — same shape.

**Rule engine — `backend/app/agents/guardrail_rules.py`** holds the explicit regex/pattern sets:

```python
# PII patterns — small, explicit, greppable. Each pattern carries the
# kind label that becomes the GuardrailFlag.detail prefix.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone_us", re.compile(r"\b\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    ("credit_card_like", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
)

# Hallucinated-citation detection. Extract phrases that look like policy
# citations from the reasoning text; flag any phrase that does not
# correspond to a retrieved chunk's section name or appear verbatim in
# any retrieved chunk's content.
_CITATION_CANDIDATE_RE = re.compile(
    r"(?P<kind>endorsement|sub-?limit|clause|provision|section|exclusion)"
    r"\s+(?P<name>[A-Z][A-Za-z0-9 \-./]{2,60})",
    re.IGNORECASE,
)

# Protected-characteristic terms. Bias check — small, explicit list.
# Conservative on purpose: this is a *floor* for the LLM check, not a
# substitute. False-positive rate matters less than false-negative rate
# in a guardrail.
_PROTECTED_TERMS: frozenset[str] = frozenset({
    "race", "ethnicity", "religion", "gender", "sexual orientation",
    "disability", "age",
})
```

`GuardrailRuleEngine.scan(adjuster_output, retrieved_chunks) -> list[GuardrailFlag]` runs each pattern set in order and returns the accumulated flags.

**Hallucinated-citation logic** (the most novel piece):

1. Apply `_CITATION_CANDIDATE_RE` to `adjuster_output.reasoning`.
2. For each candidate `(kind, name)`, build an allow-set: the section names of all retrieved chunks, plus every line of every chunk's content (normalised to lowercase, stripped). The candidate matches if `name` (lowercased) appears as a substring in any allow-set entry.
3. Unmatched candidates become a `hallucinated_citation` flag with `detail = f"{kind.lower()} {name}"`.

This catches the demo-scenario-3 failure mode (the Adjuster echoing the narrative's "unlisted endorsement") without flagging legitimate citations of sections that the chunks contain.

**Externalised prompts:**

- `backend/app/prompts/system/guardrail.md` — persona, the three check kinds explicitly enumerated, the JSON schema (a `flags` list of `{kind, detail}` objects plus a `summary` string), instructions to return `flags: []` when nothing is wrong.
- `backend/app/prompts/user/guardrail_template.md` — placeholders `{adjuster_reasoning}`, `{adjuster_settlement}`, `{retrieved_chunks}`, `{rule_flags_already_found}`.

**Defensive guards:**

- `_run_rule_checks`: empty reasoning string (Pydantic ensures non-empty upstream, but the guard belongs here for defence-in-depth), empty retrieved_chunks (callers must pass at least one chunk — anti-mistake).
- `_extract_json_block`, `_parse_llm_flags` JSON / schema guards.
- `_combine_and_decide`: defends `passed == (len(flags) == 0)` and raises if the model returned `passed=true` with non-empty flags (echoes the Pydantic model_validator at the agent level).
- `GuardrailOutput._fail_closed` model_validator (already in §2.4).

---

## 4. Testing strategy

Total target: **38 new tests** across the three agents plus the market-data loader, plus 3 opt-in real-call tests (one per agent) gated by `RUN_LLM_E2E_TESTS=1`. Backend total after Phase 3: 122 → 160 unit tests passing, 5 conditional (was 2, +3 new real-call gated).

**Per-module breakdown:**

- `test_market_data.py` (8 tests): YAML loads, lookup by each claim type, severity-band boundaries, unknown claim type guard, non-positive amount guard, missing file guard, malformed YAML guard, range-shape Pydantic validation.
- `test_doc_parser.py` (10 tests + 1 gated): happy path with mocked provider, narrative missing in DB, narrative empty / non-string, JSON-block-absent guard, non-JSON content guard, non-object JSON guard, bad-date schema guard, non-positive amount schema guard, max-length summary guard, audit-payload shape, `test_doc_parser_real_call` gated.
- `test_doc_parser_prompts.py` (2 tests): golden-shape test on the externalised system and user prompts.
- `test_adjuster.py` (10 tests + 1 gated): happy path, market lookup returns expected range for each demo amount, range-enforcement guard fires on out-of-bounds model output, unknown claim type guard, non-positive amount guard, JSON guards (3), audit-payload shape, `AdjusterResult` post-validator catches inconsistent direct construction, `test_adjuster_real_call` gated.
- `test_adjuster_prompts.py` (2 tests): golden-shape test on prompts.
- `test_guardrail.py` (10 tests + 1 gated): happy path with no flags, PII regex hits (SSN, email, phone, credit_card_like — 4 tests), hallucinated-citation hit (legit citation passes), protected-characteristic-term hit, LLM flags merge with rule flags, fail-closed invariant (passed=True with flags raises), `test_guardrail_real_call` gated.
- `test_guardrail_prompts.py` (2 tests): golden-shape test on prompts.

The conftest grows with three new fixtures: `market_data_table`, `parsed_claim_factory`, `adjuster_output_factory`. The existing `mock_provider`, `prompt_loader`, `null_api_logger`, `stub_embedder` fixtures cover the rest.

`uv run ruff check .` and `uv run mypy backend` remain clean.

---

## 5. CI changes

None. No new service containers; no new gated-by-env-var categories beyond `RUN_LLM_E2E_TESTS=1` (already exists). The new gated tests pick up the existing skip-marker pattern from `test_validator.test_validator_real_call`.

---

## 6. New dependencies

**None.** Every Phase 3 agent reuses what Phase 2 added (`anthropic`, `mistralai`, `pydantic`, `pyyaml` — `pyyaml` already pulled in for settings YAML overlay). No new runtime or dev dependency.

---

## 7. Settings additions

Per the no-hardcoded-values rule, each new agent gets per-call defaults exposed through `LLMSettings`, and the market-data path gets its own sub-model.

**`backend/settings.py` changes** — extend `LLMSettings` and add `AdjusterSettings`:

```python
class LLMSettings(BaseModel):
    # existing fields...
    doc_parser_max_tokens: int = Field(default=512, ge=1, le=8192)
    doc_parser_temperature: float = Field(default=0.0, ge=0.0, le=1.0)  # deterministic extraction
    adjuster_max_tokens: int = Field(default=768, ge=1, le=8192)
    adjuster_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    guardrail_max_tokens: int = Field(default=512, ge=1, le=8192)
    guardrail_temperature: float = Field(default=0.0, ge=0.0, le=1.0)  # deterministic-leaning

class AdjusterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_data_path: Path = Path("backend/data/market_data.yaml")

class Settings(BaseSettings):
    # existing fields...
    adjuster: AdjusterSettings = Field(default_factory=AdjusterSettings)
```

Matching blocks land in `backend/settings.yaml.template`.

No new env-var aliases. No new secrets.

---

## 8. Risks and downstream impacts

**Locked at end of Phase 3** (interface-stability surface that Phase 4 reads):

1. `DocParserOutput` JSON shape and Pydantic constraints.
2. `AdjusterOutput` JSON shape; `AdjusterResult`'s embedded `MarketRange` shape.
3. `GuardrailOutput` JSON shape; `GuardrailFlag.kind` Literal values; `GuardrailFlag.source` Literal values.
4. The three audit-log payload shapes documented in §2.5.
5. `MarketDataTable.lookup(...) -> MarketRange` typed return.
6. `market_data.yaml` top-level shape (`version`, `claim_types`, `severity_bands`, `ranges`).
7. The set of `APIAgentName` literal values (`"doc_parser"`, `"adjuster"`, `"guardrail"` are already declared in `backend/app/logging/api_logger.py` and `backend/app/audit/event.py` — Phase 3 only *uses* them; no contract change to the logger or audit-event enum).

Anything I'd later change in these surfaces becomes an interface-stability event requiring explicit re-acknowledgement before proceeding.

**Risks:**

- **Haiku JSON discipline.** Anthropic has no native JSON mode; Doc-Parser and Guardrail rely on the system prompt + strict parsing. Mitigated by `_extract_json_block` (already battle-tested in the Validator) and the gated real-call tests confirming the prompts actually produce valid JSON against the live API. Failure mode is a clean `ValueError` with a 500-char response excerpt — the audit log captures it.
- **Range-enforcement guard catching legitimate near-boundary values.** Inclusive bounds on both ends. The seed amounts ($85k, $850k, $1.4M) sit comfortably inside the ranges defined in §2.2, so the demo is not at risk. A model returning a value exactly equal to floor or ceiling is acceptable.
- **Hallucinated-citation false positives.** The candidate regex deliberately requires a citation keyword (`endorsement|sub-limit|clause|provision|section|exclusion`) followed by a Capitalised name. Adjuster's prompt is constrained not to cite policy at all, so under the happy path the candidate set is empty and the flag list is empty. False positives can only occur if a legitimate citation matches the regex but isn't in the chunk allow-set — a real risk in production, acceptable in the prototype where Guardrail's whole purpose is to err on the side of escalation.
- **Severity-band tipping points.** A claim at exactly the band boundary (`reported_amount == 50000` for water_damage) lands in `minor` per the `≤ max_amount` rule. Documented in the YAML comments; tests cover the boundary.

---

## 9. Deployment steps requiring architect involvement

Same shape as Phase 2:

- After the commit lands on `main`, Render auto-redeploys.
- No new env vars (existing `MISTRAL_API_KEY`, `ANTHROPIC_API_KEY` cover Phase 3).
- Verify `/health` returns `version=0.3.0` after the redeploy.
- Optionally run the three gated `RUN_LLM_E2E_TESTS=1` tests locally to confirm the live Haiku integration works (Doc-Parser and Guardrail) and the Adjuster's range-enforcement guard fires correctly when the model strays out of bounds.

---

## 10. Optional enhancements (clearly labelled, not built in Phase 3)

Carried forward from Phase 2's deferred list:

- Retry with exponential backoff via `tenacity` (recommended Phase 6).
- Streaming SSE through the provider interface (Phase 4 when the orchestrator wires SSE).
- Populate `LLMSettings.pricing` so `cost_usd` lights up (Phase 6 polish).
- Real PII redactor for the APILogger (Phase 7).
- Prompt golden-text fixtures as `.golden` files (Phase 6 polish).

New for Phase 3:

- **Externalise the Guardrail rule set to YAML.** The PII regexes and protected-characteristic terms could live in `backend/data/guardrail_rules.yaml`. Defer: the regexes are tightly coupled to their compilation in Python; a YAML edit without a code review would be a foot-gun.
- **Per-claim-type Adjuster prompts.** A water-damage settlement and a fire settlement involve different reasoning. Phase 3 ships one Adjuster prompt for parsimony; if the demo's reasoning quality suffers, split into `adjuster_water_damage.md`, `adjuster_fire.md`, etc. Deferred.
- **Doc-Parser confidence score per extracted field.** Useful for downstream "did the model guess?" routing. Adds prompt complexity for no Phase 3 consumer. Defer to Phase 6 if the demo would benefit.
- **Adjuster "explain the range" output field.** Show the user *why* the floor and ceiling are what they are. Trivial to add (compose a string from the market_data row) but no current consumer. Defer.

---

## 11. Files created / modified summary

**Created (13 new files):**

1. `backend/app/agents/_shared.py`
2. `backend/app/agents/doc_parser.py`
3. `backend/app/agents/doc_parser_models.py`
4. `backend/app/agents/adjuster.py`
5. `backend/app/agents/adjuster_models.py`
6. `backend/app/agents/guardrail.py`
7. `backend/app/agents/guardrail_models.py`
8. `backend/app/agents/guardrail_rules.py`
9. `backend/app/prompts/system/doc_parser.md`
10. `backend/app/prompts/user/doc_parser_template.md`
11. `backend/app/prompts/system/adjuster.md`
12. `backend/app/prompts/user/adjuster_template.md`
13. `backend/app/prompts/system/guardrail.md`
14. `backend/app/prompts/user/guardrail_template.md`
15. `backend/data/market_data.yaml`
16. `backend/data/market_data.py`
17. `backend/tests/test_market_data.py`
18. `backend/tests/test_doc_parser.py`
19. `backend/tests/test_doc_parser_prompts.py`
20. `backend/tests/test_adjuster.py`
21. `backend/tests/test_adjuster_prompts.py`
22. `backend/tests/test_guardrail.py`
23. `backend/tests/test_guardrail_prompts.py`

**Modified:**

1. `pyproject.toml` — version `0.2.0 → 0.3.0`.
2. `backend/settings.py` — extend `LLMSettings` with six per-call defaults; add `AdjusterSettings`; thread it into `Settings`.
3. `backend/settings.yaml.template` — matching blocks.
4. `backend/app/agents/__init__.py` — export `DocParser`, `Adjuster`, `Guardrail` and their result types.
5. `backend/app/agents/validator.py` — small refactor to import `_excerpt`, `_clamp_unit`, `_new_correlation_id` from `_shared.py` (no interface change).
6. `CLAUDE.md` — Current Status updated.
7. `docs/build-log.md` — new Phase 3 entry.

---

## 12. Open questions for the architect

None. Every cross-cutting decision in §2 has a recommendation; every output and audit shape is sketched; the market-data table contents are concrete. If you want anything tightened before I implement, flag it and I'll iterate.

---

**Next step.** Review this plan and reply with approval, a request for changes, or rejection. If approved, I'll append the `## Approval` footer per `docs/prompts/README.md`'s workflow and proceed to Step 3 (execute).

---

## Approval

**Approval message:** "Approved.

All cross-cutting and per-agent decisions accepted as proposed:

1. No shared base class; _shared.py helper module instead — yes.
2. backend/data/market_data.yaml with six claim_types × three severities; severity derived inside Adjuster from reported_amount — yes.
3. Doc-Parser loads narrative from DB; Adjuster and Guardrail take upstream outputs directly — yes.
4. Pydantic output models with cross-validation (AdjusterResult range check, GuardrailOutput fail-closed) — yes.
5. Three audit-log payload shapes as documented — yes.
6. Doc-Parser fail-fast JSON discipline (no retry-rescue) — yes.
7. Adjuster range-enforcement guard at parse time, ValueError on out-of-bounds (no silent clamp) — yes.
8. Guardrail three-layer design (regex rules + LLM check + fail-closed combine) — yes.
9. Hallucinated-citation logic (regex extract, chunk allow-set check) — yes.
10. Six per-call LLMSettings defaults plus AdjusterSettings — yes.
11. Preamble fix-up: pyproject.toml 0.2.0 -> 0.3.0 — yes.
12. No new deps, no CI changes — yes.

Proceed to Step 2 (record the approval footer in the plan file with verbatim approval message and ISO 8601 UTC timestamp), then execute Phase 3."

---

**Approved by:** Dermot Copps
**Approved at:** 2026-05-11T13:34:43Z

