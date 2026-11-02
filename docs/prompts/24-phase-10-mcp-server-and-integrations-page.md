# Phase 10 — An MCP server over the audit trail, and an Integrations page that shows it working

## Why this phase exists

Today the system is used through its web interface. Phase 10 adds an MCP server, so that an MCP client (Claude Desktop, Claude Code, or any other tool that supports the Model Context Protocol) can ask the system questions in natural language and receive answers taken from the audit trail. A claims manager can ask why a claim settled; an auditor can ask what the Guardrail objected to on a given run and why the objection did not count. The answer comes from the recorded data, with the audit rows it was drawn from.

A new Integrations page in the web interface lists the tools an AI client may call, generated from the server's own definitions, and shows tool calls as they happen. In a demonstration, a question typed into Claude Desktop produces visible tool calls on the web page while the answer appears in Claude Desktop, so the audience can see both the question being answered and the record of it being asked.

Decided by Dermot on 2 November 2026, in preference to Phase 9.3 (Azure AI Foundry), which moves to the backlog. Version `0.9.1.2 → 0.10.0`: a new capability, so a minor version. Plan-first as always; the plan is approved before any code.

## Design rules

1. **Answers come from the audit trail, never from re-deciding.** No tool asks a language model to judge a claim. The MCP server reads what the agents recorded and returns it, structured, so the client's model can explain it. The system of record is untouched by any question.
2. **Read-only, with one named exception.** The only tool that changes anything is `run_scenario`, limited to the three scripted scenarios by name. There is no tool for the human approve/reject decision: a person's decision on a claim belongs in the system of record's own interface, not a chat tool. No tool exposes the agent test bench or any database access.
3. **Every tool call is logged** with the tool, its arguments (which contain no secrets or personal data), the target run or claim, the caller identity available, the latency and the outcome. This is the "who asked what of the system" trail the DORA register can point at.
4. **The server lives inside the backend**, served at `/mcp` over the MCP streamable-HTTP transport, so it deploys with the backend to both stacks, shares its settings and logging, and the tool-call feed is in the same process as the event bus. A separate stdio process is not built.
5. **Access is explicit.** The `/mcp` endpoint requires a bearer token from settings (`mcp.shared_token`, env `MCP__SHARED_TOKEN`), held in Key Vault on Azure and in the Render dashboard. If the token is unset, the endpoint is **not mounted** and the Integrations page says so; there is no anonymous mode and no flag to create one. The plan states that production would put this behind API Management with Entra sign-in, as the architecture diagram already shows.

## What gets built

### 1. The MCP server (`backend/app/mcp/`)

Tools, each a thin wrapper over the existing API layer (call the same service functions the routers call, not HTTP to self):

| Tool | Kind | Returns |
|---|---|---|
| `list_claims(status?)` | read | claims with status and run count |
| `get_claim(claim_id)` | read | the claim record and its run summaries |
| `get_run(correlation_id)` | read | terminal status, fired rules, each agent's output and timing |
| `explain_decision(correlation_id)` | read | the composed account: Validator verdict and the policy passages it saw; Adjuster figure, range and reasoning; Guardrail rule-engine findings, LLM claims counted and discarded with the model's words and the code's reason; escalation rules fired; chain verification result; each statement tagged with the audit row it came from |
| `get_audit_trail(correlation_id, include_prompts=false)` | read | the entries in chain order; with prompts, the exact system and user text each agent sent |
| `verify_chain(correlation_id)` | read | the chain verification result |
| `compare_runs(correlation_id_a, correlation_id_b)` | read | the existing run comparison |
| `get_agent_instructions(agent)` | read | the agent's current system prompt |
| `run_scenario(name)` | **action** | creates the scripted claim (`harborline`, `northwood`, `coral_bay`) and runs the pipeline; returns the correlation id |

MCP prompts (templates the client offers the user): *Audit this run* and *Why did this claim escalate or settle?*, each stating which tools to call in which order. MCP resource: the policy excerpt text (`policy://excerpt`), so an answer can quote the wording.

`explain_decision` is the most important tool. The plan shows its output shape in full, and shows the Harborline run `0cdfa114` (Vercel, 30 October) as a worked example: the model's refused claim *"the $1.5M ceiling"* beside the reason `quote_not_a_provision`.

### 2. The tool-call log

