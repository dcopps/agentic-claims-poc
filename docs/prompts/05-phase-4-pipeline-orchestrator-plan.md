# Plan 05 — Phase 4: Pipeline Orchestrator

Wire the four Phase 2/3 agents into a single end-to-end pipeline, add a typed
escalation policy engine driven by `policy.yaml`, expose a synchronous trigger
endpoint and an SSE progress-stream endpoint, and verify the three locked demo
scenarios — all under one `correlation_id` with a complete audit trail.

This plan is written against the *actual* Phase 2/3 interfaces (read in full
before drafting). Where the prompt's suggested shapes collide with the code as
built, the collision is called out under **Decisions needing confirmation** and
a concrete recommendation is made. Nothing is assumed silently.

---

## 1. Decisions needing confirmation

These five points either deviate from the prompt's suggested shape or resolve a
genuine ambiguity. Each carries a recommendation; please confirm or redirect.

### D1 — `cross_jurisdictional` has no native data signal → detect via configured markers

Every seeded claim carries a **single** `jurisdiction` string, and
`DocParserOutput.jurisdiction` is one string (e.g. `"United States — New York"`,
`"Bermuda"`). None of the three demo scenarios is cross-jurisdictional, and
there is no field that enumerates multiple jurisdictions per claim.

A delimiter heuristic is wrong here — `"United States — New York"` contains an
em-dash but is a single jurisdiction (country—region), so splitting on `—`
would misfire.

**Recommendation:** detect `cross_jurisdictional` from a configured list of
**markers** in `policy.yaml` (`cross_jurisdictional_markers`), matched
case-insensitively as substrings against the normalised parsed `jurisdiction`
string. Seed markers: `"/"`, `"multi-jurisdiction"`, `"cross-border"`. None of
the three demo claims contains a marker, so the rule stays correctly dormant in
the demo, yet it is concrete, configurable, testable (a unit test constructs a
state with `jurisdiction="Bermuda / United Kingdom"` → fires), and free of a
DSL. The detector lives in code; only the marker *data* lives in YAML.

> **Approval amendment (2026-06-14):** `" and "` was dropped from the markers at
> the architect's instruction — real single jurisdictions contain that phrase
> (Trinidad and Tobago, Antigua and Barbuda, Bosnia and Herzegovina) and would
> false-positive. Final markers: `"/"`, `"multi-jurisdiction"`, `"cross-border"`.

### D2 — escalation thresholds: `policy.yaml` is authoritative, `EscalationSettings` numeric fields are superseded

`EscalationSettings` (in `settings.py`, added Phase 1) already declares
`auto_approve_ceiling = 250000`, `validator_confidence_floor = 0.65`,
`adjuster_confidence_floor = 0.75`, `hard_rules`, and `policy_path`. The prompt
wants the thresholds to live in `policy.yaml` (matching the locked decision in
`CLAUDE.md`: *"Policy lives in `backend/app/escalation/policy.yaml`"*).

Two sources of truth for the same numbers is exactly the foot-gun the standards
warn against.

**Recommendation:**
- `policy.yaml` is the **single authoritative source** the engine loads and
  evaluates against. `EscalationSettings.policy_path` locates the file (already
  present — no new setting needed for the path).
- The numeric/threshold fields on `EscalationSettings`
  (`auto_approve_ceiling`, `validator_confidence_floor`,
  `adjuster_confidence_floor`, `hard_rules`) are **not removed** (removing them
  is an interface-stability event and other phases may read them) but are no
  longer read by the engine. Their docstring gains one line noting they are
  superseded by `policy.yaml` for rule evaluation.
- `policy.yaml` ships with values **identical** to those defaults, so there is
  no behavioural divergence in the demo.
- Optional future cleanup (labelled, not done now): collapse to one source by
  deleting the superseded fields in a later phase.

If you would rather the engine *cross-check* `policy.yaml` against
`EscalationSettings` and fail at load on divergence, say so — it's a ~10-line
guard. Default recommendation is the simpler "policy.yaml authoritative,
settings fields documented as superseded".

### D3 — orchestrator constructor: `connection_factory` not `AuditWriter`; no `APILogger`

The prompt's suggested constructor takes "the `AuditWriter`, the `APILogger`".
But `AuditWriter` is **connection-scoped** (`AuditWriter(conn).append(event)`),
and the orchestrator makes **no LLM calls** (the agents own theirs), so an
`APILogger` would be dead weight.

