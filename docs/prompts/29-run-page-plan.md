> *Plain-language summary of this phase: see [the build story](README.md#entry-29), entry 29.*

# Prompt 29 — Plan: the run page

**Prompt:** `29-run-page.md`. **Scope:** the run page (Parts 1 and 2), the Guide's wording, and Part 3 (when a claim may be run again) if Dermot keeps it in this prompt. **Written:** 10 November 2026. **Status:** approved (D1 to D6; Part 3 deferred to its own prompt).

## 0. What the survey found

- **The page reads two sources and trusts one.** `RunDetailPage.tsx` loads the reconstructed run (`GET /api/runs/{id}`) and the audit rows (`GET /api/audit?correlation_id=`), but every card's state, summary and duration comes from the live SSE events alone (`_status`, `_summary`, `_duration` read `events` only). The audit rows are used only for the expanded prompt and response panels. Opened after the event there are no events, so every card is *queued* and the "Awaiting pipeline_started…" hint shows because `events.length === 0`. That is the whole of the first two failures Dermot saw.
- **An abort leaves the live cards wrong by the same cause.** On `pipeline_aborted` the page shows the banner, but `_status` still returns *running* for an agent that started and never completed, and *queued* for the rest. `AgentStatus` already has `failed` and `escalated` values with icons (✗, ⚠); nothing sets them.
- **The frontend's `PipelineResult` type is behind the API.** `GET /api/runs/{id}` returns `doc_parser_output` and `validator_output` (the backend model has carried them since Phase 4); `api/types.ts` omits both. The page never needed them; this prompt does not either (the cards read the audit rows), but the mirror is corrected.
- **What the audit trail holds, from real Azure rows** (§1 below): enough for every card in every outcome, including the abort reason. **Part 1's stop condition is not met:** `pipeline_aborted` carries `failing_agent`, `error_type` and `error_message` (sanitised, at most 500 characters), written by `_finalise_abort`. No audit payload changes.
- **`error_type` on the HTTP result is the class name only, by design** (`orchestrator/models.py`: "the message can carry unsanitised detail, so it lives in the audit vault"). The page therefore takes the message from the audit row, which is the design's intent.
- **Durations.** The live `agent_completed.duration_ms` is the agent's wall time. The audit rows hold `llm_call.latency_ms`, which is the model call alone (the Validator's retrieval is outside it; the demo fixture's is 0). The difference between consecutive rows' `created_at` is the agent's wall time to within the status write: Harborline run `f368c2c5`, Doc-Parser 1.31 s between rows against 1147 ms of model latency and a live event of about 1.3 s. §3 proposes the timestamp difference.
- **The human decision.** `api/human.py` writes one audit row (`agent='human'`, step `human_approval` or `human_rejection`, under the latest run's correlation id) and moves the claim to `settled` (approved) or `aborted` (rejected). The claim's status alone cannot say whether a person decided: `settled` is also the pipeline's auto-settle. The audit rows can, and `audit_log` is indexed by `claim_id`.
- **Where runs are started.** `POST /api/pipeline/run` and `/replay` (`api/pipeline.py`), and the MCP `run_scenario` tool (`mcp/tools.py`, `_prepare_scenario_claim`), which already refuses a claim with a run in flight by the same repository check the API uses. `scripts/verify-demo-scenarios.py` submits fresh claims and runs them once; it never re-runs a decided claim.
- **The Claims page's second-action rule does not match the backend's.** The page enables *Strict re-run* for status `settled`, `awaiting_human` or `aborted`; the backend allows replay after any terminal run, including a system abort, which leaves the claim's status at `extracted` (backlog: *Pipeline abort leaves the claim in `extracted`*). So a background claim whose run aborted shows a disabled *Strict re-run* the API would accept. Recorded in §8; Part 3 changes the primary button's label by status and leaves this rule as it is.
- **Copy and tests in place.** `copy/labels.ts` (`claimTypeLabel`, `statusLabel`, `readableFallback`) and `copy/format.ts` (`formatUsd`, `formatDateTime`) from Prompt 28; `RunDetailPage.test.tsx` mocks `useRunStream` with a controllable event list and stubs fetch so the run and audit queries 404; `AgentCard.test.tsx` builds audit entries by hand. The new tests follow both patterns.
- **Variants.** `variants.yaml` names `default`, `v1_mistral`, `v2_strict_validator`, each with a description; the page shows the raw name.
- **The MCP `explain_decision` tool** already composes plain-language outcome, coverage, settlement, guardrail and escalation explanations server-side (`mcp/explain.py`). The card sentences below say the same things in the same order, so a reader who uses both sees one story.

## 1. What a run holds after the event (real rows, Azure, 10 November 2026)

`GET /api/runs/{id}` reconstructs from the audit rows: `status`, `escalation_decision` (with `fired_rules[{name, rule_type, description, observed_value}]`), the four outputs as far as the run got (`null` beyond the abort), `aborted_agent`, `error_type`, `completed_at`. The audit rows are, in order:

| Outcome | Rows (agent / step) | What each card can show |
|---|---|---|
| **Settled** — `f368c2c5` (Harborline, 16:20Z) | orchestrator `pipeline_started` {variant, claim_id, started_at}; doc_parser `doc_extract` {output{claim_type …, narrative_summary}, llm_call{latency_ms 1147 …}}; validator `coverage_check` {verdict{covered true, confidence 0.92, policy_basis, cited_chunks}, retrieval{chunks}, llm_call{latency_ms 3206}}; adjuster `settlement_estimate` {output{recommended_settlement "82500.00", confidence 0.85, reasoning}, demo_fixture false, market_data, llm_call{latency_ms 2452}}; guardrail `output_check` {output{passed true, flags [], summary}, rule_checks, llm_flags_counted [], llm_flags_discarded [], llm_call{latency_ms 1499}}; orchestrator `escalation_decision` {escalate false, fired_rules [], reasoning}; orchestrator `pipeline_settled` {status, settlement "82500.00", completed_at, fired_rule_names []} | Every card done with its sentence and duration; header *Settled*, *Standard run*, no rules. |
| **Escalated on the ceiling** — `67bdf225` (Northwood, 4 November) | the same four agent rows (adjuster `demo_fixture` false, settlement "820000.00", confidence 0.85); `escalation_decision` {escalate true, fired_rules [{settlement_over_ceiling, threshold, "settlement > $250,000", observed_value "820000.00"}]}; `pipeline_awaiting_human` {status, settlement, fired_rule_names} | Every card done; header *Awaiting human review*; rule line "Settlement over the $250,000 ceiling: $820,000". |
| **Guardrail failure** — `e9566e92` (Coral Bay, 4 November) | adjuster row has `demo_fixture: true`, `llm_call: {note: "no model call; deterministic demo fixture", provider: "demo_fixture", latency_ms: 0}`, output recommended_settlement "1400000.00", confidence 0.82; guardrail output {passed false, flags [{kind hallucinated_citation, detail "endorsement 'Coastal Surge Rider' not in retrieved chunks", source rule}], summary "Guardrail flagged 1 issue(s): hallucinated_citation."}; `escalation_decision` fired_rules [{guardrail_failed, hard, "Guardrail output check did not pass", null}, {settlement_over_ceiling, threshold, …, "1400000.00"}]; `pipeline_awaiting_human` | Adjuster card says the fixture; Guardrail card *Failed: …* as its verdict, under the ⚠ marker, not as an abort; header *Awaiting human review* with two rule lines. |
| **Aborted** — `0aca331d` (smoke_damage) and `8c537109` (hail), both 10 November | `pipeline_started`; `doc_extract`; `coverage_check`; **no adjuster row**; orchestrator `pipeline_aborted` {status "aborted", failing_agent "adjuster", error_type "ValueError", error_message "MarketDataTable.lookup: unknown claim_type 'smoke_damage' (normalised='smoke_damage'); supported types=['fire', 'flood', 'storm_complex', 'theft', 'water_damage', 'wind']", completed_at} | Doc-Parser and Validator done; Adjuster *Failed* with the reason in plain words and that message beneath; Guardrail *Not run*; header *Aborted*. |
| **Guardrail threw** (fail-closed; no Azure instance, from `_finalise_guardrail_throw`) | three agent rows; **no guardrail row**; `pipeline_awaiting_human` {reason "guardrail_threw", error_type, error_message, fired_rule_names ["guardrail_failed"]} | Guardrail *Failed: the check itself raised an error, so the claim went to a person*; header *Awaiting human review*. Covered by a test only. |

The failing agent writes no row of its own when the error precedes its model call (the market lookup); when a model call fails the agent's row carries an `error` block, and the `pipeline_aborted` row still names the agent and the message. The page reads the orchestrator's row in both cases.

## 2. The rule for combining the two sources, and the card states

**The rule.** For each agent the audit trail is consulted first: the agent's own row means *done* with the row's summary and duration; a `pipeline_aborted` row naming it means *failed* and every agent after it *not run*; a `pipeline_awaiting_human` row with `reason: guardrail_threw` means the Guardrail *failed* in the same sense. Only when the audit trail has no row for an agent does the live stream speak: `agent_started` means *running*, otherwise *queued*. The live `pipeline_aborted` event is applied by the same function as the audit row, so an abort watched live moves the cards at once. The awaiting hint shows only while there are neither events nor audit rows and the run was started from this session.

**Card states** (`AgentStatus`, existing values, now all used): `queued` ○ "Waiting"; `running` ◐ with the description and progress bar as now; `done` ✓ with the sentence and duration; `escalated` ⚠ for the Guardrail when its verdict is *Failed* (the run went to a person, the agent did not break); `failed` ✗ with the plain-words reason and the message beneath; and a new `not_run` ∅ "Not run: the run stopped at the {Agent}". One function `deriveCards(audit, events)` returns the four states, summaries and durations; it is a pure module (`pages/runDerivation.ts`) with its own tests.

**Run not found.** Today a direct link to an unknown run shows the awaiting hint forever. The Claims page's trigger navigates with `state: { started: true }`; a page opened without that state, whose run query is 404 and whose audit list is empty, shows "Run not found." A page opened with it shows the awaiting hint until the first event or row.

## 3. Every sentence the cards and header can show (for approval)

**Card summaries** (the top line; the raw request and response stay in the expanded panel as now):

| Agent | State | Sentence |
|---|---|---|
| Doc-Parser | done | "Summarised the claim (Water damage)" — the type through `claimTypeLabel` |
| Validator | done | "Covered, confidence 0.92" / "Not covered, confidence 0.41" |
| Adjuster | done | "Recommends $82,500, confidence 0.85" |
| Adjuster | done, `demo_fixture: true` | "Recommends $1,400,000 from the fixed demonstration file, no model call, confidence 0.82" |
| Guardrail | done, passed | "Passed" — and when `llm_flags_discarded` is non-empty: "Passed; 3 objections refused" (the list beneath as now) |
| Guardrail | done, not passed (⚠) | "Failed: " + the findings, one phrase per flag kind: `hallucinated_citation` → "cited policy wording the policy does not contain"; `pii` → "personal data in the reasoning"; `bias` → "biased language in the reasoning"; joined with "; ". The flag's `detail` ("endorsement 'Coastal Surge Rider' not in retrieved chunks") is shown on the line beneath, as the refused objections are. |
| any | running | the existing description ("Retrieving policy clauses and deciding coverage with citations…") and bar |
| any | queued | "Waiting" |
| any | not run | "Not run: the run stopped at the Adjuster" |
| any | failed | "Failed: " + the plain-words reason (table below), with the audit row's `error_message` beneath in small type |

**Failure reasons in plain words**, from `error_type` and the message's shape (the code stays beneath):

| Seen | Sentence |
|---|---|
| `ValueError` whose message begins `MarketDataTable.lookup: unknown claim_type` | "the Adjuster has no market range for the claim type Smoke damage" (the type from the message, through `claimTypeLabel`) |
| `LLMProviderError` | "the model provider refused or failed the call" |
| any other | "the {Agent} raised {error_type}" |

**Guardrail threw** (fail-closed, awaiting row with `reason: guardrail_threw`): "Failed: the check itself raised an error, so the claim went to a person", message beneath.

**Durations:** seconds to one decimal, "3.4 s" (`formatSeconds(ms)` in `copy/format.ts`); the live event's `duration_ms` while live, the difference between the agent's row and the previous row's `created_at` afterwards (D2).

**Refused objections:** the quote kept in quotation marks; the reason: `no_quote` → "the model gave no quotation"; `quote_not_in_reasoning` → "those words are not in the Adjuster's reasoning"; `quote_not_a_provision` → "those words do not name a policy provision"; anything else → `readableFallback`.

**The header:** the outcome badge through `statusLabel` ("Settled", "Awaiting human review", "Aborted", "Running"); the variant as a sentence with the stored name in small monospace beside it: `default` → "Standard run", `v2_strict_validator` → "Strict Validator run", `v1_mistral` → "Mistral run", anything else → `readableFallback(variant)` + " run"; then, when the escalation decision has fired rules, a list titled "Why it went to a person" with one line per rule:

| Rule | Line |
|---|---|
| `settlement_over_ceiling` | "Settlement over the $250,000 ceiling: $820,000" |
| `validator_confidence_floor` | "Validator confidence below 0.65: 0.58" |
| `adjuster_confidence_floor` | "Adjuster confidence below 0.75: 0.70" |
| `guardrail_failed` (description "Guardrail output check did not pass") | "Guardrail check did not pass" |
| `guardrail_failed` (fail-closed description) | "Guardrail check itself failed, so the claim went to a person" |
| `claim_type_watchlist` / `claimant_watchlist` | "Claim type is on the watchlist" / "Claimant is on the watchlist" |
| `cross_jurisdictional` | "Claim spans more than one jurisdiction" |
| unknown name | the rule's own `description`, with the observed value if any |

The thresholds in those lines are typed into the copy module; a test reads `backend/app/escalation/policy.yaml` and asserts each threshold rule's `value` appears in its line, so the two cannot drift silently (D3).

All new text lives in `copy/run.ts` (new) and extensions to `copy/labels.ts` (`variantLabel`, `ruleLine`, `refusalReason`, `guardrailFinding`) and `copy/format.ts` (`formatSeconds`).

## 4. Part 3 — when a claim may be run again

**Detection of a human decision: the audit rows, not the status.** `RunsRepository.human_decision(conn, claim_id) -> Literal['approved','rejected'] | None`: `SELECT step FROM audit_log WHERE claim_id = %s AND agent = 'human' AND step IN ('human_approval','human_rejection') ORDER BY created_at DESC LIMIT 1`, on the existing `audit_log_claim_id_idx`. Why not the status: `settled` is written by the pipeline and by approval alike; `aborted` is written only by rejection today, but that is an accident of who writes it, and the project's rule is that the audit trail explains decisions. One source, one query.

**The refusal.** A shared `require_open_claim(settings, claim_id)` in `api/pipeline.py` (where `execute_run` already lives for the MCP tool to import) raises `HTTPException(409, detail=…)` for `run` and `replay`, checked after the claim exists and before the active-run check, so a closed claim is refused for the right reason even with no run in flight. Message: `claim {id} was approved by a person and is closed to further runs` / `… was rejected by a person …`. The client already surfaces `detail` (run-page error banner: "Could not start the run: claim … is closed to further runs").

**`run_scenario`.** `_prepare_scenario_claim` gains the same check through a shared `ClaimClosedError` (raised by a repository-level helper both the API and the tool call) and raises `ToolError("claim_closed: claim {id} was approved by a person and is closed to further runs")`, in the tool's existing `code: message` style (`not_found`, `run_in_flight`, `not_a_scripted_claim`). Recorded in `mcp_tool_calls` as an error outcome like the others. `docs/demo-mcp.md`'s line about running a scenario twice on the same claim gains "unless a person has decided it".

**The Claims page.** The primary button reads **Process** for status `received` and **Run again** for any other status (the claim has had a run); for a `settled` claim *Run again* first shows an inline confirmation in the row's actions cell, "This claim has already settled. Run it again?" with *Run again* and *Cancel*, no browser dialog. For a claim a person has decided, both buttons are disabled with the reason leading their tooltips: "Closed: a person approved this claim; it cannot be run again. " / "Closed: a person rejected this claim; it cannot be run again. " followed by the existing text.

**The page needs to know a person decided, and the claim list does not say so today.** Two options. **(a) Recommended:** `ClaimRecord` gains `human_decision: 'approved' | 'rejected' | null`, filled by `list_claims` and `get` from the audit rows in one grouped query (the MCP `list_claims` already computes `run_count` this way). Additive: every existing key unchanged, every endpoint returning a claim carries it. **(b)** Fetch each claim's runs on the Claims page and look for the human rows: fifty extra requests per page load and the run summaries do not carry the decision either. The field is the plan; it is a second interface-stability event, acknowledged here with the refusal.

**Interface-stability acknowledgement.** (1) `POST /api/pipeline/run/{claim_id}` and `POST /api/pipeline/replay/{claim_id}` gain a 409 refusal, message above, where there was none. (2) `ClaimRecord` (`POST /api/claims`, `GET /api/claims`, `GET /api/claims/{id}`, `POST …/human-decision`) gains `human_decision`, additive. (3) MCP `run_scenario` gains the `claim_closed` error. No audit payload, SSE event, table or setting changes; no database change (the query uses an existing index). Recorded under *Locked interface extensions* in `CLAUDE.md` at close-out.

**Tests.** Backend: `has human decision` repository test (none, approved, rejected, latest wins); `run` 409 after approval and after rejection with the message asserted; `replay` the same; the refusal comes before the active-run 409 (a closed claim with no active run is refused as closed); the field on list and get (null, approved, rejected); `run_scenario` with a decided scripted claim → `claim_closed`; the Harborline scenario still runs. **Mutation proof:** the `require_open_claim` call removed from `run` → the two run-refusal tests fail; restored, all pass. Frontend: *Process* for `received`, *Run again* otherwise; the settled confirmation (appears, *Cancel* closes it, *Run again* posts); both buttons disabled with the reason for `human_decision: 'approved'` and `'rejected'`; a 409 from the POST shown in the run page's banner (existing path).

**Should Part 3 be its own prompt?** It can be, and I recommend it is (D1). Parts 1 and 2 are frontend only and a point release; Part 3 changes two API behaviours, touches the MCP tool and the Claims page, and deserves its own plan footer, register entry and interface record. The run page can be verified in full without it, and Dermot's verification of "a claim approved and then closed to re-running" is a one-prompt check on its own. If Dermot prefers one prompt, this plan already covers it and the version becomes `0.10.2`.

## 5. Files touched and tests

| File | Change |
|---|---|
| `frontend/src/pages/runDerivation.ts` (new) | `deriveCards(audit, events)`: the four `CardState {status, summary, durationMs, failure?}`; the header's variant, outcome and fired rules from the rows or the run; pure, no React. |
| `frontend/src/pages/RunDetailPage.tsx` | Uses `deriveCards`; header sentence, rule list, run-not-found; the awaiting hint by the §2 rule; `data-testid`s `run-variant`, `fired-rules`, `run-not-found`. |
| `frontend/src/components/AgentCard.tsx` | Takes `CardState`; renders the sentence, "3.4 s", the failure message beneath, the new `not_run` icon; refused reasons in words; findings' detail line. The expanded panels unchanged. |
| `frontend/src/copy/run.ts` (new) | Every sentence in §3: summaries, failure reasons, the not-run and waiting words, the header's title for the rules, the not-found text. |
| `frontend/src/copy/labels.ts` | `variantLabel`, `ruleLine(rule)`, `refusalReason(code)`, `guardrailFinding(kind)`. |
| `frontend/src/copy/format.ts` | `formatSeconds(ms)`. |
| `frontend/src/api/types.ts` | `PipelineResult` gains `doc_parser_output`, `validator_output` (the API already returns them); `AgentStatus` gains `not_run`; Part 3: `ClaimRecord.human_decision`. |
| `frontend/src/copy/guide.ts`, `guide.test.ts` | *Try it* step 3: "…the run page opens and each card says what the agent concluded as it finishes."; `runPage`: outcomes named by their labels, "each card says what the agent concluded and how long it took"; Part 3: the second *tryMore* sentence or a new one names *Run again*. |
| `frontend/src/pages/ClaimsPage.tsx` (Part 3) | *Process* / *Run again* by status; the inline confirmation; the closed state from `human_decision`; `tooltips.ts` gains the two closed texts. |
| `backend/app/runs/repository.py` (Part 3) | `human_decision(conn, claim_id)`, `human_decisions(conn, claim_ids)` for the list. |
| `backend/app/api/pipeline.py` (Part 3) | `require_open_claim`; called by `run` and `replay`. |
| `backend/app/claims/models.py`, `repository.py` (Part 3) | `ClaimRecord.human_decision`; filled in `get` and `list_claims`. |
| `backend/app/mcp/tools.py` (Part 3) | `_prepare_scenario_claim` refuses a decided claim with `claim_closed`. |
| `docs/demo-mcp.md`, `docs/walkthrough.md` | One clause each: the decided-claim rule; the two "Screen:" outcome lines read as the badge now reads. |
| `pyproject.toml`, `uv.lock` | the version (§6). |
| `docs/BACKLOG.md` | at close-out: the run-page items of 10 November and *Agent card stuck at "running" after a pipeline abort* marked done; the *Process repeatable* item done when Part 3 ships. |
| Close-out | report, build-log entry *Prompt 29*, build-story entry 29, regeneration, register entry if anything halts or deviates, `CLAUDE.md` (status; Part 3's interface record). |

**Tests, in the existing style.**

- `runDerivation.test.ts` (new, pure): the five outcomes of §1 built from hand-made audit rows with no events — settled (four done, sentences, durations from timestamps), ceiling (rules), Guardrail failure (⚠ and the finding), aborted (failed Adjuster with reason and message, Guardrail not run), Guardrail threw; events only — started/completed/aborted sequences; rows and events together — rows win; the failure-reason table; the market-lookup message parsed to the type.
- `RunDetailPage.test.tsx`: **a finished run rendered with no live events** (fetch stubs for the run and audit; no awaiting hint; the four sentences; the header sentence and badge); **an aborted run with no live events** (the failed agent, the plain reason, the message, the later agent not run, the badge *Aborted*); **a live abort moving the cards** (events only: Adjuster started then `pipeline_aborted` → Adjuster failed, Guardrail not run, banner still shown); the Guardrail-failure run shown as *Awaiting human review* with two rule lines; run not found (no state, 404s); the awaiting hint only with `state.started`.
- `AgentCard.test.tsx`: the sentence per state including the fixture; "3.4 s"; the refused reasons in words with the quote kept; the finding detail line; `not_run`.
- `labels.test.ts`, `format.test.ts`, `run.test.ts`: every mapping; `formatSeconds(3421)` → "3.4 s", `0` → "0.0 s"; **the rule lines' thresholds asserted against `policy.yaml`** (read from disk in the test).
- `guide.test.ts`: the changed sentences and their labels.
- Part 3 as listed in §4, with the mutation proof.

Expected: frontend 92 → about 118 (Parts 1–2 about 20, Part 3 about 6); backend 527 → about 537 (Part 3 only; unchanged if Part 3 is split off).

## 6. Version

- Parts 1 and 2 alone: `0.10.1.2`, a point release, presentation only. The bump rolls a new backend image whose `/health` reports it, as Prompt 28's did.
- With Part 3: `0.10.2`, a minor release, because the API refuses something it accepted before and the claim record gains a field. The number says to a reader that behaviour changed.

Recommended: whichever D1 decides.

## 7. Deployed verification, Dermot present, on the Azure frontend

Push → CI green → both deploy workflows → Azure `/health` reports the version. Then, on the Azure frontend:

1. The three runs named at the top of the prompt opened from their claims and read: `f368c2c5` four cards done with sentences and durations, *Settled*, *Standard run*, no rule list, no awaiting hint; `0aca331d` and `8c537109` Doc-Parser and Validator done, Adjuster *Failed* "the Adjuster has no market range for the claim type Smoke damage / Hail" with the message beneath, Guardrail *Not run*, badge *Aborted*.
2. The two 4 November runs read: `67bdf225` with "Settlement over the $250,000 ceiling: $820,000"; `e9566e92` with the Adjuster's fixture sentence, the Guardrail's *Failed: cited policy wording the policy does not contain* under ⚠, the detail line, and two rule lines.
3. One scenario (Harborline) submitted and run live to a settlement: the cards fill with sentences as before and the page, reloaded afterwards, reads the same.
4. One background claim of an unsupported type run live to an abort: the Adjuster card turns *Failed* and the Guardrail *Not run* at the moment of the banner.
5. Part 3, if in this prompt: Northwood submitted, run, approved in the human review panel; on the Claims page both buttons disabled with the reason; `POST /api/pipeline/run/{id}` answered 409 with the message (curl); `run_scenario("northwood", claim_id)` through the connector refused with `claim_closed`. A settled Harborline claim's *Run again* shows the confirmation and, confirmed, starts a run.

Azure stays running throughout; `azure-stop.sh` is not run.

## 8. Contradictions and loose ends in the record

- `api/types.ts` `PipelineResult` lacks two fields the API returns (§0); corrected here.
- The Claims page's `REPLAYABLE` set (`settled`, `awaiting_human`, `aborted`) is narrower than the backend's replay rule (any terminal run), and `aborted` as a claim status is a human rejection, which Part 3 closes. Left as it is in this prompt; the only claims it affects are background claims whose runs aborted on an unsupported type, which would abort again. Noted for the claim-page prompt, where the runs are listed and the rule can be exact.
- `AgentStatus` has carried `escalated` and `failed` since Phase 6 with nothing setting them; both are used from here.
- `docs/walkthrough.md` twice says the screen shows `awaiting_human`; after this prompt the badge reads *Awaiting human review*. Two lines updated.
- `docs/demo-mcp.md` says a scenario can be run twice on the same claim with `run_scenario(name, claim_id)`; true unless a person has decided the claim (Part 3). One clause added when Part 3 ships.
- The Guide's *Reading a run page* says "Each shows what it produced and how long it took"; still true, and it now names the outcomes by their labels.
- `docs/test-evidence.md`'s frontend table predates Prompt 28's counts; out of scope, noted.
- The backlog item *Pipeline abort leaves the claim in `extracted`* is unchanged by this prompt: the Claims page shows such a claim as *Summarised* with *Run again*. The decision it asks for (a `failed` status, or back to `received`) is a locked-interface event and is not taken here.

## 9. Risks

- **Timestamps as durations** (D2): the difference includes the status write and the row write, a few tens of milliseconds; the live value is used while live, so the two can differ by that much on a reload. Acceptable; stated on the card's title attribute as "from the audit trail".
- **Parsing an error message** for the market-lookup sentence couples the page to the message's shape; the fallback sentence ("the Adjuster raised ValueError") keeps the card truthful if the shape changes, and the test pins the shape used.
- **The settled confirmation** adds a step the Guide must describe (one sentence).
- **Function size.** `RunDetailPage` sheds its five private helpers into `runDerivation.ts`; `AgentCard` gains a `CardSummary` component so the main function stays under 50 lines.

## 10. Decisions requested

- **D1 Part 3 as its own prompt.** Parts 1, 2 and the Guide here as `0.10.1.2`; Part 3 as Prompt 30 with its two interface changes. *Recommended: yes.*
- **D2 Durations after the event** from the difference between consecutive audit rows' `created_at` (the agent's wall time), not `llm_call.latency_ms` (model time only, 0 for the fixture). *Recommended: yes.*
- **D3 Rule-line thresholds** typed into the copy module and asserted against `policy.yaml` by a test that reads the file. *Recommended: yes.*
- **D4 Guardrail verdict marker.** The Guardrail card shows ⚠ (`escalated`) when its verdict is *Failed*, distinct from ✗ (`failed`) for an agent that broke. *Recommended: yes.*
- **D5 Run not found** decided by the navigation state (`state.started` from the Claims page trigger) plus a 404 and an empty audit list. *Recommended: yes.*
- **D6 The sentences in §3** as drafted, including "from the fixed demonstration file, no model call" for the fixture. *Recommended: yes, with any wording changes.*
- **D7 (Part 3 only) `human_decision` on `ClaimRecord`**, additive, filled from the audit rows. *Recommended: yes.*
- **D8 (Part 3 only) Check order:** the closed-claim refusal before the active-run refusal. *Recommended: yes.*

No optional items.

---

**Approved by Dermot, 11 November 2026 (2026-11-11T09:17Z).** D1 to D6 as recommended; Part 3 (when a claim may be run again) becomes its own prompt, and D7 and D8 wait for it. One wording change: a confidence is shown as a percentage in brackets — "Covered (92% confident)", "Recommends $82,500 (85% confident)" — and the escalation lines that carry a confidence take the same form. Verbatim: *"Approved: D1 to D6 as recommended, with Part 3 as its own prompt; D7 and D8 wait for it. One wording change: show confidence as a percentage in brackets, \"Covered (92% confident)\", \"Recommends $82,500 (85% confident)\", and the same form in the escalation lines where a confidence appears. Commit the prompt and plan, then build Parts 1 and 2."*
