> *Plain-language summary of this phase: see [the build story](README.md#entry-24), entry 24.*

# Phase 10 — Plan: an MCP server over the audit trail, and an Integrations page that shows it working

**Prompt:** `24-phase-10-mcp-server-and-integrations-page.md`. **Version:** `0.9.1.2 → 0.10.0`. **Status:** approved 2 November 2026 (see *Approval*); execution in progress.

Inputs read before planning: the prompt; `docs/BACKLOG.md` (*An MCP server in front of the prototype's API*, *In-UI "How it works" info page*); `backend/app/main.py`, `api/__init__.py`, `api/pipeline.py`, `api/claims.py`, `api/runs.py`, `api/audit.py`, `api/human.py`, `api/agents_test.py`; `orchestrator/event_bus.py`, `orchestrator/models.py`; `audit/verify.py`, `runs/repository.py`, `claims/models.py`; `backend/settings.py`, `settings.yaml.template`; `backend/db/migrations/`; `backend/data/seed_claims.py`; `prompts/loader.py`; `logging/api_logger.py`; `pyproject.toml`, `uv.lock`, `Dockerfile`, `render.yaml`; `backend/tests/conftest.py` and the API tests; `infra/bicep/main.bicep`, `main.bicepparam`, `modules/keyvault.bicep`, `modules/containerapps.bicep`, `scripts/azure-deploy.sh`; the whole of `frontend/src/`; the MCP Python SDK documentation for the 2.x line (`py.sdk.modelcontextprotocol.io`: *run*, *deploy*, *authorization*, *servers/tools*, *prompts*, *resources*, *client*), the `mcp` PyPI page and release feed, and Anthropic's help article *Get started with custom connectors using remote MCP* plus the *authenticate with request headers* reference. Three checks were run locally and one against the Render deployment; their results are in §0.

---

## 0. Findings that shape the plan

1. **The SDK is `mcp` 2.3.0, stable, released 2 October 2026.** The 2.x line is the current stable line (2.0.0 on 28 July 2026; 1.30.0 on 7 September is the maintenance line). Python `>=3.10`. The server class is `MCPServer` (`from mcp.server import MCPServer`); transport options are keyword arguments of `streamable_http_app()`, whose signature on 2.3.0 is `(*, streamable_http_path='/mcp', json_response=False, stateless_http=False, event_store=None, retry_interval=None, max_request_body_size=4 MiB, session_idle_timeout=1800, max_sessions=10000, transport_security=None, host='127.0.0.1') -> Starlette`. **Checked locally:** `mcp==2.3.0` resolves in an isolated environment beside this project's exact pins (`fastapi 0.136.1`, `starlette 1.0.0`, `pydantic 2.13.4`, `sse-starlette 3.4.4`), so no existing lock entry has to move. See §1 for what it adds.
2. **The host application's lifespan must run the MCP session manager.** The SDK documents this as "the line everyone forgets": a mounted sub-application's lifespan never runs, so `_lifespan` in `main.py` enters `mcp.session_manager.run()` when, and only when, the endpoint is mounted. Without it the first request fails with `RuntimeError: Task group is not initialized`.
3. **Mounting at `/mcp` the obvious way produces a redirect.** `app.mount("/mcp", …)` answers `GET /mcp` with `307 → /mcp/`; behind the Render and Azure TLS terminators that redirect is emitted as `http://` unless uvicorn trusts the forwarded headers, and the MCP client refuses an HTTPS→HTTP redirect by design. **Checked locally:** registering the MCP Starlette app as an exact route — `app.add_route("/mcp", guarded_app, methods=[…])` with `streamable_http_app(streamable_http_path="/mcp")` — delivers `/mcp` to the inner app unchanged, no redirect, no proxy-header dependency. That is the form in §2; `Dockerfile` and `render.yaml` are untouched.
4. **The SDK's DNS-rebinding protection rejects every public hostname by default** (421 *Invalid Host header* unless `Host` is `localhost`/`127.0.0.1`). Both deployments sit behind an ingress that owns the `Host` header, and the bearer token is the access control, so the plan disables the host allowlist for this endpoint (`TransportSecuritySettings(enable_dns_rebinding_protection=False)`), with the per-deployment allowlist as the alternative (§2, decision D3).
5. **The SDK's authentication is OAuth-shaped.** `token_verifier=` and `auth=AuthSettings(issuer_url=…, resource_server_url=…)` travel together; the server then publishes RFC 9728 protected-resource metadata and answers 401 with a `resource_metadata` pointer. Claude's connector flow "detects authentication settings" from exactly those signals, and we have no authorization server to point at. A static shared token is therefore checked by a small ASGI guard of our own in front of the MCP app, not by the SDK's verifier (§2).
6. **How Claude reaches the server.** Custom connectors (claude.ai, Claude Desktop, Cowork) connect **from Anthropic's cloud, not from the laptop**, so the endpoint must be public — both deployments are. A fixed credential is entered under *Request headers* (`authorization` = `Bearer <token>`, with *No sign-in*). That field is documented as **beta and limited to some organisations**; the fallbacks are Claude Code (`claude mcp add-json … {"type":"http","url":…,"headers":{"Authorization":"Bearer …"}}`) and the third-party `mcp-remote` bridge in `claude_desktop_config.json`. The connection panel and the demo script carry the connector steps first and the Claude Code command second (decision D4).
7. **The pipeline event bus is single-reader and has no replay.** `PipelineEventBus` holds one `asyncio.Queue` per correlation id; a second subscriber steals events from the first, consumed events are gone, and there are no event ids. The activity feed is a broadcast with replay, so it gets its own small bus (`ActivityBus`, per-subscriber queues, no terminal sentinel) rather than a reserved channel on the pipeline bus (§5).
8. **There is no service layer to call.** The routers' helpers (`_list`, `_get`, `_get_run`, `_compare`, `_list_entries`, `_verify`, `_execute`) are private, two of them hold inline SQL, and `get_orchestrator_factory` needs a `Request`. The prompt's rule — "call the same service functions the routers call, not HTTP to self" — is met by three small promotions, each leaving every HTTP shape byte-identical: the audit-entry SQL moves from `api/audit.py` into `AuditRepository.list_entries(conn, cid)`; the orchestrator-factory closure moves out of the dependency into `make_orchestrator_factory(app)` with the dependency delegating to it; and the prompt lookup in `api/agents_test.py` becomes `load_agent_prompts(agent, variant, registry)`. The tools and the routers then share one function each.
9. **Two tool fields have no existing source.** Nothing counts runs per claim (`list_claims` gains one grouped query, `RunsRepository.count_runs_by_claim`), and nothing records per-agent wall time in the audit; `get_run` reports each agent row's `created_at` and its `llm_call.latency_ms`, which is what the record holds, and says so.
10. **Chain verification is whole-ledger.** `verify_chain(conn)` walks the entire table; the correlation id on the existing endpoint only drives the 404. The tool keeps the name the prompt gives it and returns `scope: "whole_ledger"` with the run's own row count beside the ledger total, so the answer never implies a per-run proof that was not made.
11. **The worked example in the prompt mixes two runs.** On the Render audit (read on 2 November 2026), `0cdfa114` is the Harborline run that settled at $82,500 and its refused claim is *"inventory valuation and depreciation"*; *"the $1.5M ceiling"* is the refused claim of the Northwood run `6197d116` (`awaiting_human`, `settlement_over_ceiling`, $920,000). §3 shows `0cdfa114` from its real rows and notes the other.
12. **The demo's `compare_runs` needs two runs of the same claim** (`RunClaimMismatchError` → 400 otherwise). Render has the pair the demo wants, on the Harborline claim `08454ce5`: `2c42cf40` (`awaiting_human`, the morning of 30 October under `0.9.1.1`) and `0cdfa114` (`settled`, the afternoon of 30 October under `0.9.1.2`). The prompt's "26 October escalation" is on Azure and on a different claim from the 30 October runs (each verification pass submits fresh claims), so it cannot be compared; the demo script uses the Render pair and the Azure pass checks whether an Azure pair exists (§8, decision D6).
13. **The three scripted scenarios are defined in three places** (`backend/data/seed_claims.py`, `scripts/verify-demo-scenarios.py`, `frontend/src/fixtures/demoClaims.ts`). `run_scenario` uses the backend's copy — `seed_claims._build_scripted_claims()` made public — and builds a `ClaimSubmission` from it; `claim_number` is assigned by `ClaimsRepository.insert`, so every call creates a fresh claim, as the verification script does. The other two copies are untouched (optional O3).
14. **`PromptLoader` knows two kinds, `system` and `user`.** The two MCP prompt templates are user-message templates, so they live in `backend/app/prompts/user/` as `mcp_audit_this_run.md` and `mcp_why_settled_or_escalated.md`; no loader change.
15. **`llm_flags_discarded` is not shown on the Run Detail page today.** The Guardrail card renders `payload.output`, and the refused claims are top-level keys beside it; they are visible only in the Audit page's `output_check` row JSON. The Guide says exactly that, and `explain_decision` is where they appear structured (optional O2 would add a line to the card).
16. **Smaller facts the execution depends on.** `APICallRecord.agent` is a closed literal without `mcp`, so the tool-call record is its own model, not a reuse. The `client` fixture builds `TestClient(create_app())` without entering the lifespan; the MCP tests use `with TestClient(app) as c` so the session manager runs. The existing Run Detail test matches `getByRole('button', { name: /copy/i })`, which the new button would also match; it is tightened to the exact name. `Badge` has no amber tone; the *action* badge adds one. `/health` reads the version from `pyproject.toml`; nothing else carries it.

---

## 1. Dependency — flagged per the standing rule

**One new direct dependency: `mcp>=2.3,<3`** (locked at 2.3.0). The existing stack cannot cover it: the Model Context Protocol's JSON-RPC framing, the streamable-HTTP session manager, the capability negotiation and the tool/prompt/resource schemas are the protocol, and the client being demonstrated (Claude's connector) speaks exactly that. Writing it by hand is not a serious option. No `cli` or `rich` extra; the server runs inside FastAPI and nothing uses the `mcp` command.

**What it brings into `uv.lock`** (from the package's own metadata, checked on 2.3.0): `mcp-types==2.3.0`, `httpx2>=2.10.0` (the SDK's HTTP client — a separate package from `httpx`, which stays in the dev group), `jsonschema>=4.20` (with `referencing`, `rpds-py`, `jsonschema-specifications`), `pyjwt[crypto]>=2.10.1`, `python-multipart>=0.0.9`, plus `anyio`, `opentelemetry-api`, `pydantic>=2.12`, `sse-starlette>=3.0`, `starlette`, `typing-extensions`, `typing-inspection`, `uvicorn` which are already present. **No existing locked version has to change** (confirmed by resolving 2.3.0 against the exact pins). The `uv add` output and the lock diff are recorded in the report, and any surprise in it is raised before the commit, as in Phase 9.2.

**No further dependency.** The end-to-end test uses the `mcp` client (`from mcp import Client`, `mcp.client.streamable_http.streamable_http_client`) with an `httpx2.AsyncClient` carrying the bearer header; `pytest-asyncio` is not added — the suite's existing `asyncio.run(...)` pattern is kept. The frontend adds nothing (`EventSource`, `fetch`, clipboard and TanStack Query are already there). The `mcp-remote` bridge is a client-side tool a user may run; it is named in the docs and never installed by this repository.

---

## 2. Mounting and auth

### 2a. Settings — `backend/settings.py` and `settings.yaml.template`

```python
class MCPSettings(BaseModel):
    """The MCP endpoint. Unset `shared_token` means the endpoint does not exist."""
    model_config = ConfigDict(extra="forbid")
    shared_token: SecretStr | None = None   # MCP__SHARED_TOKEN; "" is treated as unset
    token_label: str = "shared-token"       # recorded as the caller; never the value
    activity_replay_count: int = Field(default=20, ge=0, le=500)  # records sent on feed connect
```

`Settings` gains `mcp: MCPSettings = Field(default_factory=MCPSettings)`. `MCP__SHARED_TOKEN` works through the existing `env_nested_delimiter`; no alias. The template gains an `mcp:` block in the same commented style (`# shared_token: loaded from MCP__SHARED_TOKEN — do not put values here`). A whitespace-only or empty token is normalised to unset before the mount decision (sanitise → validate → abort → execute).

### 2b. Construction — `backend/app/mcp/server.py` and `main.py`

- `build_mcp_server(app: fastapi.FastAPI) -> MCPServer` registers the nine tools, two prompts and one resource as closures over `app` (settings, event bus and the orchestrator factory are read from `app.state` at call time, so a test can inject a stub factory the same way the API tests do). `MCPServer(name=cfg.app_name, version=<package version>, instructions=<two sentences on what the server is and is not for>)`.
- The server object is **always built** in `create_app` and stored as `app.state.mcp_server`, because `/api/mcp/tools` lists its definitions whether or not the endpoint is mounted.
- The endpoint is **mounted only when the token is set**:

```python
asgi = mcp.streamable_http_app(
    streamable_http_path=MCP_PATH,          # "/mcp", a module constant
    stateless_http=True,                    # see note
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
app.add_route(MCP_PATH, BearerGuard(asgi, expected=cfg.mcp.shared_token), methods=["GET", "POST", "DELETE"])
```

  `stateless_http=True` because no tool uses the server-to-client back-channel (no elicitation, sampling or progress) and a stateless server survives a scale-to-zero restart or a second replica without sticky sessions; the SDK notes the flag only affects pre-2026 clients. `app.state.mcp_mounted: bool` records the decision for the catalogue endpoint.
- `_lifespan` enters `async with app.state.mcp_server.session_manager.run():` around its `yield` only when mounted (finding 2).

### 2c. The bearer guard — `backend/app/mcp/auth.py`

A ~30-line ASGI callable. For every `http` scope it reads `Authorization`, requires the `Bearer ` scheme, compares the token with `hmac.compare_digest` against the configured secret, and on any failure answers `401` with `WWW-Authenticate: Bearer realm="agentic-claims-mcp"` and a one-line JSON body (`{"detail": "missing or invalid bearer token"}`), never echoing what was received. Non-`http` scopes (lifespan, websocket) are refused with 404 rather than passed through. Nothing reaches the MCP app unauthenticated, so the SDK's own auth is left unset (finding 5). The caller identity available to the log is the token's label from settings.

### 2d. Behaviour when the token is unset

- `/mcp` is **not registered** — a request gets FastAPI's ordinary 404, indistinguishable from any unknown path. There is no anonymous mode and no flag to create one.
- `GET /api/mcp/tools` still answers, with `mounted: false`, so the Integrations page can say the endpoint is not configured on this deployment and still show what it would offer.
- `GET /api/mcp/activity` still answers (an empty replay, then silence), so the page's feed component needs no special case beyond the `mounted` flag.
- Startup logs one INFO line either way (`mcp endpoint mounted at /mcp` / `mcp endpoint not mounted: MCP__SHARED_TOKEN unset`).

### 2e. Production access path (documented, not built)

The architecture reference and the Integrations page's explanation state that in production the endpoint sits behind Azure API Management with Entra sign-in, as the production diagram already shows; the shared token is the prototype's stand-in for that, held in Key Vault on Azure and in the Render dashboard.

---

## 3. Tool implementations — `backend/app/mcp/tools.py`, `explain.py`, `scenarios.py`

### 3a. Common mechanics

- Each tool is an `async def` registered with `@mcp.tool(title=…, annotations=ToolAnnotations(read_only_hint=True|False, …))`. Name from the function, description from the docstring (plain language, one paragraph — it is also the catalogue's one-liner), parameter schema from the type hints, output schema from the Pydantic return type.
- Blocking work (every database call, the pipeline) runs through `run_in_threadpool`, exactly as the routers do.
- **Every tool body is wrapped by `logged_tool(recorder)`**, which measures latency, derives the target from the arguments, and records one `ToolCallRecord` on every exit path: `ok`, a structured refusal, or an unexpected exception. Unknown ids raise the SDK's `ToolError` with a `not_found: run 0cdfa114-…` message, which the client receives as an `is_error` result, never a stack trace. Any other exception is logged with its class, recorded as `outcome: error`, and re-raised as `ToolError("internal_error: <ClassName>")` with no detail from the traceback.
- Arguments recorded are the tool's parameters as received (ids, a status, a flag, a scenario name). No tool takes free text, so nothing personal or secret can enter the log through arguments.

### 3b. The tools

| Tool | Parameters | Returns (Pydantic model) | Calls (after §0.8) |
|---|---|---|---|
| `list_claims` | `status: ClaimStatus \| None = None` | `ClaimListing{claims: [{claim_id, claim_number, claimant_name, claim_type, reported_amount, status, scenario_tag, run_count}]}` | `ClaimsRepository.list_claims(conn, limit=CLAIMS_LIST_LIMIT, status=)` (the router's default `50`, extracted to one shared constant) + `RunsRepository.count_runs_by_claim(conn, claim_ids)` (new, one `GROUP BY` over `pipeline_started` rows) |
| `get_claim` | `claim_id: UUID` | `ClaimView{claim: ClaimRecord, runs: list[RunSummary]}` | `ClaimsRepository.get`, `RunsRepository.list_runs_for_claim` |
| `get_run` | `correlation_id: UUID` | `RunView{result: PipelineResult, agents: [{agent, step, audit_id, recorded_at, model_latency_ms, provider, model, demo_fixture}]}` | `RunsRepository.get_run` + `AuditRepository.list_entries` (for the per-agent rows) |
| `explain_decision` | `correlation_id: UUID` | `DecisionExplanation` — §3c | `AuditRepository.list_entries`, `verify_chain`, `ClaimsRepository.get`; composed by the pure function `compose_explanation(claim, entries, verification)` |
| `get_audit_trail` | `correlation_id: UUID`, `include_prompts: bool = False` | `AuditTrail{correlation_id, prompts_included, entries: list[AuditEntryView]}` | `AuditRepository.list_entries`; when `include_prompts` is false the pure `strip_prompts(payload)` removes `llm_call.prompt` from each entry and the description says the stripped payload will not re-hash to `row_hash` |
| `verify_chain` | `correlation_id: UUID` | `ChainVerificationReport{scope: "whole_ledger", ok, rows_checked, first_break, run_rows}` | existence check via `AuditRepository.list_entries`, then `audit.verify.verify_chain(conn)` |
| `compare_runs` | `correlation_id_a: UUID`, `correlation_id_b: UUID` | `RunComparison` (existing) | `RunsRepository.compare`; `RunClaimMismatchError` → `ToolError("runs belong to different claims: …")` |
| `get_agent_instructions` | `agent: Literal["doc_parser","validator","adjuster","guardrail"]` | `AgentPromptView` (existing: `agent, variant, system, user`) for `variant="default"` | `load_agent_prompts(agent, "default", registry)` |
| `run_scenario` | `name: Literal["harborline","northwood","coral_bay"]` | `ScenarioRun{scenario, claim_id, correlation_id, status, fired_rule_names, settlement}` | `scenarios.submission_for(name)` → `ClaimsRepository.insert`; then the same `_execute(factory("default"), claim_id, uuid4(), "default", bus)` the router uses, so the run streams to the Run page like any other |

`run_scenario` is the only tool with `read_only_hint=False` (`destructive_hint=False`, `idempotent_hint=False`, `open_world_hint=False`). It refuses any other name at the schema (the `Literal` is the input schema) and again in code (`ValueError` → `ToolError`) so a client that ignores the schema still cannot name an arbitrary claim. It runs the pipeline synchronously and returns the terminal result with the correlation id — about 45 seconds on Render for Harborline (`0cdfa114`: 17:29:55 → 17:30:41). If the connector's tool timeout proves shorter than that in the deployed pass, the fallback is a one-function change: start the run in a task and return the correlation id immediately, with the description telling the client to poll `get_run` (decision D5).

**Not exposed, by design:** the human approve/reject endpoint, the agent test bench, replay with variants, any raw SQL, and any mutation of a claim other than the three scripted submissions.

### 3c. `explain_decision` — the output shape in full

Composed only from the audit rows and the chain check; every statement carries the row it came from. `source` is always `{audit_id, agent, step, recorded_at, chain_hash}`.

```json
{
  "correlation_id": "…", "claim_id": "…", "claim_number": "…", "claimant_name": "…",
  "variant": "default", "started_at": "…", "completed_at": "…",
  "outcome": { "status": "settled | awaiting_human | aborted", "settlement": "82500.00 | null",
               "fired_rule_names": [], "source": {…} },
  "coverage": { "covered": true, "confidence": 0.92, "policy_basis": "…", "reasoning": "…",
                "passages_seen": [ { "chunk_id": "…", "section": "…", "similarity": 0.598 } ],
                "passages_cited": [ { "chunk_id": "…", "section": "…" } ], "source": {…} } ,
  "settlement": { "recommended": "82500.00", "confidence": 0.85,
                  "range": { "claim_type": "water_damage", "severity": "moderate", "floor": "50000", "ceiling": "200000" },
                  "reasoning": "…", "demo_fixture": false, "source": {…} },
  "guardrail": { "passed": true, "summary": "…",
                 "rule_engine_flags": [ { "kind": "…", "detail": "…", "source": "rule_engine" } ],
                 "llm_flags_counted":   [ { "kind": "…", "detail": "…", "quote": "…" } ],
                 "llm_flags_discarded": [ { "kind": "…", "detail": "…", "quote": "…", "reason": "quote_not_a_provision" } ],
                 "llm_verification_recorded": true, "source": {…} },
  "escalation": { "escalate": false, "reasoning": "…",
                  "fired_rules": [ { "name": "…", "rule_type": "hard | threshold", "description": "…", "observed_value": "…" } ],
                  "source": {…} },
  "human_decision": null,
  "models": [ { "agent": "validator", "provider": "anthropic", "model": "…", "requested_model": "…", "latency_ms": 3144, "source": {…} } ],
  "chain": { "scope": "whole_ledger", "ok": true, "rows_checked": 118, "first_break": null, "run_rows": 7 }
}
```

Rules of composition, each with a test: a section whose row is absent is `null` (an aborted run has no `escalation` and no `outcome.settlement`; a Guardrail throw yields the synthesised `escalation` the run repository already produces); `llm_verification_recorded` is `false` when the `llm_flags_*` keys are absent (rows written before `0.9.1.2`), and the two lists are then empty, so absence is never shown as "nothing was claimed"; `human_decision` is filled from a `human_approval` / `human_rejection` row when one exists; `models` lists every agent row that has an `llm_call.model`, so the demo fixture appears with `provider: "demo_fixture"` and no model; the prompts are never included here (`get_audit_trail(include_prompts=true)` is the one place).

### 3d. Worked example — Harborline run `0cdfa114` (Vercel → Render, 30 October 2026), from its recorded rows

| Section | What the tool returns (from audit rows 70–76, chain `ok`) |
|---|---|
| outcome | `settled`, settlement `82500.00`, no rules fired — row 76 `pipeline_settled`, chain `f5db6357…` |
| coverage | covered, confidence 0.92, basis *Named Perils Covered, Exclusions*; passages seen: *Named Perils Covered* (0.598), *Exclusions* (0.581), *Sub-Limits* (0.543); cited: the first two; reasoning begins "The narrative describes a burst supply line (plumbing system) that caused accidental water discharge…" — row 72 |
| settlement | 82,500.00, confidence 0.85, range water_damage / moderate / 50,000–200,000, `demo_fixture: false`; reasoning: "…positions slightly below the claim to reflect typical adjustment for **inventory valuation and depreciation**, while remaining in the upper-middle portion of the market range…" — row 73 |
| guardrail | passed; rule-engine flags `[]`; `llm_flags_counted: []`; `llm_flags_discarded: [{kind: hallucinated_citation, quote: "inventory valuation and depreciation", detail: "reasoning references a provision for inventory valuation and depreciation that does not appear in the retrieved policy chunks", reason: quote_not_a_provision}]`; `llm_verification_recorded: true` — row 74 |
| escalation | `escalate: false`, "No escalation rules fired; claim is eligible for auto-settlement." — row 75 |
| models | doc_parser / validator / adjuster / guardrail all `anthropic`, `claude-haiku-4-5-20251001`, requested = responding; latencies 1184 / 3144 / 2418 / 1701 ms |
| chain | `whole_ledger`, ok, 118 rows checked (the Render ledger on 2 November), `run_rows: 7` |

Read against the prompt's intent: the model's refused claim sits beside the code's reason, and the claim settled on the rules alone. The sentence the prompt quotes, *"the $1.5M ceiling"*, is the Northwood run `6197d116` (rows 91–97: $920,000, `settlement_over_ceiling`, the same `quote_not_a_provision` refusal); the demo script can use either, and both are in the Render ledger.

### 3e. Prompts and resource

- **`audit_this_run`** (`user/mcp_audit_this_run.md`, argument `correlation_id`): instructs the client to call `verify_chain`, then `explain_decision`, then `get_audit_trail` without prompts, and to report, in order: whether the chain verifies, what each agent recorded, what the Guardrail objected to and why it did or did not count, and which rules sent the claim where — quoting audit ids.
- **`why_settled_or_escalated`** (`user/mcp_why_settled_or_escalated.md`, argument `claim_id`): `get_claim`, then `explain_decision` on the latest run, then answer in plain language with the rules and amounts, citing rows.
- **`policy://excerpt`**: `@mcp.resource("policy://excerpt", mime_type="text/plain")` returning `backend/data/sample_policy.txt` (read through the same path guard the policy loader uses).

Both templates are loaded through `PromptLoader.user(name, correlation_id=…)`, so they follow the externalised-prompt rule and the strict-placeholder check.

---

## 4. The tool-call log — decision: a table (recommended), interface-stability event acknowledged

**Recommendation: (a) `mcp_tool_calls` via migration `0003_mcp_tool_calls`.** The governance value is the persisted record of who asked what of the system; an in-memory buffer is lost at every scale-to-zero, which on Azure is every demo gap. The feed's reconnect replay (§5) also falls out of the table for free. Option (b) is kept only as the structured log line, which the table does not replace: every record is also written as one JSON line to the `backend.app.mcp.calls` logger (so Application Insights and the Render log viewer carry it too).

```sql
CREATE TABLE mcp_tool_calls (
    call_id      BIGSERIAL PRIMARY KEY,
    called_at    TIMESTAMPTZ NOT NULL,
    tool         TEXT NOT NULL CHECK (length(tool) > 0),
    arguments    JSONB NOT NULL,
    target_kind  TEXT NULL CHECK (target_kind IN ('claim', 'run')),
    target_id    UUID NULL,
    caller       TEXT NOT NULL,
    outcome      TEXT NOT NULL CHECK (outcome IN ('ok', 'error')),
    error_class  TEXT NULL,
    latency_ms   INTEGER NOT NULL CHECK (latency_ms >= 0)
);
CREATE INDEX mcp_tool_calls_called_at_idx ON mcp_tool_calls (called_at DESC);
```

`target` is the first id the tool concerns (`compare_runs` records `run` + `correlation_id_a`, both ids stay in `arguments`; `run_scenario` records the run it created, or `null` when it failed before one existed). `caller` is the token label. **This table is not `audit_log` and is not chained**: the chain is the claims record, and questions about it are a different thing from decisions in it. `ToolCallRecord` (Pydantic, `extra="forbid"`) is the single shape used for the row, the log line, the bus message and the SSE frame.

**Interface-stability acknowledgement.** A new table is a database-contract event: additive (no existing table or column changes), `down_revision = "0002_audit_human_agent"`, applied by the same `alembic upgrade head` in CI, in the pytest fixture, and by hand on Neon and on the Azure server before the deploy (as 0002 was). The test fixture's `TRUNCATE` list gains the table. `README.md` and `infra/bicep/README.md` migration steps are updated.

---

## 5. The live feed — `GET /api/mcp/activity`

- **`ActivityBus`** (`backend/app/mcp/activity.py`): `subscribe() -> AsyncIterator[ToolCallRecord]` registers a per-subscriber `asyncio.Queue(maxsize=cfg.pipeline.event_queue_maxsize)` and removes it on exit; `publish(record)` puts to every queue, dropping with a WARNING on a full one, never raising (the same discipline as the pipeline bus). It is built in `_lifespan` as `app.state.activity_bus`. A separate class rather than a reserved channel on `PipelineEventBus` because that bus is one-reader-per-key with a terminal sentinel and a teardown timer, none of which fits an endless broadcast (finding 7).
- **The recorder** writes the row (threadpool), then publishes on the loop. The row's `call_id` is the SSE event id.
- **The endpoint** (`backend/app/api/mcp.py`, `mcp_router`, included in `api_router`): subscribe first, then read the last `activity_replay_count` rows (ascending), yield them as `event: tool_call`, `id: <call_id>`, `data: <ToolCallRecord JSON>`, then yield live records, skipping any whose `call_id` is not greater than the highest replayed — so a call that lands between the read and the first live frame is neither lost nor doubled. `EventSourceResponse` as the pipeline stream uses it. Reconnect is the browser's `EventSource` retry; the replay on each connect is the "last N on reconnect" the prompt asks for, and the client dedupes by `call_id`, so `Last-Event-ID` is not needed.
- **`GET /api/mcp/tools`** (same router): `{"mounted": bool, "path": "/mcp", "tools": [{name, title, description, kind: "read" | "action", parameters: <input JSON schema>}]}`, built from `await server.list_tools()` with `kind` derived from `annotations.readOnlyHint`. Generated from the server's definitions on every request, so it cannot drift.
- Both endpoints are unauthenticated like the rest of `/api` (the web UI is public). The records carry ids, a tool name, a label, an outcome and a latency — nothing secret, nothing personal.

---

## 6. Frontend

### 6a. Routing and shared pieces

- `App.tsx`: two nav links, *Integrations* (`/integrations`) and *Guide* (`/guide`), after *Agents*; two `<Route>`s; `App.test.tsx` gains the two link assertions.
- `api/types.ts`: `McpTool`, `McpCatalogue`, `ToolCallRecord`. `api/client.ts`: `getMcpCatalogue()`, `mcpActivityUrl()`. `hooks/queries.ts`: `useMcpCatalogue()` (`['mcpCatalogue']`, `staleTime: FRESH`).
- `hooks/useMcpActivity.ts`: the `useRunStream` pattern (native `EventSource`, named event `tool_call`, `JSON.parse` in try/catch) with newest-first state keyed by `call_id`, a cap of the last 100 records in memory, and no terminal close.
- `components/ui.tsx`: `Badge` gains `tone="warning"` (amber) for *action*.
- `copy/integrations.ts`, `copy/guide.ts`: all prose for the two pages, reviewed as text (draft Guide copy in 6c).

### 6b. Integrations page — `pages/IntegrationsPage.tsx`

Three cards, top to bottom:

1. **Tool catalogue** — table *Tool · What it does · Kind*, one row per catalogue tool, `read-only` (neutral badge) / `action` (amber). A caption under the table: *Generated from the server's own definitions.*
2. **Connection** — the `/mcp` URL for this deployment (`API_BASE + '/mcp'`, or the page's origin when `API_BASE` is empty), the Claude connector steps (*Customize › Connectors › Add custom connector › URL › No sign-in › Request headers: `authorization` = `Bearer <MCP shared token>`*), a second snippet for Claude Code (`claude mcp add-json agentic-claims '{"type":"http","url":"…/mcp","headers":{"Authorization":"Bearer <MCP shared token>"}}'`), each with a `CopyButton`, the token always the placeholder text. One paragraph from `copy/integrations.ts` saying what MCP is, that every answer comes from the audit trail, that the server reads and runs the three scripted scenarios and nothing else, and that production would put this behind API Management with Entra sign-in. When `mounted` is false the card opens with the plain sentence *The MCP endpoint is not configured on this deployment (no shared token is set), so nothing can connect to it; the catalogue below shows what it would offer.*
3. **Live activity** — the feed, newest first: time, tool, caller, outcome badge, latency, and a link to the run (`/claims/:claimId/runs/:correlationId` needs the claim id, which the record does not carry — the link goes to `/audit?correlation_id=…` for `run` targets and `/claims/:id` for `claim` targets). Empty state: *No tool calls yet.* A link to the Guide at the foot; the Guide links back.

### 6c. Guide page — `pages/GuidePage.tsx`, copy in `copy/guide.ts` (draft for review at the gate)

One screen, four short blocks and a link list. Draft text:

> **What this is.** The working claims-handling system this project built. It is a prototype in scope, with synthetic claims and a short policy excerpt, and it is built and operated to production standards: deployed on two clouds, audited, verified and change-controlled. It reads a claim, checks it against the policy, proposes a settlement, checks that proposal, and either settles the claim or hands it to a person, with every step recorded in a tamper-evident audit trail.
>
> **The three scenarios.** *Harborline* (water damage, $85,000) should settle on its own, at about $82,500: covered, inside the market range, nothing for the Guardrail to object to. *Northwood* (fire, $850,000) should go to a person because the proposed settlement is above the $250,000 ceiling. *Coral Bay* (storm, $1.4M) should go to a person because the Guardrail finds the Adjuster citing a "Coastal Surge Rider" endorsement that the policy does not contain, and the amount is over the ceiling too.
>
> **Reading a run page.** The four cards are the four agents in order: Doc-Parser, Validator, Adjuster, Guardrail; each shows what it produced and how long it took, and opens to show the recorded request and response. The status badge is the run's outcome: *settled*, *awaiting human*, or *aborted*. *View audit log* opens every recorded step of the run with its hash. The Guardrail's refused claims — things the model said were policy citations that the code could not find in the Adjuster's text — are in the audit log's `output_check` row under `llm_flags_discarded`, and in the *explain decision* answer on the Integrations page.
>
> **Links.** The interactive architecture diagram (the production target, with a clickable claim journey) · The build story, phase by phase · The decision register · The repository · Integrations.

The scenario facts are taken from the seed data and the escalation policy; the Coral Bay endorsement name from the demo fixture. Each block is a `Card`; the page stays inside one screen at 1280×800 (a test asserts the copy's total length stays under a constant).

### 6d. Run Detail — "Copy question for Claude"

A second `CopyButton` beside the existing one: `label="Copy question for Claude"`, `value` from `copy/integrations.ts`: *Using the claims MCP server, explain run `<correlation id>` and tell me whether its audit chain verifies.* The existing test's `/copy/i` selector is tightened to `{ name: 'Copy' }`.

### 6e. Frontend tests (Vitest + Testing Library, existing style)

- `IntegrationsPage.test.tsx`: renders every tool the stubbed catalogue returns, with the right badge per `kind` (the "renders every tool the backend reports" test); shows the not-configured sentence when `mounted` is false; renders feed records newest first with the audit link; the clipboard copies the Claude Code snippet with the placeholder, never a token.
- `GuidePage.test.tsx`: the four blocks and the five links render with the exact URLs; the Integrations link is present.
- `useMcpActivity.test.ts`: with a richer `MockEventSource` (captures listeners, dispatches `MessageEvent`), records are prepended, deduplicated by `call_id`, capped, and a malformed frame is ignored.
- `RunDetailPage.test.tsx`: the new button copies the question with the run's id.
- `App.test.tsx`: the two nav links. `copy/guide.test.ts`: links are absolute `https://` URLs and the architecture URL is the one in the prompt.

---

## 7. Tests (backend)

All with the service layer stubbed unless stated; the live-LLM and end-to-end tests gated as the suite already gates them.

- **`test_mcp_auth.py`** — with `with TestClient(create_app(settings_with_token)) as c`: `POST /mcp` without a header → 401 with `WWW-Authenticate: Bearer`; wrong token → 401; right token with an `initialize` request → 200; `GET /mcp` without a token → 401; token unset → `/mcp` is 404 and `/api/mcp/tools` says `mounted: false`; empty-string token counts as unset. **Mutation proof** (the project's protocol: applied, observed, reverted, recorded in the report): replace the `compare_digest` call with `True` — the first two tests must fail; replace the mount condition with `True` — the "404 when unset" test must fail.
- **`test_mcp_tools.py`** — through the in-memory `Client(mcp)` with the repositories and the factory stubbed by `app.state` and `monkeypatch`: each tool's happy path returns its model; `get_run` / `get_claim` / `explain_decision` / `get_audit_trail` / `verify_chain` / `compare_runs` on an unknown id → `is_error` result whose text starts with `not_found:`; `compare_runs` across claims → `is_error` with the mismatch text; `get_audit_trail` default strips `llm_call.prompt` from every entry and `include_prompts=True` keeps it; `run_scenario("anything_else")` is refused at the schema (JSON-RPC invalid params) and, calling the function directly, by the `ValueError` guard; `run_scenario("harborline")` inserts a claim with `scenario_tag=auto_approve` and calls the factory's orchestrator with the new claim id; the catalogue lists exactly the nine registered tools with the right `kind` per tool.
- **`test_mcp_explain.py`** — `compose_explanation` over fixture rows: the full shape on a settled run; `null` sections on an aborted run; a Guardrail-throw run gets the synthesised escalation; a pre-`0.9.1.2` `output_check` row gives `llm_verification_recorded: false` and empty lists; a human-decision row fills `human_decision`; every `source.audit_id` matches its row; the demo-fixture Adjuster appears in `models` with `provider: demo_fixture`. The 30 October rows of `0cdfa114` (fetched for this plan, prompts stripped) are saved as a fixture so the worked example in §3d is also a test.
- **`test_mcp_tool_log.py`** — against the test database: a successful call writes one row with `outcome: ok`, the arguments, the target and a non-negative latency; a `not_found` refusal writes `outcome: error`, `error_class: ToolError`; an unexpected exception writes `error_class` and the client sees `internal_error: <Class>` and no traceback text; the caller is the label, and the token value appears nowhere in the row or the log line (asserted by searching both).
- **`test_mcp_activity.py`** — `ActivityBus`: two subscribers both receive a record; a full queue drops with a warning; the SSE endpoint, with a stubbed bus and a seeded table, emits the replay rows then a live record, and never a `call_id` twice (the overlap case).
- **`test_audit_api.py` / `test_api_pipeline.py` / `test_agents_test_api.py`** — unchanged assertions re-run after the three promotions in finding 8; a new test for `AuditRepository.list_entries`, `RunsRepository.count_runs_by_claim` and `make_orchestrator_factory`.
- **`test_mcp_e2e.py`** — gated on `RUN_MCP_E2E_TESTS=1` with `MCP_E2E_URL` and `MCP_E2E_TOKEN`: the official client (`httpx2.AsyncClient` with the bearer header → `streamable_http_client` → `Client`) lists tools, reads the policy resource, calls `list_claims` and `verify_chain`, and confirms a wrong token is refused. Run by hand against a local backend before the deploy and against the deployed endpoints in §8.
- **`test_settings.py`** — the `mcp` block defaults, `MCP__SHARED_TOKEN` through the environment, the `token_label` and `activity_replay_count` bounds.

Expected: about 45 backend tests added to 429 passing, about 14 frontend tests added to 36. `ruff`, `mypy --strict` and the frontend lint/typecheck stay clean; no function over 50 lines, the audit-payload builders excepted as already recorded.

---

## 8. Deployed verification — with Dermot present

1. **Token.** `openssl rand -hex 24` once; export `MCP_SHARED_TOKEN` in the deploying shell. `scripts/azure-deploy.sh` resolves it like the Postgres password: reuse the Key Vault value if the secret exists, else take it from the environment — so a later redeploy does not rotate the token under a connected client. The same value goes into the Render dashboard as `MCP__SHARED_TOKEN`.
2. **Azure.** `azure-start.sh` first (Postgres was stopped on 30 October; Azure will have restarted it around 6 November, so check). `alembic upgrade head` against the Azure server (0003). `azure-deploy.sh what-if` — expect the known noise plus the real changes: one Key Vault secret, one Container App secret and env entry; then `deploy`. Push to `main` → CI → the two deploy workflows carry the image and the frontend.
3. **Render / Neon / Vercel.** `alembic upgrade head` against Neon; the dashboard variable; the push deploys the backend and the frontend.
4. **Connect.** In Claude (claude.ai or Desktop): *Customize › Connectors › Add custom connector*, the Azure `/mcp` URL, *No sign-in*, request header `authorization: Bearer <token>`. If the *Request headers* field is absent on the account (it is in beta), fall back to Claude Code with `claude mcp add-json` and record which path was used.
5. **Demo script** (`docs/demo-mcp.md`), two windows: the Integrations page open on the Azure frontend; in Claude, *run_scenario harborline* → the feed shows the call, the Run page can be opened live; *explain_decision* on the returned id → the refused claim, if the model raised one, beside its reason; *verify_chain*; then *compare_runs* on the Render pair `2c42cf40` / `0cdfa114` with the Render endpoint connected, or on an Azure pair if one exists (D6).
6. **Confirm** on both deployments: the feed shows the calls; `mcp_tool_calls` holds them (`psql` count and the newest rows, token value absent); `/api/mcp/tools` lists nine tools; a wrong token is refused; the pipeline, the audit chain and the three scripted scenarios are unchanged (`verify-demo-scenarios.py` against Render, the three scenarios through the Azure UI).
7. `azure-stop.sh` last.

---

## 9. Docs, version, interface stability

- **Version** `0.10.0` in `pyproject.toml` (the one runtime source; `/health` follows).
- **Interface-stability events, acknowledged here:** (1) the `mcp_tool_calls` table, migration 0003, additive; (2) three new HTTP surfaces — `/mcp` (MCP streamable HTTP, bearer), `GET /api/mcp/tools`, `GET /api/mcp/activity` (SSE) — additive; (3) new settings block `mcp`; (4) new Key Vault secret `mcp-shared-token` and Container App env `MCP__SHARED_TOKEN`. **Unchanged:** every existing HTTP and SSE shape, every audit payload, the chain, the agents, the pipeline, `Dockerfile`, `render.yaml`, the frontend's existing routes.
- **Docs:** `README.md` *Integrations (MCP)* section (connection steps, the demo pointer, the "not mounted without a token" rule); `docs/demo-mcp.md`; `docs/architecture-stack-reference.md` (*API edge* row: the prototype column gains "MCP endpoint `/mcp` behind a shared bearer token"; the Phase 9 table gains an *AI access to the record* row naming API Management + Entra as the production path); `docs/dora-third-party-register.md` (Anthropic row: Claude's connector reaches the claims record from Anthropic's cloud through `/mcp`; every call is logged in `mcp_tool_calls` with caller, tool, target and outcome; the shared token is revocable by rotation) with one cross-reference line in `change-governance.md`; `docs/BACKLOG.md` (MCP item closed; *Azure AI Foundry as a third provider* moved to *Future work* with the two risks the prompt names, region and quota; the *How it works* page item noted as partly met by the Guide); `docs/decision-register.md` R-20 (the access decision: shared token, not mounted when unset, no anonymous mode; the read-only decision: one action, no human-decision tool) and further entries for anything the execution deviates on; `docs/build-log.md` entry; `docs/prompts/README.md` entry 24 with signposts on the prompt, plan and report; `README_TLDR.md` and the table regenerated by the §10 script; `CLAUDE.md` (status, tree, settings, an *Architectural Decisions* bullet for the five design rules, the interface extensions list, Foundry to the backlog).

---

## 10. Regeneration script — `scripts/regenerate-build-story.py`

Stdlib only. Parses every `### NN — Title` heading and its `**TL;DR:**` paragraph in `docs/prompts/README.md`, rewrites the at-a-glance rows between the table header and the next blank line, and rewrites `docs/prompts/README_TLDR.md` below its preamble; refuses (non-zero, with the count) if the entries are not numbered contiguously or any entry lacks a TL;DR; after writing, **exits 1 if either file's content changed** and 0 if both were already identical to the entries — so the standing rule is one command, and a run that reports a change tells the author to commit. Tests in `backend/tests/test_regenerate_build_story.py` over a temporary copy: identical input → exit 0 and no write; a changed TL;DR → exit 1 and both files updated; a missing TL;DR → refusal with the entry number in the message. Used at this phase's close-out, and the `CLAUDE.md` *Build story* rule names it.

---

## 11. Execution order (four commits, each green)

1. **Server and log.** `uv add mcp`; settings; `backend/app/mcp/` (`server.py`, `auth.py`, `tools.py`, `explain.py`, `scenarios.py`, `activity.py`, `models.py`, `tool_log.py`); the three promotions of finding 8; migration 0003; the two prompt templates; `main.py` wiring; backend tests of §7 except the feed and e2e; mutation proof recorded.
2. **Feed, catalogue, frontend.** `api/mcp.py`; `ActivityBus`; the two pages, the hook, the button, the copy modules, the frontend tests; local end-to-end run of `test_mcp_e2e.py` against `uvicorn` with a token.
3. **Docs and script.** §9 documents, §10 script and its tests, `0.10.0`, run the script at close-out.
4. **Deploy and verify** per §8; report `24-…-report.md`; build-log, register, build-story entries; `CLAUDE.md`; final push; `azure-stop.sh`.

---

## Files

**New (backend):** `backend/app/mcp/__init__.py`, `server.py`, `auth.py`, `tools.py`, `explain.py`, `scenarios.py`, `activity.py`, `models.py`, `tool_log.py`; `backend/app/api/mcp.py`; `backend/app/audit/repository.py`; `backend/db/migrations/versions/0003_mcp_tool_calls.py`; `backend/app/prompts/user/mcp_audit_this_run.md`, `mcp_why_settled_or_escalated.md`; tests `test_mcp_auth.py`, `test_mcp_tools.py`, `test_mcp_explain.py`, `test_mcp_tool_log.py`, `test_mcp_activity.py`, `test_mcp_e2e.py`, `test_regenerate_build_story.py`; fixture `backend/tests/fixtures/mcp/run_0cdfa114.json`.
**Modified (backend):** `pyproject.toml`, `uv.lock`, `backend/settings.py`, `backend/settings.yaml.template`, `backend/app/main.py`, `backend/app/api/__init__.py`, `api/audit.py`, `api/pipeline.py`, `api/claims.py` (the shared limit constant), `api/agents_test.py`, `backend/app/runs/repository.py`, `backend/data/seed_claims.py` (public accessor), `backend/tests/conftest.py` (TRUNCATE list), `test_settings.py`.
**New (frontend):** `src/pages/IntegrationsPage.tsx`, `GuidePage.tsx` and their tests; `src/hooks/useMcpActivity.ts` and test; `src/copy/integrations.ts`, `guide.ts`, `guide.test.ts`.
**Modified (frontend):** `src/App.tsx`, `App.test.tsx`, `src/api/client.ts`, `types.ts`, `src/hooks/queries.ts`, `src/components/ui.tsx`, `src/pages/RunDetailPage.tsx` and test, `src/setupTests.ts` (richer `MockEventSource`).
**Infra and scripts:** `infra/bicep/main.bicep`, `main.bicepparam`, `modules/keyvault.bicep`, `modules/containerapps.bicep`, `infra/bicep/README.md`; `scripts/azure-deploy.sh`; new `scripts/regenerate-build-story.py`.
**Docs:** as §9, plus `docs/demo-mcp.md`, this plan, the report.

---

## Risks

1. **The connector's *Request headers* field is beta and account-gated.** If absent, the Claude Desktop demo runs through Claude Code instead; the finding is recorded and the panel's wording adjusted. The `mcp-remote` bridge is the third path, documented only.
2. **Connector tool timeout versus a 45-second `run_scenario`.** Unknown until tried; the fallback (detached start, poll `get_run`) is one function (D5).
3. **Cold starts.** Azure at zero replicas takes ~28 s; Render's free tier sleeps. The demo warms both (Integrations page open, `azure-start.sh`) before connecting.
4. **The first exact-path mounting of a Streamable HTTP app** was checked with a stand-in inner app, not the SDK's; step 1 of the execution confirms it with the SDK and the fallback is `Mount` plus `FORWARDED_ALLOW_IPS=*` on both stacks (an env var, not a command change).
5. **`uv.lock` growth** (about ten packages). Reported; none replaces an existing version.
6. **Scope.** This is the largest phase since 9.1: nine tools, a migration, a feed, two pages, infra and a script. The four-commit order keeps each step green and lets the deploy wait for a session with Dermot present.
7. **The Guide's claim about where refused claims appear** is true today only for the Audit page and the MCP answer; O2 would make the Run page show them too.

---

## Decisions requested at the approval gate

- **D1 — Tool-call log:** table `mcp_tool_calls` via migration 0003 (recommended) or in-memory ring buffer plus log lines.
- **D2 — `mcp` 2.3.0** as the one new dependency, with its transitive set as listed, confirmed.
- **D3 — Host allowlist:** disable the SDK's DNS-rebinding host check on `/mcp` (recommended: the ingress owns `Host`, the token is the control), or add an `mcp.allowed_hosts` setting listing the two deployed hostnames plus localhost.
- **D4 — Connection panel:** Claude connector steps first and the Claude Code `add-json` command second, `mcp-remote` named in the docs only (recommended), or a single snippet.
- **D5 — `run_scenario` runs synchronously** and returns the terminal result with the id (recommended), switching to detached-plus-poll only if the connector times out in §8.
- **D6 — The demo's comparison pair:** the Render pair `2c42cf40` / `0cdfa114` on the Harborline claim (recommended, the behaviour change between `0.9.1.1` and `0.9.1.2` on one claim in one day), with an Azure pair used instead if §8 finds one.
- **D7 — The Guide copy** in §6c, as drafted or amended.
- **D8 — The DORA-register placement** of the access paragraph (Anthropic row, recommended) rather than `change-governance.md`.

---

## Optional enhancements (clearly labelled; not in scope unless approved)

- **O1.** `/api/mcp/tools` also returns the two prompts and the resource, and the Integrations catalogue shows them in a second, shorter table.
- **O2.** The Guardrail card on Run Detail shows a one-line *Refused claims: n* with the quotes, so the demo talking point is visible without opening the audit JSON; the Guide text then points there too.
- **O3.** One source for the three scripted scenarios: `scripts/verify-demo-scenarios.py` and `frontend/src/fixtures/demoClaims.ts` read them from the backend (`GET /api/scenarios` or a generated file) instead of carrying copies.
- **O4.** `run_scenario` accepts an optional `claim_id` of an existing scripted claim to re-run it, so a demo can create its own same-claim pair for `compare_runs` on any deployment.
- **O5.** A `Last-Event-ID`-aware replay on the activity feed (resume from the last seen `call_id` rather than the fixed last N).

---

## Approval

**Approved by Dermot, 2 November 2026.** D1–D6 and D8 as recommended. **D7:** the Guide copy as drafted with two changes — Harborline should settle "at a figure a little below the claimed amount" rather than naming $82,500, and readers are pointed to the Guardrail card for refused claims rather than to the audit JSON key (which makes O2 part of the scope). **Optional items:** O1, O2 and O4 taken into scope; O3 and O5 to the backlog. Execution follows §11 and **stops before §8, the deployed verification, so that Dermot can be present.**