**Recommendation:** `PipelineOrchestrator.__init__` takes the four agent
instances, the `EscalationPolicy`, a `connection_factory` (same
`Callable[[], AbstractContextManager[psycopg.Connection]]` the agents accept),
and `Settings`. It builds `AuditWriter(conn)` per pipeline-level write, exactly
mirroring the agents. No `AuditWriter` instance and no `APILogger` in the
constructor.

### D4 — `run(...)` accepts an optional injected `correlation_id` and `emit` callback

The prompt's `run(claim_id) -> PipelineResult` plus "orchestrator generates a
fresh correlation_id at entry" (q2) collides with the SSE design (q6/q7): a
truly synchronous `POST /run` cannot be observed live by a
`GET /stream/{correlation_id}` whose id the observer only learns *from* the POST
response.

**Recommendation:** the public method becomes
`run(claim_id: UUID, *, correlation_id: UUID | None = None, emit: EventEmitter | None = None) -> PipelineResult`:
- `correlation_id=None` → generate one at entry (the prompt's default
  behaviour); if supplied, use it (lets the frontend open the SSE stream first,
  then trigger the run with the same id).
- `emit` is a plain synchronous callback `Callable[[PipelineEvent], None]`,
  defaulting to a no-op. The orchestrator stays entirely **asyncio-agnostic** —
  all asyncio (the queue, the thread-safe bridge) lives at the API edge. Tests
  pass a list-appending emitter and assert on the event sequence with zero
  async machinery.

This keeps the synchronous contract (the POST still runs to completion and
returns the full `PipelineResult`) while making the SSE stream genuinely usable.

### D5 — SSE concurrency model: blocking orchestrator runs in a threadpool; bus bridges thread→loop

The orchestrator does blocking I/O (psycopg, LLM SDKs). Calling it directly from
an async endpoint would block the event loop.

**Recommendation:** the `POST /run` async handler invokes the orchestrator via
`starlette.concurrency.run_in_threadpool`. The injected `emit` callback bridges
from the worker thread back to the asyncio `PipelineEventBus` using
`loop.call_soon_threadsafe(queue.put_nowait, event)`. The SSE handler subscribes
to the same correlation-id queue and yields. Late subscribers get **buffered**
events (queue created on first publish-or-subscribe, drained on subscribe), torn
down after the terminal event plus a short grace period. No Redis, no external
broker — in-process only, as the prompt requires.

---

## 2. Shared design questions (prompt §Step 1)

1. **Where does the orchestrator live / interface?** → `PipelineOrchestrator`
   class in `backend/app/orchestrator/pipeline.py`. Constructor per **D3**.
   Public `run(...)` per **D4**. Chosen over a module-level function for
   testability (collaborators injected, agents mocked).
2. **Correlation id management** → generated at `run` entry (or injected per
   **D4**), passed explicitly to every agent's `evaluate(...)`, and stamped on
   every orchestrator-written audit entry. **Confirmed:** all four agents'
   `evaluate(...)` already accept an injected `correlation_id` (verified in
   source) — *no agent fix-up needed*. The per-call `_new_correlation_id()`
   inside each agent's `_invoke_llm` mints a *separate* id for the API-logger
   record only, not the audit chain; that is by design and is left untouched.
3. **Agent-failure matrix** (locked):

   | Failing agent | Result status | Audit entry | Rationale |
   |---|---|---|---|
   | Doc-Parser raises | `aborted` | `pipeline_aborted` | Pipeline cannot proceed without parsed fields |
   | Validator raises | `aborted` | `pipeline_aborted` | No coverage verdict → nothing to adjust |
   | Adjuster raises | `aborted` | `pipeline_aborted` | No settlement → nothing to guard/decide |
   | Guardrail raises | `awaiting_human` | `pipeline_awaiting_human` | **Fail-closed**: a broken guardrail must never auto-approve |

   Agent exceptions are **never** silently converted to escalation. Only a
   Guardrail *throw* maps to escalation, and only because Guardrail's whole
   semantics are fail-closed. Every abort names the failing agent and the
   exception type. (A Guardrail that *returns* `passed=False` is a normal
   escalation via the `guardrail_failed` hard rule, distinct from a throw.)
4. **Escalation engine location** → `backend/app/escalation/policy.py`:
   `EscalationPolicy.load_from_yaml(path) -> EscalationPolicy` (I/O at load) and
   `EscalationPolicy.evaluate(state: PipelineState) -> EscalationDecision` (pure,
   no I/O). Loaded once at FastAPI startup (lifespan), injected, immutable for
   the request lifecycle. Schema in §4 below.