Every call recorded with: timestamp, tool, arguments, target (claim or correlation id where present), outcome (`ok` / `error` with the error class), latency, and the caller identity the transport provides (for a shared token, the token's label, not its value). **The plan decides between** (a) a new table `mcp_tool_calls` via migration 0003, additive, **an interface-stability event to acknowledge**, or (b) structured log lines plus an in-memory ring buffer for the live feed. Recommendation to consider: (a), because the governance value is in the persisted record, and an in-memory feed is lost on every scale-to-zero. The tool-call log is **not** written to `audit_log`: that chain is the claims record, and questions about it are a different thing from decisions in it.

### 3. The live feed

A new SSE endpoint `/api/mcp/activity` streams tool-call records as they happen, reusing the `PipelineEventBus` pattern (a separate bus or a reserved channel; the plan says which and why). On reconnect the client receives the last N records from the log.

### 4. The Integrations page (frontend)

A new page, *Integrations*, in the top navigation beside Claims, Audit and Agents:

- **Tool catalogue**, fetched from a new read endpoint `/api/mcp/tools` that returns the server's own tool definitions (name, description, parameters, read-only or action). Rendered as a table with a plain-language one-liner per tool and a *read-only* / *action* badge. Because it is generated from the definitions, it cannot drift from what the server offers.
- **Connection panel**: the `/mcp` URL for this deployment and the client configuration snippet for Claude Desktop (token shown as a placeholder, never the value), plus a one-paragraph plain-language explanation of what MCP is and what the server does and does not permit.
- **Live activity feed**: the tool calls as they arrive over SSE, newest first, each linking to the run it concerns where there is one. When the endpoint is not mounted (no token configured), the page says so plainly instead of showing an empty feed.

### 5. Run Detail: "Copy question for Claude"

A small button on the Run Detail page that copies a ready-made question to the clipboard: *"Using the claims MCP server, explain run `<correlation id>` and tell me whether its audit chain verifies."* So the correlation id never has to be read aloud in a demonstration.

### 6. Guide page (frontend)

A new page, *Guide*, in the top navigation, one screen long, for a first-time visitor: one paragraph on what the system does and what it is (a working system, prototype in scope, built to production standards, in the glossary's words); the three scripted scenarios with the outcome each should produce and why; how to read a run page (the four agent cards, the status badge, the audit log link, and where the Guardrail's refused claims appear); and a short list of links: the interactive architecture diagram at `https://dcopps.github.io/agentic-claims-poc/diagrams/Architecture_Diagram.html` (described as the production target, with a clickable claim journey), the build story, the decision register, and the repository. Text lives in the frontend's existing `copy/` module, not inline in components, so it can be reviewed as prose. The Guide and Integrations pages link to each other.

### 7. Documentation and demo

- `README.md`: an *Integrations (MCP)* section with the connection steps and the demo script.
- A two-minute **demo script** in `docs/demo-mcp.md`: two windows; `run_scenario harborline` from Claude Desktop; watch the feed; `explain_decision`; then `compare_runs` between a 26 October escalation and a 30 October settlement to show the change in the Guardrail's behaviour between the two dates.
- `docs/architecture-stack-reference.md`: the MCP server added to the prototype column; API Management with Entra sign-in named as the production access path.
- `docs/dora-third-party-register.md` or `change-governance.md`: one paragraph on AI access to the claims record being logged.
- Register entry (the access and read-only decisions), build-story entry, signposts, `CLAUDE.md` (status, tree, settings, an *Architectural Decisions* bullet for the five design rules, Foundry moved to the backlog with its two risks).

## Plan-first

Produce `docs/prompts/24-phase-10-mcp-server-and-integrations-page-plan.md` covering:

1. **Dependency.** The MCP Python SDK (`mcp`, with its FastMCP server API) is a new dependency: flag it per the standing rule, state its transport support for mounting inside an existing ASGI application, and confirm the version. Any further dependency is flagged separately.
2. **Mounting and auth.** How `/mcp` is mounted into the FastAPI app, how the bearer token is checked before any tool runs, the exact behaviour when the token is unset (not mounted; the tools endpoint still answers so the Integrations page can explain), and the settings additions (`settings.py` and `settings.yaml.template` both).
3. **Tool implementations.** Each tool's parameters, return shape, and the existing service function it calls. `explain_decision` in full with the worked example. Error behaviour: unknown ids return a structured not-found, never a stack trace; every tool records a log entry on every exit path.
4. **The tool-call log decision** (table or in-memory), with the interface-stability acknowledgement if a table.
5. **The live feed** mechanics and the reconnect behaviour.
6. **Frontend.** The two new pages (Integrations, Guide), the catalogue endpoint, the feed hook (reusing the existing SSE client), the Run Detail button, and tests in the existing style (component tests for the page and the button; a test that the catalogue renders every tool the backend reports).
7. **Tests.** Unit tests per tool with the service layer mocked, including the not-found and token-missing paths; a test that `run_scenario` refuses any name outside the three; a test that the tool catalogue endpoint lists exactly the registered tools; a gated end-to-end test against a local backend driving the MCP endpoint with the official client library. Mutation proof for the auth check (remove it, show the test fails).
8. **Deployed verification, with Dermot present.** Token into Key Vault via Bicep parameter (`readEnvironmentVariable`, as the other secrets) and into the Render dashboard; push deploys both stacks; connect Claude Desktop to the Azure `/mcp` endpoint; run the demo script; confirm the Integrations page feed shows the calls on both deployments; confirm the tool-call log persisted (if a table). `azure-start.sh` first, `azure-stop.sh` last.
9. **Docs, version, interface stability** as above. `0.10.0`. The tool-call table, if chosen, is the one interface event.
10. **Regeneration script.** The at-a-glance table and `README_TLDR.md` are currently regenerated by hand each close-out. Add a small committed script under `scripts/` that regenerates both from the entries in `docs/prompts/README.md` and exits non-zero if the result differs from what is committed, so the standing rule becomes a command. Use it at this phase's close-out.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`: plan-first, defensive ordering, function size, externalised prompts (the two MCP prompt templates live under `backend/app/prompts/` like every other prompt), system/user separation, mutation-proof tests, no secrets or client name anywhere.
- No change to the agents, the pipeline, the audit chain, or any existing HTTP or SSE shape. The MCP server is additive.
- The human-decision endpoint is not exposed through MCP. The agent test bench is not exposed.
- The shared token never appears in code, docs, logs, the tool-call log or the Integrations page.
- Nothing on Render, Vercel or Neon changes except by the normal deploy and the one dashboard variable.

## Archive

Pre-saved at `docs/prompts/24-phase-10-mcp-server-and-integrations-page.md`; plan and report alongside. Azure AI Foundry (formerly Phase 9.3) is a backlog item with its region and quota risks noted; the Render / Neon retirement remains an open decision.
