# Demo: asking the system about a claim through Claude (two minutes)

> *Plain-language context: [the build story](prompts/README.md#entry-24), entry 24, and the register entry [R-20](decision-register.md#r-20).*

Two windows. On the left, the web interface's **Integrations** page on the deployment you are showing (the Azure frontend or the Vercel one); its *Live activity* table is empty or shows earlier calls. On the right, Claude with the claims connector enabled (Claude's *Customize › Connectors*, or Claude Code with the same endpoint — the Integrations page's *Connection* card has both snippets). Everything Claude says comes from the audit trail; everything it asks appears in the left window as it asks it.

**Before you start.** Warm both ends: open the Integrations page (it wakes a sleeping backend), and on Azure run `scripts/azure-start.sh` first. Have the connector already added; adding it live costs a minute of clicking.

| Step | Say in Claude | What the audience sees |
|---|---|---|
| 1 | *Using the claims MCP server, run the harborline scenario.* | A `run_scenario` row appears on the left with its latency once the pipeline finishes (about a minute). Claude reports the run settled, the figure, and the correlation id. If you open the Run page for that id in a third tab you can watch the four cards complete live. |
| 2 | *Explain that run, and tell me whether its audit chain verifies.* (Or paste the question the Run page's *Copy question for Claude* button gives you.) | `explain_decision` and `verify_chain` rows on the left. Claude gives the Validator's verdict and the passages it saw, the Adjuster's figure and range, and the Guardrail's result. **The talking point:** if the model claimed one of the Adjuster's phrases was a policy citation, Claude shows the quote beside the code's reason for refusing it, and the claim settled anyway. |
| 3 | *Compare runs 2c42cf40-… and 0cdfa114-… on the same claim.* (the two Harborline runs of 30 October on the Render deployment: an escalation under `0.9.1.1` in the morning, a settlement under `0.9.1.2` in the afternoon) | A `compare_runs` row. Claude reports the diff: escalation changed, the guardrail result changed, the settlement did not — the behaviour change the Phase 9.2.2 release made, on one claim in one day. |
| 4 | *What exactly did the Guardrail agent send to the model on that run?* | A `get_audit_trail` row with `include_prompts: true`. Claude quotes the recorded system and user prompt. |

**What to point at on the left.** Every row names the tool, its arguments, the run or claim it concerned, the caller (the token's label, never its value), the outcome and the latency. The same rows are in the `mcp_tool_calls` table and in the backend's structured log: this is the record of who asked what of the system. The *Tool catalogue* above the feed is generated from the server's own definitions, with the one action tool marked `action`; the *Connection* card says what the server does and does not permit.

**If something does not happen.** A sleeping backend (Render's free tier, or Azure at zero replicas) makes the first call slow or makes the connector time out once; retry. If Claude's connector refuses the token, the account may not have the *Request headers* field (it is in beta); use the Claude Code command from the *Connection* card instead. If `run_scenario` times out in the connector, the run still completes — ask Claude to call `get_run` with the id, or open the Run page.

**The comparison pair.** `compare_runs` needs two runs of the same claim. On Render, the Harborline claim `08454ce5` holds the pair above. On Azure, use any claim with two runs (`list_claims` shows `run_count`), or run the scenario twice on the same claim with `run_scenario(name, claim_id)`.