5. **`PipelineResult` / `EscalationDecision`** → sketched in §3 below.
6. **SSE event structure** → typed `PipelineEvent` union, one `event:` name per
   type, JSON `data:` payload, `correlation_id` on every event. Shapes in §7.
   No heartbeat in Phase 4 (a mocked-LLM run is sub-second; a live run is well
   under Render's timeout — documented, revisit only if a live run risks the
   proxy timeout).
7. **Two endpoints** → `POST /api/pipeline/run/{claim_id}` (synchronous; returns
   `PipelineResult`; accepts optional `correlation_id` query param per **D4**)
   and `GET /api/pipeline/stream/{correlation_id}` (SSE). In-process
   `PipelineEventBus` keyed by `correlation_id`. Recommended split chosen over
   the single-endpoint variant.
8. **Pipeline audit entries** → three additional entries under the same
   `correlation_id`, written by the orchestrator with `agent="orchestrator"`
   (the `AgentName` literal **already includes** `"orchestrator"` — no schema
   change): `pipeline_started`, `escalation_decision`, and exactly one of
   `pipeline_settled` / `pipeline_awaiting_human` / `pipeline_aborted`. Payload
   shapes in §6.

---

## 3. New typed models

All in `backend/app/orchestrator/models.py` unless noted. All
`ConfigDict(extra="forbid")`, type hints throughout. These lock at end of
Phase 4.

```python
# PipelineStatus
PipelineStatus = Literal["settled", "awaiting_human", "aborted"]

# RuleType
RuleType = Literal["hard", "threshold"]

class FiredRule(BaseModel):
    name: str                      # stable identifier, e.g. "settlement_over_ceiling"
    rule_type: RuleType
    description: str               # human-readable, e.g. "settlement > $250,000"
    observed_value: str | None = None   # the threshold field's value as a string
                                        # (Decimal/float rendered), None for hard rules

class EscalationDecision(BaseModel):
    escalate: bool
    fired_rules: list[FiredRule]   # every rule that fired, not just the first
    reasoning: str                 # deterministic summary composed from fired_rules

class PipelineState(BaseModel):
    # The orchestrator's in-memory accumulator, also the EscalationPolicy input.
    claim_id: UUID
    correlation_id: UUID
    doc_parser_output: DocParserOutput
    validator_verdict: ValidatorVerdict
    adjuster_output: AdjusterOutput
    guardrail_output: GuardrailOutput

class PipelineResult(BaseModel):
    status: PipelineStatus
    claim_id: UUID
    correlation_id: UUID
    escalation_decision: EscalationDecision | None   # None only when aborted
    doc_parser_output: DocParserOutput | None
    validator_output: ValidatorVerdict | None
    adjuster_output: AdjusterOutput | None
    guardrail_output: GuardrailOutput | None
    aborted_agent: AgentName | None = None           # set only when status == "aborted"
    error_type: str | None = None                    # exception class name, sanitised
    completed_at: datetime
```

Notes:
- On abort, the agent outputs collected *so far* are populated; the rest are
  `None`. This keeps the result inspectable (you can see how far the pipeline got).
- `error_type` carries the exception *class name* only — never the message — on
  the result object that crosses the HTTP boundary, to avoid leaking unsanitised
  detail. The full message lives in the audit `pipeline_aborted` payload (the
  audit vault is the trusted record).

---

## 4. `policy.yaml` schema and the EscalationPolicy engine

### 4.1 File: `backend/app/escalation/policy.yaml`

```yaml
version: 1

# Named lists the hard-rule detectors consult. Matched case-insensitively
# after a normalising strip (lower-cased, surrounding whitespace removed).
watchlists:
  claim_types: []          # e.g. ["aviation", "marine_war"] — empty for the demo
  claimants: []            # e.g. ["Sanctioned Entity Ltd"] — empty for the demo

# Substring markers that indicate a cross-jurisdictional claim (see D1).
# Note: " and " is deliberately NOT a marker — single jurisdictions such as
# "Trinidad and Tobago" or "Antigua and Barbuda" contain it and would
# false-positive.
cross_jurisdictional_markers:
  - "/"
  - "multi-jurisdiction"
  - "cross-border"

# Always-escalate rules. `name` must be one of the four recognised hard-rule
# names; an unknown name fails at load. `description` is human copy for the UI.
hard_rules:
  - name: guardrail_failed
    description: "Guardrail check did not pass"
  - name: claim_type_watchlist
    description: "Claim type is on the escalation watchlist"
  - name: claimant_watchlist
    description: "Claimant is on the escalation watchlist"
  - name: cross_jurisdictional
    description: "Claim spans multiple jurisdictions"

# Threshold rules. `field` selects a PipelineState accessor (fixed registry);
# `comparator` is one of > < >= <=; `value` is the boundary.
threshold_rules:
  - name: settlement_over_ceiling
    field: adjuster_settlement
    comparator: ">"
    value: "250000"
    description: "settlement > $250,000"
  - name: validator_confidence_floor
    field: validator_confidence
    comparator: "<"
    value: "0.65"
    description: "validator confidence < 0.65"
  - name: adjuster_confidence_floor
    field: adjuster_confidence
    comparator: "<"
    value: "0.75"
    description: "adjuster confidence < 0.75"
```

