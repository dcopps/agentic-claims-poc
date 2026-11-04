> *Plain-language summary of this phase: see [the build story](README.md#entry-24), entry 24.*

# Phase 10 — Report: an MCP server over the audit trail, and an Integrations page that shows it working

**Prompt:** `24-phase-10-mcp-server-and-integrations-page.md`. **Plan:** `24-phase-10-mcp-server-and-integrations-page-plan.md` (approved 2 November 2026). **Version:** `0.9.1.2 → 0.10.0`, with point releases `0.10.0.1` and `0.10.0.2` during the verification. **Completed at:** 2026-11-04T11:45Z. **Status:** complete; verified on both deployed stacks and through Claude Desktop's connector.

## What was built

The inventory is in the build log (*Phase 10*). In one paragraph: an MCP server inside the backend (`backend/app/mcp/`), mounted at `/mcp` as an exact-path route only when `MCP__SHARED_TOKEN` is set, behind a constant-time bearer guard; nine tools (eight read, `run_scenario` the one action, limited to the three scripted names or an existing claim carrying that scenario's tag), two prompts and the policy resource; `explain_decision` composed from audit rows with every section tagged by its row; every call recorded on every exit path in `mcp_tool_calls` (migration 0003), a structured log line and the live feed; `GET /api/mcp/tools` (the catalogue from the server object) and `GET /api/mcp/activity` (SSE, replay then live); the *Integrations* and *Guide* pages, *Copy question for Claude* on Run Detail, the Guardrail card's *Refused claims* line; the token wired through Bicep to Key Vault and the Container App; `scripts/regenerate-build-story.py`.

## Decisions at the gate (Dermot, 2 November 2026)

D1–D6 and D8 as the plan recommended; D7 with two copy changes (Harborline "at a figure a little below the claimed amount"; refused claims pointed at the Guardrail card); O1, O2 and O4 in scope; O3 and O5 to the backlog. Execution in four commits, stopping before the deployed verification.

## Tests

Backend **521 passed, 0 failed, 18 skipped** at close (429 / 15 before the phase): the MCP suites (auth 14, tools 19, explain 12, tool log 8, activity 5, scenarios 7, API 5, settings 4, promotions 4, e2e 3 gated), the regeneration script (6) and the logging setup (4). Frontend **54 passed** (36 before). `ruff`, `mypy --strict`, ESLint, `tsc`, `vite build` and `az bicep build` clean.

**Mutation proofs (applied, observed, reverted).** (1) `BearerGuard._authorised` returning `True` in place of the `compare_digest` call: `test_wrong_token_is_refused` fails, eight pass — the missing-header and other-scheme refusals sit before the comparison, so those tests still pass, which is the correct reading (the plan had expected two failures). (2) `mount_mcp` given a dummy token when none is set: `test_unset_token_means_no_route` and `test_blank_token_counts_as_unset` fail, seven pass.

## Findings and deviations from the plan

- The prompt's worked example attached *"the $1.5M ceiling"* to run `0cdfa114`; on the Render ledger that phrase belongs to the Northwood run `6197d116`, and `0cdfa114`'s refused claim is *"inventory valuation and depreciation"*. The plan, the fixture `backend/tests/fixtures/mcp/run_0cdfa114.json` and the tests use the recorded rows.
- "Subscribe first, then read the replay" needed the activity bus to register a subscriber eagerly; `ActivityBus.subscribe()` returns a registered `Subscription` rather than being a generator.
- `_register_read_tools` was split into four functions to respect the 50-line limit; `verify_chain` is registered by name because the function cannot shadow the verifier it wraps.
- **Two point releases during the verification.** `0.10.0.1`: the guard logs every refusal with its reason (`header_absent` / `scheme_not_bearer` / `token_mismatch`), never the value, after Claude's connector was refused and the record could not say whether a header had arrived. `0.10.0.2`: that line logged nothing on Azure, because nothing had ever configured the root logger — locally the MCP SDK's `basicConfig` installed a console handler at INFO, but with the Application Insights distro's handler already on the root that call is a no-op, so every application INFO line on Azure (tool-call log lines included) had been dropped since Phase 9.2. `backend/app/logging/setup.py` now applies `Settings.log_level` (declared in Phase 0, never read before) and adds a console handler when none writes to the console.

## Deployed verification (plan §8), 2 and 4 November 2026, Dermot present

**Azure.** Postgres was `Stopped`; `azure-start.sh` took about 25 minutes to see it `Ready`. Migration 0003 applied to the Azure server (91 audit rows and 22 claims unchanged) and to Neon (118 audit rows unchanged), hostnames echoed only. `azure-deploy.sh what-if` showed the three expected real changes (the vault secret, the Container App's secret reference and `MCP__SHARED_TOKEN` entry, `minReplicas` 1 → 0 drift) plus the known noise; `deploy` generated the token and stored it as `mcp-shared-token` (deployment `claimsai-dev-3372130-20261102T184904Z`); the warm replica was re-set. `/mcp` refused without a token (401 with the challenge) and with a wrong one; the catalogue reported `mounted: true`; the official client with the vault's token passed 3/3.

**Claude's connector.** Refused six times on 2 November; with the diagnostic live, its next refusal read `header_absent`: the connector form's detection probe sends no header, is refused, runs OAuth discovery (`/.well-known/oauth-protected-resource[/mcp]`, `/.well-known/oauth-authorization-server`, all 404) and reports a failure; saved with `authorization: Bearer <token>` it connected at 20:21 UTC and Claude Desktop's first question was tool call 4, `list_claims`, in 76 ms.

**The three scenarios on Azure**, verified read-only from the database and the tool-call log on 4 November:

| Scenario | Run | Call | Outcome | Rules | Guardrail |
|---|---|---|---|---|---|
| Harborline (official client, 11:08) | `cc53d855` | 9 | `settled`, $85,000.00 | none | passed; no model claim raised |
| Northwood (Claude Desktop, 11:28) | `67bdf225` | 12 | `awaiting_human`, $820,000.00 | `settlement_over_ceiling` | passed; no model claim raised |
| Coral Bay (Claude Desktop, 11:28) | `e9566e92` | 13 | `awaiting_human`, $1,400,000.00 | `guardrail_failed`, `settlement_over_ceiling` | failed on the rule-engine `hallucinated_citation` flag; demo fixture |

Seven audit rows each, the seven steps in order; chain `ok` over 112 rows; 25 claims. The log holds `run_scenario` for all three (ok, 17.2 s / 9.1 s / 6.7 s — the pipeline runs in about nine seconds on Azure), `explain_decision` for Harborline (call 10) and Coral Bay (call 14), and `verify_chain` for Harborline (call 11); no `explain_decision` was asked for Northwood. The Azure Integrations page showed the feed with the day's calls on 2 November.

**Render.** After the dashboard variable was corrected, `/health` 0.10.0.2, catalogue `mounted: true`, 401 without and with a wrong token, the official client 3/3, and `scripts/verify-demo-scenarios.py` reproduced all three scenarios: *OK: all three demo scenarios reproduced the expected outcomes.*

## Interface-stability events (acknowledged in the plan)

Table `mcp_tool_calls` (migration 0003, additive); surfaces `/mcp`, `GET /api/mcp/tools`, `GET /api/mcp/activity`; settings block `mcp`; Key Vault secret `mcp-shared-token` and env `MCP__SHARED_TOKEN`. Unchanged: every existing HTTP and SSE shape, every audit payload, the chain, the agents, the pipeline, `Dockerfile`, `render.yaml`.

## Suggestions (not in scope)

- The connector form's header-less detection probe will always show one `header_absent` refusal per set-up; a line on the Integrations page saying so would save the next person the search.
- `Settings.log_level` now works; a `backend.app.mcp.calls` line per call doubles the table on every deployment. If the Azure log volume ever matters, route that logger to the exporter only.
- Backlog items from this phase: O3 (one source for the scripted scenarios), O5 (`Last-Event-ID` on the feed), the Render / Neon retirement decision, Azure AI Foundry.