### 4.2 Engine: `backend/app/escalation/policy.py`

- `EscalationPolicy.load_from_yaml(path)` — defensive load (sanitise→validate→
  abort→execute): file exists / is a regular file / under a size cap / parses to
  a mapping / `version == 1` / every `hard_rules[].name` is one of the four
  **recognised** names (unknown → `ValueError` at load) / every
  `threshold_rules[].field` is a recognised field name / every `comparator` is
  one of `> < >= <=` / every `value` parses (Decimal for monetary, float for
  confidence). Internally validated through a small Pydantic `PolicyDocument`
  model so the schema guards are declarative.
- **Fixed registries, no DSL:**
  - Hard-rule detectors: `dict[str, Callable[[PipelineState, PolicyDocument], bool]]`
    keyed by the four recognised names.
  - Threshold field accessors: `dict[str, Callable[[PipelineState], Decimal | float]]`
    mapping `adjuster_settlement`, `validator_confidence`, `adjuster_confidence`.
  - Comparators: `dict[str, Callable[[X, X], bool]]` for `> < >= <=`.
- `evaluate(state)` — pure. Runs every hard rule and every threshold rule,
  collects **all** that fire into `fired_rules` (OR semantics: `escalate = any`),
  composes a deterministic `reasoning` string. No I/O.
- **Defensive guards:**
  - Monetary comparisons use `Decimal` (exact at six figures); confidence uses
    `float`. `value` strings are parsed to the right type at load.
  - **Missing/None required field on `PipelineState` → fail-closed**: treated as
    escalation with a synthetic `FiredRule(name="state_incomplete", ...)` and a
    logged gap, never a silent pass. (Guards the case where a future caller
    builds a partial state.)
  - Watchlist / marker matching normalises both sides (lower-case, strip) before
    comparing — case-insensitive per the prompt.

### 4.3 Recognised rule names (locked)

Hard: `guardrail_failed`, `claim_type_watchlist`, `claimant_watchlist`,
`cross_jurisdictional`. Threshold: `settlement_over_ceiling`,
`validator_confidence_floor`, `adjuster_confidence_floor`.

---

## 5. The orchestrator

### File: `backend/app/orchestrator/pipeline.py`

Public method reads as a sequence of named helper calls; each helper ≤30 lines.

```python
def run(self, claim_id, *, correlation_id=None, emit=None) -> PipelineResult:
    cid = correlation_id or new_correlation_id()
    emit = emit or _noop_emit
    self._emit_and_audit_started(claim_id, cid, emit)
    try:
        parsed     = self._extract(claim_id, cid, emit)        # DocParser
        verdict    = self._validate(claim_id, cid, emit)       # Validator (returns ValidatorResult)
        adjusted   = self._adjust(claim_id, cid, parsed, verdict, emit)   # Adjuster
        guarded    = self._guard(claim_id, cid, adjusted, verdict, emit)  # Guardrail
    except _GuardrailFailure as exc:
        return self._finalise_guardrail_throw(...)             # awaiting_human, fail-closed
    except _AgentFailure as exc:
        return self._finalise_abort(...)                       # aborted
    state    = self._assemble_state(...)
    decision = self._decide_escalation(state, cid, emit)       # EscalationPolicy + audit + SSE
    return self._finalise(state, decision, cid, emit)          # settled | awaiting_human + audit + SSE
```

Per-step specification:

| Helper | Input → Output | SSE events | Audit | Failure mode |
|---|---|---|---|---|
| `_emit_and_audit_started` | claim_id, cid → — | `pipeline_started` | `pipeline_started` | n/a |
| `_extract` | claim_id, cid → `DocParserOutput` | `agent_started`/`agent_completed` (doc_parser) | (agent writes `doc_extract`) | raise → `_AgentFailure("doc_parser")` → abort |
| `_validate` | claim_id, cid → `ValidatorResult` | `agent_started`/`agent_completed` (validator; summary `covered`) | (agent writes `coverage_check`) | raise → abort |
| `_adjust` | parsed, verdict → `AdjusterResult` | `agent_started`/`agent_completed` (adjuster; summary settlement) | (agent writes `settlement_estimate`) | raise → abort |
| `_guard` | adjuster_result, chunks → `GuardrailResult` | `agent_started`/`agent_completed` (guardrail; summary `passed`) | (agent writes `output_check`) | raise → `_GuardrailFailure` → `awaiting_human` |
| `_decide_escalation` | state → `EscalationDecision` | `escalation_decision` | `escalation_decision` | n/a (pure) |
| `_finalise` | state, decision → `PipelineResult` | `pipeline_completed` | `pipeline_settled` \| `pipeline_awaiting_human` | n/a |
| (abort paths) | — | `pipeline_aborted` | `pipeline_aborted` | — |

Implementation notes:
- The Validator returns a `ValidatorResult` carrying both `verdict` and
  `retrieved_chunks`. The orchestrator threads `verdict` to the Adjuster and the
  **retrieved chunks** to the Guardrail (Guardrail's `evaluate` needs
  `retrieved_chunks` — verified in source). This is the one piece of cross-agent
  data plumbing the orchestrator owns.
- Wrapping exceptions: each agent step catches the agent's `ValueError` /
  `LLMProviderError`, wraps in a small internal `_AgentFailure(agent_name, exc)`
  (or `_GuardrailFailure` for the guardrail) so the `run` body's control flow is
  a clean two-branch `except`. These are private structured exception types
  (optional-enhancement-grade, but small enough to include now — see §11).
- Status decision in `_finalise`: `awaiting_human` if `decision.escalate` else
  `settled`.
- Audit writes by the orchestrator open their own short-lived connection via
  `connection_factory` and `AuditWriter(conn).append(...)`, committing each.

### Outcome status truth table

| Guardrail | Escalation decision | Status |
|---|---|---|
| returns `passed=True` | no rules fired | `settled` |
| returns `passed=True` | ≥1 rule fired (e.g. settlement) | `awaiting_human` |
| returns `passed=False` | `guardrail_failed` fires (≥1) | `awaiting_human` |
| **throws** | (not reached) | `awaiting_human` (fail-closed) |
| any earlier agent throws | (not reached) | `aborted` |

---

## 6. Pipeline-level audit payload shapes (locked)

All written with `agent="orchestrator"`, under the run's `correlation_id`.

- **`pipeline_started`** (`step="pipeline_started"`):
  ```json
  { "claim_id": "<uuid>", "correlation_id": "<uuid>", "started_at": "<iso8601>" }
  ```
- **`escalation_decision`** (`step="escalation_decision"`):
  ```json
  { "escalate": true,
    "fired_rules": [ { "name": "...", "rule_type": "hard|threshold",
                       "description": "...", "observed_value": "..."|null } ],
    "reasoning": "..." }
  ```
- **`pipeline_settled` / `pipeline_awaiting_human`** (`step` = that name):
  ```json
  { "status": "settled|awaiting_human",
    "escalate": false,
    "fired_rule_names": ["..."],
    "settlement": "85000.00",
    "completed_at": "<iso8601>" }
  ```
- **`pipeline_aborted`** (`step="pipeline_aborted"`):
  ```json
  { "status": "aborted",
    "failing_agent": "doc_parser|validator|adjuster",
    "error_type": "ValueError|LLMProviderError",
    "error_message": "<sanitised — no secrets, truncated to 500 chars>",
    "completed_at": "<iso8601>" }
  ```
  The audit vault is the trusted record, so it *does* carry the (sanitised,
  truncated) error message — distinct from the HTTP `PipelineResult`, which
  carries only `error_type`.

---

## 7. SSE event shapes (locked)

`PipelineEvent` is a discriminated union (`event_type` field). Each is emitted
with `EventSourceResponse`, `event:` = the type name, `data:` = the JSON below.
Every payload carries `correlation_id` and `timestamp`.

| `event:` name | `data` payload |
|---|---|
| `pipeline_started` | `{ correlation_id, claim_id, timestamp }` |
| `agent_started` | `{ correlation_id, agent, timestamp }` |
| `agent_completed` | `{ correlation_id, agent, duration_ms, summary, timestamp }` |
| `escalation_decision` | `{ correlation_id, escalate, fired_rules:[{name,rule_type,description}], timestamp }` |
| `pipeline_completed` | `{ correlation_id, status, summary, timestamp }` |
| `pipeline_aborted` | `{ correlation_id, failing_agent, error_type, message (sanitised), timestamp }` |

`agent_completed.summary` is one or two fields per agent: doc_parser →
`{claim_type}`; validator → `{covered}`; adjuster → `{recommended_settlement}`;
guardrail → `{passed}`. Timestamps are injected by the API-edge emitter
(orchestrator stays clock-agnostic for testability; the emitter stamps on
publish).

---

## 8. The event bus and endpoints

### File: `backend/app/orchestrator/event_bus.py`
- `PipelineEventBus`: in-memory `dict[UUID, asyncio.Queue[PipelineEvent | _Sentinel]]`.
- `subscribe(correlation_id) -> AsyncIterator[PipelineEvent]`: gets-or-creates
  the queue, yields until the terminal sentinel.
- `publish(correlation_id, event)`: gets-or-creates the queue, `put_nowait`.
  Thread-safe entry point `publish_threadsafe(loop, correlation_id, event)` uses
  `loop.call_soon_threadsafe` for calls originating in the orchestrator's worker
  thread.
- Terminal handling: on `pipeline_completed` / `pipeline_aborted`, enqueue a
  sentinel; the subscriber stops; the queue is dropped after a small grace
  period (`PipelineSettings.event_grace_period_s`). Late subscribers receive
  **buffered** events (documented choice).

### File: `backend/app/api/pipeline.py`
- `POST /api/pipeline/run/{claim_id}` — async handler. Resolves the orchestrator
  + bus from app state (lifespan-built). Optional `correlation_id` query param
  (per **D4**). Builds a thread-safe emitter bound to the running loop + bus,
  runs `orchestrator.run(...)` via `run_in_threadpool`, returns `PipelineResult`
  as JSON. Guards: unknown `claim_id` → `404` (the orchestrator's first agent
  raises a "claim not found" `ValueError`; the handler maps abort-on-doc-parser
  with a not-found message to 404, other aborts to a `200` with
  `status="aborted"` body — see note). Malformed UUID → `422` (FastAPI path
  validation).
- `GET /api/pipeline/stream/{correlation_id}` — async handler returning
  `EventSourceResponse(bus.subscribe(correlation_id))`.

Endpoint status-code policy (interface contract):
- A successful pipeline run — including one that ends `awaiting_human` or
  `aborted` (agent failure mid-run) — returns **HTTP 200** with the typed
  `PipelineResult` body. `aborted` is a *pipeline outcome*, not an HTTP error.
- Only *request-level* failures use 4xx: unknown `claim_id` not present in the
  `claims` table → **404**; malformed path UUID → **422**.

> Open sub-decision: whether "claim not found" should be a pre-flight 404 (a
> cheap `SELECT 1 FROM claims` in the handler before running) or allowed to
> surface as a doc-parser abort. **Recommendation:** pre-flight check → clean
> 404, so a genuinely missing claim never writes a `pipeline_started` +
> `pipeline_aborted` pair to the audit log for what is really a bad request.
> Confirm.

### Wiring: `backend/app/main.py` lifespan
- Add a FastAPI `lifespan` that, on startup, builds the four agents (via their
  `with_defaults(settings, provider=get_provider(...))`), loads the
  `EscalationPolicy` from `settings.escalation.policy_path`, constructs the
  `PipelineOrchestrator` and the `PipelineEventBus`, and stashes them on
  `app.state`. The pipeline router reads them from `app.state`. `create_app`
  gains the lifespan; existing health/router wiring unchanged.
- **Test posture:** the lifespan builds real providers, which require API keys.
  Unit/integration tests do **not** exercise the lifespan-built graph; they
  construct `PipelineOrchestrator` directly with mocked agents (mirroring the
  Phase 2/3 posture). The API tests that need the endpoints use a dependency
  override / app-state injection to insert a stub orchestrator, so no real keys
  or network are touched in CI. (One opt-in gated real-call test exercises the
  live graph.)

---

## 9. Settings additions

New `PipelineSettings` sub-model (added to `settings.py` **and**
`settings.yaml.template`, per the settings standard), hung off `Settings` as
`pipeline`:

```python
class PipelineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_grace_period_s: float = Field(default=5.0, ge=0.0, le=120.0)
    event_queue_maxsize: int = Field(default=1000, ge=1)   # backpressure bound
```

No other new settings — `escalation.policy_path` already exists and locates
`policy.yaml`. No hardcoded values: the grace period and queue bound are named
fields with documented defaults; the threshold constants live in `policy.yaml`.

---

## 10. Files created / modified

**Created**
- `backend/app/orchestrator/__init__.py` — exports.
- `backend/app/orchestrator/models.py` — `PipelineStatus`, `RuleType`,
  `FiredRule`, `EscalationDecision`, `PipelineState`, `PipelineResult`,
  `PipelineEvent` union + per-event models, `EventEmitter` type alias.
- `backend/app/orchestrator/pipeline.py` — `PipelineOrchestrator`.
- `backend/app/orchestrator/event_bus.py` — `PipelineEventBus`.
- `backend/app/escalation/policy.py` — `EscalationPolicy`, `PolicyDocument`.
- `backend/app/escalation/policy.yaml` — the locked rules.
- `backend/app/api/pipeline.py` — the two endpoints.
- Tests: `backend/tests/test_escalation_policy.py`,
  `test_pipeline_orchestrator.py`, `test_pipeline_event_bus.py`,
  `test_pipeline_scenarios.py` (3 integration + 1 gated),
  `test_api_pipeline.py`.

**Modified**
- `backend/app/main.py` — add `lifespan`, mount pipeline router.
- `backend/app/api/__init__.py` — include the pipeline sub-router.
- `backend/settings.py` — add `PipelineSettings`; one-line docstring note on the
  superseded `EscalationSettings` threshold fields (per **D2**).
- `backend/settings.yaml.template` — add the `pipeline:` block.
- `backend/app/escalation/__init__.py` — export `EscalationPolicy` etc.
- `pyproject.toml` — `0.3.0 → 0.4.0`; add `sse-starlette` dependency.
- `CLAUDE.md` — Current Status (Step 6).
- `docs/build-log.md`, `docs/prompts/05-...-report.md` — Steps 4/5.

---

## 11. Testing strategy (target ~40–48 new tests)

- **`EscalationPolicy`** (~16): each of 4 hard rules fires; each threshold fires
  at the boundary (`>250000` does/doesn't at exactly 250000; `<0.65`/`<0.75`
  boundaries); OR-combination (multiple fire → all captured); case-insensitive
  watchlist + marker matching; load guards each with a triggering test asserting
  on message content (missing file, non-mapping, bad version, unknown hard-rule
  name, unknown threshold field, bad comparator, unparseable value);
  missing-field fail-closed guard.
- **`PipelineOrchestrator`** (~10): happy path (all agents mocked, settle);
  threshold-escalation path; guardrail-returns-fail path; each abort case
  (doc_parser / validator / adjuster throw → `aborted` naming the agent);
  guardrail-throw → `awaiting_human` (fail-closed); correlation_id threaded to
  every agent; emit sequence correct; pipeline-level audit entries written.
- **`PipelineEventBus`** (~6): subscribe→publish→receive; late subscriber gets
  buffered events; terminal sentinel ends iteration; cleanup after grace;
  thread-safe publish; queue-maxsize backpressure guard.
- **Integration `test_pipeline_scenarios.py`** (3 + 1 gated): the three locked
  scenarios end-to-end against seeded claims with the LLM mocked at the
  `LLMProvider` boundary — (1) $85k water → `settled`, no fired rules, full audit
  trail; (2) $850k fire → `awaiting_human`, `settlement_over_ceiling` fired,
  guardrail passed; (3) $1.4M storm with Adjuster output mocked to embed a
  hallucinated endorsement → Guardrail `passed=False`, `awaiting_human`,
  `guardrail_failed` fired regardless of thresholds. Plus one
  `RUN_LLM_E2E_TESTS=1`-gated real-call auto-approve run.
- **API `test_api_pipeline.py`** (~6): `POST /run` happy path (stub orchestrator
  via app-state override) returns typed `PipelineResult`; unknown claim_id →
  404; malformed UUID → 422; `awaiting_human` body shape; SSE endpoint yields
  the event sequence for a correlation_id; SSE on an unknown correlation_id
  behaves (empty/closes cleanly — documented).

Every guard clause gets a triggering test asserting on **message content**, not
just exception type (global standard). Running total updated in the report
(~180 → ~225).

---

## 12. New dependencies

**One:** `sse-starlette` (already a locked dependency in `CLAUDE.md`'s tech
stack, but not yet in `pyproject.toml`). Provides `EventSourceResponse`.
Justification: SSE transport is the locked streaming decision; hand-rolling SSE
framing (event/id/retry, keep-alive, disconnect handling) would be strictly
worse than the maintained library the architecture already names. No other new
dependencies — `run_in_threadpool` and `asyncio.Queue` are stdlib/Starlette
already present.

---

## 13. Risks, downstream impacts, locked interfaces

**Locked at end of Phase 4** (Phases 5–7 consume these; any change is an
interface-stability event):
1. `PipelineResult`, `EscalationDecision`, `FiredRule`, `PipelineState`,
   `PipelineStatus` shapes.
2. The six SSE event names and their `data` payloads (§7).
3. `POST /api/pipeline/run/{claim_id}` (optional `correlation_id` query) and
   `GET /api/pipeline/stream/{correlation_id}` — paths, methods, status-code
   policy.
4. The four pipeline-level audit `step` identifiers and their payloads (§6).
5. `policy.yaml` schema (`version`, `watchlists`, `cross_jurisdictional_markers`,
   `hard_rules`, `threshold_rules`) and the seven recognised rule names.

**Flagged risks / prototype simplifications:**
- `PipelineEventBus` is in-process. Phase 5 may replace it with a real bus
  (Service Bus in production; in-process for the prototype). The SSE endpoint's
  coupling to in-process subscribers is a deliberate prototype simplification.
- Late-subscriber semantics are "buffered, best-effort" — fine for a
  single-process demo, not a delivery guarantee.
- The orchestrator opens a fresh connection per pipeline-level audit write
  (mirrors the agents). Connection-pool pressure is a non-issue at demo scale;
  noted for production.

---

## 14. Optional enhancements (labelled; not built unless you say so)

Carried forward (deferred): retry via `tenacity`; pricing-table population for
`cost_usd`; real PII redactor; prompt golden-text fixtures.

New for Phase 4:
- **Per-agent timeout** in the orchestrator (wrap each `evaluate` in a deadline)
  — guards a hung provider; deferred because each provider already takes
  `request_timeout_s`.
- **Idempotent re-run protection** on `POST /run` (reject a second run for a
  claim already `settled`) — deferred; needs a claim-status column write that is
  arguably Phase 5 decoupling territory.
- **Structured pipeline-abort exception hierarchy** as a public module (vs the
  private `_AgentFailure`/`_GuardrailFailure` used internally now) — promote if
  Phase 5 needs to catch them across the event boundary.
- **SSE heartbeat** — add only if a live run risks exceeding Render's proxy
  timeout (it should not at current latencies).

---

## 15. Execution order (once approved)

1. `pyproject.toml`: version bump + `sse-starlette`; `uv lock`.
2. `policy.yaml` + `EscalationPolicy` + its tests.
3. orchestrator `models.py`, `event_bus.py` + bus tests.
4. `PipelineOrchestrator` + orchestrator unit tests.
5. `PipelineSettings` (settings.py + template).
6. API `pipeline.py` + `main.py` lifespan + API tests.
7. Integration scenario tests.
8. `ruff` + `mypy` + full `pytest`; fix to green.
9. Build-log entry, report, `CLAUDE.md` status, single commit, push.

---

**Verdict requested.** Please review — particularly the five **Decisions
needing confirmation** in §1 (cross-jurisdictional markers, policy.yaml as the
single source of truth, the orchestrator constructor deviation, the injected
`correlation_id`/`emit`, and the threadpool/bus SSE model) and the §8 "claim not
found → pre-flight 404" sub-decision. On approval I will record the `## Approval`
footer and proceed to Step 3.

---

## Approval

**Approval message:** "Approved, with one change: drop \" and \" from cross_jurisdictional_markers in policy.yaml. Real single jurisdictions contain that phrase (Trinidad and Tobago, Antigua and Barbuda, etc.) and would false-positive. Keep \"/\", \"multi-jurisdiction\", \"cross-border\". Then append the ## Approval footer and proceed to Step 3."

**Amendment applied:** `" and "` removed from `cross_jurisdictional_markers` in §1 (D1) and §4.1. Final markers: `"/"`, `"multi-jurisdiction"`, `"cross-border"`. All other decisions (D2–D5 and the §8 pre-flight-404 sub-decision) approved as written.

---

**Approved by:** Dermot Copps
**Approved at:** 2026-06-14T14:00:04Z
