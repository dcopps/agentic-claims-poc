# How the system was tested

This document traces, for every phase of the build, what was planned to be tested, what was built to test it, and what the result was. It is written for a reader who asks "how do I know this was tested?" and does not want to search twenty-four plans, twenty-four reports and the build log to find out. It claims nothing the record does not support: where a plan stated no count, or a phase recorded no proof, the table says so.

It was produced by prompt 25 on 5 November 2026 and records a fresh run of both test suites made that day. Nothing in the code or the tests was changed to produce it. The plain-language record of incidents and decisions is the [decision register](decision-register.md); the plain-language account of the build is [the build story](prompts/README.md); the engineer's chronological record is the [build log](build-log.md). Terms in *italics* on first use are defined in the register's glossary.

Parts 1 and 4 are written for a reader who is not an engineer. Parts 2, 3, 5 and 6 are the engineer's detail.

## 1. How testing works here, in plain language

**What an automated test is, and why there are hundreds.** An *automated test* is a small program that runs one part of the system with a known input and fails if the result is not what was promised. The system has 593 of them (521 that run on every change, 18 that need a live model or a running server, and 54 for the web pages, as of 5 November 2026). There are that many because the project's rule is that every guard in the code, every place where the system refuses bad input or stops rather than guessing, has a test that triggers it and checks the message it gives. A change that breaks any promise the system has made fails a test before the change is committed.

**Four kinds of evidence.** The tests fall into four groups, and they prove different things.

- *The backend tests* exercise the service: the four *agents*, the *orchestrator*, the *audit trail*, the escalation rules, the database and the new *MCP* endpoint. They run against a local database that the test harness empties before each test. Since Phase 8.5 the harness refuses to run against any live database host, after an incident in which it emptied one ([R-02](decision-register.md#r-02)). Where an agent would call a *language model*, the tests put a stand-in in its place that returns a known answer, so the tests are fast, free and repeatable, and so they test the system's handling of an answer rather than the model's choice of one.
- *The frontend tests* render each web page and component with the service replaced by recorded answers, and check what appears on the page: the right cards, the right badge, the right link, the right text copied to the clipboard.
- *The replay corpus* is the one place the live model is tested. Seven recorded Guardrail inputs, taken from real runs on the *deployed stacks*, are sent again to the current model with the current instructions, and the verdict is compared with the one expected. It costs a few cents and takes under a minute, so it is run by hand before every demonstration, not on every change.
- *The deployed verification passes* run *the three scripted scenarios* on the live installations, by a script or by a person at the screen, and check the outcome of each, the seven audit entries each run writes, and that the audit chain still verifies. They are the only test of the whole system end to end with real models.

**What a mutation proof is.** A test that passes proves little on its own; it might pass for the wrong reason. A *mutation proof* removes the guard the test exists for, runs the test and watches it fail, then puts the guard back. Only then is the test known to catch the fault. Seven phases recorded one; the sentence from each report is in part 3. The earliest phases did not record any.

**What CI is, and why a deployment waits for it.** *Continuous integration (CI)* is a shared build server that runs every check (style, types, tests) on every change pushed to the repository, in a clean environment that has none of a developer's local state. Since Phase 9.2 the two automatic deployments to Azure are triggered only by a green CI run on the main branch, so nothing reaches the live Azure installation without the full suite passing somewhere other than a developer's machine. Part 6 describes the workflows and the period during which CI was red.

**What is not tested automatically.** Stated plainly, because a reader should not infer more than the record supports:

- The model's behaviour, except through the seven replay cases and the deployed passes. The replay is a regression check on a small fixed set, not a scored evaluation (part 4).
- The path a person takes through the real screens in a browser. The page tests render components in isolation; the deployed passes through a frontend are done by a person. A proposal to automate it is in the backlog (part 5).
- The operational shell scripts (start, stop, deploy) are syntax-checked only; `shellcheck` was not available on the build machine and is recorded as not run.
- The infrastructure templates are compiled and linted; the check that they match the live Azure state (a "what-if") is run by hand before each deployment and recorded in the build log.
- The two deploy workflows are exercised only by real pushes; their behaviour is recorded in the build log, not asserted by a test.
- The wording of the prompts sent to the models is checked for shape (the required sections and rules are present), not for effect; the effect is what the replay corpus watches.
- The 18 gated tests are not part of any automatic run. Two of them exercise the retained Mistral path and cannot pass on the project's current Mistral account ([R-06](decision-register.md#r-06)).

## 2. The test suites as they stand

### Backend

| | |
|---|---|
| Framework | pytest, run through `uv`; the `pytest` options and test path are in `pyproject.toml` |
| Database | `agentic_claims_test` on local PostgreSQL, from `TEST_DATABASE_URL` in `.env.test`; the harness refuses `*.neon.tech` and `*.postgres.database.azure.com` (R-02) |
| Command | `uv run pytest` |
| Fresh run | **521 passed, 0 failed, 18 skipped** in 11.06 s, 2026-11-05T17:51Z, commit `ed24e5d` |
| Also in CI | `uv run ruff check .` and `uv run mypy backend`, both clean on the same commit |

**The 18 skipped tests**, every one of them gated on an environment variable so that the default run costs nothing and needs no key:

| Count | Gate | What they are |
|---|---|---|
| 1 | `RUN_EMBEDDING_TESTS=1` | end-to-end indexing of the policy text through the real embedding model (`test_index_policy.py`) |
| 6 | `RUN_LLM_E2E_TESTS=1` and a key | one live call each for the Validator, Doc-Parser, Adjuster, Guardrail, the full pipeline and the agent test bench. **The Validator and Adjuster cases ask for `MISTRAL_API_KEY`**: they exercise the retained Mistral path, which the project's free-tier account cannot use since September 2026 ([R-06](decision-register.md#r-06)), so they would fail with the provider's refusal even when the key is set. The other four need `ANTHROPIC_API_KEY`. |
| 8 | `RUN_LLM_E2E_TESTS=1` and `ANTHROPIC_API_KEY` | the replay corpus: the seven recorded fixtures, plus Coral Bay replayed with the rule engine's findings blanked (`test_guardrail_replay.py`, part 4) |
| 3 | `RUN_MCP_E2E_TESTS=1`, `MCP_E2E_URL`, `MCP_E2E_TOKEN` | the official MCP client over HTTP against a running backend (`test_mcp_e2e.py`) |

**The 59 test modules.** Counted as `backend/tests/test_*.py`; the directory also holds `conftest.py` (fixtures and the live-host refusal), `__init__.py`, and two shared fixture modules, `guardrail_replay_fixture.py` and `mcp_fixture.py`, which contain no tests. "Added in" is the phase whose commit first added the file; a file is often extended by later phases. "Functions" counts `test_` functions in the file; parametrised functions expand to more collected cases, which is why 59 modules yield 539 collected tests.

| Module | Added in | Functions | What it guards |
|---|---|---|---|
| `test_health.py` | 0 | 1 | `/health` answers with the package version |
| `test_settings.py` | 0 | 6 | the settings model's defaults and the environment override |
| `test_audit_canonical.py` | 1 | 7 | canonical JSON for hashing is deterministic across key order and rejects naive datetimes, Decimals, sets and bytes |
| `test_audit_chain.py` | 1 | 8 | the SHA-256 chain primitive: genesis constant, round-trip, input guards, a golden chain |
| `test_audit_writer.py` | 1 | 7 | the writer links each row to the previous hash, refuses an unknown claim and bad inputs, round-trips JSONB |
| `test_audit_verify.py` | 1 | 4 | chain verification: empty, clean, payload tampered, hash tampered |
| `test_index_policy.py` | 1 | 9 | the policy chunker; plus the gated end-to-end embedding run |
| `test_schema.py` | 1 | 5 | the migrated schema: columns, indexes, the foreign key, the vector extension |
| `test_seed_claims.py` | 1 | 9 | the synthetic claim generator: counts, scenario coverage, reproducibility, refusal to overwrite without the flag |
| `test_settings_phase1.py` | 1 | 13 | database, embedding and model settings: aliases, scheme validation, locked identifiers |
| `test_api_logger.py` | 2 | 13 | every model call is written as one canonical record; disabled logger writes nothing |
| `test_llm_provider_anthropic.py` | 2 | 5 | the Anthropic wrapper: key required, system and user separated, SDK errors translated, empty content refused |
| `test_llm_provider_mistral.py` | 2 | 5 | the Mistral wrapper, the same contract |
| `test_prompt_loader.py` | 2 | 16 | prompts are loaded from files only: missing, empty and oversized files refused; variant resolution |
| `test_settings_phase2.py` | 2 | 13 | logging, retrieval and per-model settings: defaults and bounds |
| `test_validator.py` | 2 | 14 | the Validator: retrieval substituted into the prompt, the parsed decision, every malformed-answer guard, the recorded provider and model; one gated live call |
| `test_validator_prompts.py` | 2 | 3 | the Validator's prompt files hold the required sections |
| `test_adjuster.py` | 3 | 14 | the Adjuster: market range enforced, out-of-range answers refused, the recorded reasoning; one gated live call |
| `test_adjuster_prompts.py` | 3 | 2 | the Adjuster's prompt files hold the required sections |
| `test_doc_parser.py` | 3 | 11 | the Doc-Parser: narrative summarised, fields from the claim record, every malformed-answer guard; one gated live call |
| `test_doc_parser_prompts.py` | 3 | 2 | the Doc-Parser's prompt files hold the required sections |
| `test_guardrail.py` | 3 | 27 | the Guardrail's rule engine (PII, bias, hallucinated citation) and its handling of the model's answer; the Phase 8.6.1 regression cases; one gated live call |
| `test_guardrail_prompts.py` | 3 | 4 | the Guardrail's prompt files: citation definition, the required `quote`, the output format |
| `test_market_data.py` | 3 | 14 | the market-range table: lookup per claim type and amount, boundaries, unknown types refused |
| `test_api_pipeline.py` | 4 | 6 | the run endpoint and the event stream contract |
| `test_escalation_policy.py` | 4 | 20 | the escalation rules: each hard rule, each threshold, OR semantics, every rule that fired is recorded |
| `test_pipeline_event_bus.py` | 4 | 8 | the in-process event bus the stream reads from |
| `test_pipeline_orchestrator.py` | 4 | 12 | the orchestrator runs the four agents in order, writes the audit rows, aborts on a failed agent |
| `test_pipeline_scenarios.py` | 4 | 5 | the three scripted scenarios end to end with stand-in models reach their locked outcomes; one gated live pipeline |
| `test_api_claims_runs.py` | 5 | 12 | the claims, runs and replay endpoints |
| `test_claims_repository.py` | 5 | 13 | a claim is persisted before any agent runs; submission validation |
| `test_runs_repository.py` | 5 | 11 | past runs are reconstructed from the audit log alone |
| `test_variants.py` | 5 | 14 | the replay variant mechanism: registry, settings resolution, overrides |
| `test_agent_probe.py` | 6 | 4 | the agents' no-audit probe path for the test bench |
| `test_agents_test_api.py` | 6 | 10 | the agent test bench API and the prompt display; one gated live call |
| `test_audit_api.py` | 6 | 5 | the audit list and whole-ledger verification endpoints |
| `test_human_decision_api.py` | 6 | 7 | approval and rejection by a person: recorded as audit rows, terminal states enforced |
| `test_migration_0002.py` | 6 | 4 | the audit `agent` constraint extension, including the documented downgrade hazard |
| `test_anonymisation.py` | 7 | 2 | no client name in code, docs, fixtures or infrastructure |
| `test_demo_fixture.py` | 7 | 5 | the guardrail scenario's deterministic fixture is used only for its claim and is recorded as such |
| `test_audit_persistence.py` | 8.4 | 4 | audit rows survive the agent's own connection close (the R-01 regression) |
| `test_db_isolation.py` | 8.5 | 5 | the test-database resolution and the refusal of live hosts (R-02) |
| `test_agent_wiring.py` | 8.6 | 4 | each agent is built with the provider its selector names, through the real factory |
| `test_settings_providers.py` | 8.6 | 11 | the per-agent provider selectors and model resolution; unknown values refused with the allowed list |
| `test_telemetry.py` | 9.2 | 5 | Application Insights export is a no-op without a connection string and installs when one is set |
| `test_guardrail_replay.py` | 9.2.1 | 5 | the replay corpus: fixture contract, the corpus tripwire, a malformed fixture refused; the gated live replays |
| `test_guardrail_llm_flags.py` | 9.2.2 | 14 | a model's citation flag counts only when code finds its quote in the reasoning and the quote has a provision's shape; every discard reason |
| `test_mcp_auth.py` | 10 | 11 | `/mcp` exists only with a token; a missing, wrong or non-bearer token is refused and the refusal is logged by reason, never by value |
| `test_mcp_tools.py` | 10 | 21 | the nine tools through the SDK's in-memory client against the test database |
| `test_mcp_explain.py` | 10 | 12 | the decision explanation is composed from audit rows, every section tagged with its row |
| `test_mcp_tool_log.py` | 10 | 8 | every tool call is recorded on every exit path: row, log line, feed |
| `test_mcp_activity.py` | 10 | 5 | the activity bus broadcasts to every subscriber and drops on a full queue |
| `test_mcp_scenarios.py` | 10 | 4 | `run_scenario` accepts the three names and nothing else |
| `test_mcp_api.py` | 10 | 5 | the tool catalogue and the activity feed endpoints |
| `test_mcp_e2e.py` | 10 | 3 | gated: the official client over HTTP |
| `test_phase10_promotions.py` | 10 | 4 | the four functions promoted out of the routers keep their behaviour |
| `test_settings_mcp.py` | 10 | 4 | the `mcp` settings block; a blank token counts as unset |
| `test_regenerate_build_story.py` | 10 | 6 | the build-story regeneration script: unchanged, rewritten, refused |
| `test_logging_setup.py` | 10 (0.10.0.2) | 4 | the root logger takes its level from settings and gains a console handler only when none writes to the console |

### Frontend

| | |
|---|---|
| Framework | Vitest with Testing Library, in a simulated browser (jsdom); `fetch` is stubbed per test, and since Phase 10 a mock `EventSource` stands in for the live feed |
| Command | `cd frontend && npm test -- --run` |
| Fresh run | **14 files, 54 passed, 0 failed, 0 skipped** in 4.16 s, 2026-11-05T17:49Z, commit `ed24e5d` |
| Also in CI | `npm run lint` and `npm run typecheck` |

| File | Added in | Tests | What it guards |
|---|---|---|---|
| `App.test.tsx` | 0 | 4 | the navigation and the routes: claims landing, audit viewer, test bench, comparison view |
| `components/ClaimForm.test.tsx` | 5 | 3 | the submit form: prefill from a demo claim, the POST on submit |
| `copy/tooltips.test.ts` | 5 | 1 | the tooltips name the production equivalents |
| `components/AgentCard.test.tsx` | 6 | 11 | an agent's card: the recorded prompt and response from the audit entry, the waiting and integrity-error states, the running progress bar, the refused-claims list |
| `components/AgentTestPanel.test.tsx` | 6 | 2 | the test bench panel: runs an agent, refuses malformed JSON without calling the API |
| `components/HumanReviewPanel.test.tsx` | 6 | 3 | the review panel: shows the Adjuster's evidence, requires a reviewer name, submits the decision |
| `components/ui.test.tsx` | 6 | 4 | the status badge colours |
| `pages/AuditPage.test.tsx` | 6 | 2 | the audit viewer lists entries and shows a verified or broken chain |
| `pages/ClaimsPage.test.tsx` | 8 | 2 | *Process* navigates at once and fires the run in the background |
| `pages/RunDetailPage.test.tsx` | 8 | 7 | the run page: queued cards, error banners, the full correlation id, the copy buttons, the audit link |
| `copy/guide.test.ts` | 10 | 5 | the Guide's copy: the four public links, the glossary definition, the three scenarios, one screen |
| `hooks/useMcpActivity.test.ts` | 10 | 3 | the feed hook: newest first, duplicates dropped, capped at 100, malformed frames ignored |
| `pages/GuidePage.test.tsx` | 10 | 1 | the Guide page renders its blocks and links |
| `pages/IntegrationsPage.test.tsx` | 10 | 6 | the Integrations page: every tool the backend reports is rendered with its kind; the unconfigured state; the feed; the copied command never contains a token |

Three Phase 5 component tests (`ClaimList`, `CompareView`, `ProgressStrip`) were removed in Phase 6 when those components were replaced.

## 3. Traceability: plan → tests → result, phase by phase

One row per phase. The second column links the plan's testing section where it has one; where it has none the row says so and links the nearest heading. *Predicted* is the plan's own figure, quoted as written (a range stays a range); *recorded* is the report's. *Files* are the test files the phase's build-log entry names as added or changed. *Mutation proof* quotes the report, or says "none recorded". The build-log column links the entry.

| Phase | Plan and testing section | Test files added or changed | Predicted | Recorded | Mutation proof | Build log |
|---|---|---|---|---|---|---|
| 0 | [`01-…-plan.md`](prompts/01-phase-0-repository-scaffold-plan.md) — no testing section; nearest [*CI*](prompts/01-phase-0-repository-scaffold-plan.md#ci-githubworkflows) | `test_health.py`, `test_settings.py`; `App.test.tsx` | none stated | 7 backend, 2 frontend | none recorded | [Phase 0](build-log.md#2026-05-08--phase-0-repository-scaffold) |
| 1 | [*Test surface and pass-rate expectations*](prompts/02-phase-1-data-layer-plan.md#test-surface-and-pass-rate-expectations) | `test_audit_canonical.py`, `test_audit_chain.py`, `test_audit_writer.py`, `test_audit_verify.py`, `test_index_policy.py`, `test_schema.py`, `test_seed_claims.py`, `test_settings_phase1.py` | "~46–50 tests" new | 65 passing, 1 skipped; 2 frontend | none recorded | [Phase 1](build-log.md#2026-05-08--phase-1-data-layer-and-settings-infrastructure) |
| 2 | [*Testing strategy — concrete recommendation*](prompts/03-phase-2-llm-gateway-and-validator-plan.md#testing-strategy--concrete-recommendation) | `test_api_logger.py`, `test_llm_provider_anthropic.py`, `test_llm_provider_mistral.py`, `test_prompt_loader.py`, `test_settings_phase2.py`, `test_validator.py`, `test_validator_prompts.py` | listed per module, not totalled | 122 passing, 2 skipped; 2 frontend | none recorded | [Phase 2](build-log.md#2026-05-11--phase-2-llm-gateway-and-validator-agent) |
| 3 | [*4. Testing strategy*](prompts/04-phase-3-remaining-agents-plan.md#4-testing-strategy) | `test_adjuster.py`, `test_adjuster_prompts.py`, `test_doc_parser.py`, `test_doc_parser_prompts.py`, `test_guardrail.py`, `test_guardrail_prompts.py`, `test_market_data.py` | "38 new tests … plus 3 opt-in real-call tests"; "122 → 160" | 178 passing, 5 skipped; 2 frontend | none recorded | [Phase 3](build-log.md#2026-05-11--phase-3-remaining-agents-doc-parser-adjuster-guardrail) |
| 4 | [*11. Testing strategy (target ~40–48 new tests)*](prompts/05-phase-4-pipeline-orchestrator-plan.md#11-testing-strategy-target-4048-new-tests) | `test_api_pipeline.py`, `test_escalation_policy.py`, `test_pipeline_event_bus.py`, `test_pipeline_orchestrator.py`, `test_pipeline_scenarios.py` | "~40–48" | 225 passing, 6 skipped ("47 passing + 1 gated" new); 2 frontend | none recorded | [Phase 4](build-log.md#phase-4--pipeline-orchestrator) |
| 5 | [*9. Testing strategy (target ~45–55 new backend + ~12 frontend)*](prompts/06-phase-5-decoupling-and-replay-plan.md#9-testing-strategy-target-4555-new-backend--12-frontend) | `test_api_claims_runs.py`, `test_claims_repository.py`, `test_runs_repository.py`, `test_variants.py`; `ClaimForm`, `ClaimList`, `CompareView`, `ProgressStrip`, `tooltips` tests (from the commit; the build-log entry lists areas, not files) | "~45–55 new backend + ~12 frontend" | 277 passing, 6 skipped; 13 frontend ("52 backend + 11 frontend" new) | none recorded | [Phase 5](build-log.md#phase-5--decoupling-and-replay) |
| 6 | [*5. Testing strategy (~30–40 backend, ~25–35 frontend)*](prompts/07-phase-6-frontend-polish-plan.md#5-testing-strategy-3040-backend-2535-frontend) | `test_agent_probe.py`, `test_agents_test_api.py`, `test_audit_api.py`, `test_human_decision_api.py`, `test_migration_0002.py`, `test_prompt_loader.py`; `AgentCard`, `AgentTestPanel`, `HumanReviewPanel`, `ui`, `AuditPage` tests | "~30–40 backend, ~25–35 frontend" | 311 passing, 7 skipped; 22 frontend ("34 backend + ~18 frontend" new) | none recorded (the word in this phase's files is React Query's `useMutation`) | [Phase 6](build-log.md#phase-6--frontend-polish--supporting-backend-endpoints) |
| 7 | [*5. Testing / CI / deps*](prompts/08-phase-7-demo-polish-and-documentation-plan.md#5-testing--ci--deps) | `test_anonymisation.py`, `test_demo_fixture.py` | "~6–8 new tests" | 326 passing, 7 skipped; 22 frontend ("15 backend" new) | none recorded | [Phase 7](build-log.md#phase-7--demo-polish-and-documentation) |
| 8 | [*3. Testing strategy (~13 new/updated)*](prompts/09-phase-8-demo-polish-fixes-plan.md#3-testing-strategy-13-newupdated) | `test_guardrail.py`, `test_seed_claims.py`; `ClaimsPage`, `RunDetailPage` tests | "~13 new/updated" | 330 passing, 7 skipped; 30 frontend | none recorded | [Phase 8](build-log.md#phase-8--demo-polish-fixes-from-rehearsal-discoveries) |
| 8.2 | [*Testing strategy (~8–10 changed/new)*](prompts/10-phase-8.2-doc-parser-refactor-plan.md#testing-strategy-810-changednew) | `test_doc_parser.py`, `test_doc_parser_prompts.py`, `test_agent_probe.py`, `test_demo_fixture.py`, `test_pipeline_scenarios.py`, `test_prompt_loader.py`, `test_runs_repository.py` | "~8–10 changed/new" | 327 passing, 7 skipped (−3 net); 30 frontend | none recorded | [Phase 8.2](build-log.md#phase-82--doc-parser-refactor-claim-record-as-source-of-truth) |
| 8.3 | [*Tests (~10 new, ~4 modified)*](prompts/11-phase-8.3-explainability-panel-fixes-plan.md#tests-10-new-4-modified) | `test_demo_fixture.py` and the four agents' prompt-capture tests; `AgentCard`, `RunDetailPage` tests | "~10 new, ~4 modified" | 331 passing, 7 skipped (+4); 36 frontend (+6) | none recorded | [Phase 8.3](build-log.md#phase-83--explainability-panel-fixes) |
| 8.4 | [*Test pass-rate target*](prompts/12-phase-8.4-audit-write-fix-plan.md#test-pass-rate-target) (design in *6. Test design*) | `test_audit_persistence.py` | "331 backend tests → 335" | 335 passing, 7 skipped | yes — the four tests run against three connection states: "True original bug (`autocommit=False` with post-SET commit): 3 fail, 1 pass — reproduces the rehearsal exactly (Guardrail survives)"; "`autocommit=False` without post-SET commit: 4/4 fail" | [Phase 8.4](build-log.md#phase-84--audit-write-transaction-fix) |
| 8.5 | [*Test pass-rate target*](prompts/13-phase-8.5-test-isolation-fix-plan.md#test-pass-rate-target) (design in *8. Discriminator tests*) | `test_db_isolation.py`, `test_audit_persistence.py` | "335 → 338 backend passing" | 338 (the full run confirmed in 8.5.1, once the local test database existed) | none recorded; the guard's refusal was observed end to end against the live-pointing configuration | [Phase 8.5](build-log.md#phase-85--test-isolation-fix) |
| 8.5.1 | no plan file (point release from the prompt alone) | `test_migration_0002.py`, `test_health.py` | — | 338 passed, 0 failed, 7 skipped (345 collected) | yes — "The pre-fix form was deliberately reinstated with the new assertion kept, and the test re-run: it failed … The code that previously passed while destroying the schema now fails." | [Phase 8.5.1](build-log.md#phase-851--migration-test-autocommit-fix-point-release) |
| 8.5.2 | [*5. Test strategy*](prompts/15-phase-8.5.2-pin-mistral-model-plan.md#5-test-strategy) | `test_settings_phase1.py`, `test_settings_phase2.py`, `test_api_logger.py`, `test_llm_provider_mistral.py`, `test_variants.py` | "338 passed, 0 failed, 7 skipped" unchanged | 338 passed, 0 failed, 7 skipped | none recorded | [Phase 8.5.2](build-log.md#phase-852--pin-mistral-model-to-mistral-large-2512-point-release) |
| 8.5.3 | [*4. Test design*](prompts/16-phase-8.5.3-requested-model-audit-and-db-reset-plan.md#4-test-design) | `test_validator.py`, `test_adjuster.py`, `test_doc_parser.py`, `test_guardrail.py`, `test_demo_fixture.py`, `test_variants.py` | "New tests (9)"; "Expected: 347 passed, 0 failed, 7 skipped" | 347 passed, 0 failed, 7 skipped (the Phase 8.6 plan's re-run baseline; the 8.5.3 report records the deployed check and the proof, not a count line) | yes — "With the `requested_model` line temporarily removed from `attach_request`, all 9 new tests failed; restored, all pass." | [Phase 8.5.3](build-log.md#phase-853--record-requested_model-in-agent-audit-payloads-reset-the-deployed-db-point-release) |
| 8.6 | [*8. Tests*](prompts/17-phase-8.6-validator-adjuster-on-claude-haiku-plan.md#8-tests) | `test_settings_providers.py`, `test_agent_wiring.py`, `test_variants.py`, `test_adjuster.py`, `test_doc_parser.py`, `test_guardrail.py` | "347 + 16 new = ≈ 363" | 366 passed, 0 failed, 7 skipped | none recorded | [Phase 8.6](build-log.md#phase-86--validator-and-adjuster-default-to-claude-haiku-mistral-path-retained-as-a-variant) |
| 8.6.1 | [*5. Part B — tests*](prompts/18-phase-8.6.1-guardrail-citation-regex-fix-plan.md#5-part-b--tests) | `test_guardrail.py` | "+6 new = 372 passed" | 373 passed, 0 failed, 7 skipped ("Seven new tests, not six": the planned sixth passed with the defect reinstated, so a seventh was added) | yes — "M1 — global `re.IGNORECASE` reinstated: 3 failures … with the exact production flag"; "M2 — name class reverted to `[A-Z]`: `test_citation_candidates_still_flag[numbered_section]` fails." | [Phase 8.6.1](build-log.md#phase-861--guardrail-citation-regex-false-positive-point-release) |
| 9.1 | [`19-…-plan.md`](prompts/19-phase-9.1-azure-foundation-bicep-container-apps-plan.md) — no testing section; [*7. Verification*](prompts/19-phase-9.1-azure-foundation-bicep-container-apps-plan.md#7-verification-recorded-in-the-report-and-the-build-log) is the deployment check | `test_db_isolation.py` (+2, the Azure host) | none stated | 375 passed, 0 failed, 7 skipped | none recorded | [Phase 9.1](build-log.md#phase-91--azure-foundation-bicep-postgres-flexible-server-container-apps-key-vault-managed-identity) |
| 9.2 | [`20-…-plan.md`](prompts/20-phase-9.2-static-web-apps-oidc-deploy-app-insights-plan.md) — no testing section | `test_telemetry.py`, `test_settings_phase1.py` | none stated | 382 passed, 0 failed, 7 skipped; 36 frontend | none recorded | [Phase 9.2](build-log.md#phase-92--frontend-on-static-web-apps-oidc-deploy-on-push-application-insights-second-verification-pass) |
| 9.2.1 | [*Test module — `test_guardrail_replay.py`*](prompts/21-phase-9.2.1-guardrail-false-positive-fix-plan.md#test-module--backendteststest_guardrail_replaypy) | `test_guardrail_replay.py`, `test_guardrail_prompts.py`, `test_anonymisation.py`; fixtures `ded5557b`, `8e886c66`, `2c42cf40` and the four Azure rows | no count stated | 391 passed, 0 failed, 14 skipped | partial — the build log's *Mutation proof — what has been observed so far*: the old prompt from git restored, each fixture replayed 3 × under old and new; the report's table records "Confirmation through the committed files (gated test, twice): 6 passed, 6 passed" | [Phase 9.2.1](build-log.md#phase-921--guardrail-false-positives-on-the-auto-approve-scenario-point-release) |
| 9.2.2 | [*4. Tests*](prompts/22-phase-9.2.2-guardrail-quote-verified-citation-flags-plan.md#4-tests) | `test_guardrail_llm_flags.py`, `test_guardrail.py`, `test_guardrail_prompts.py`, `test_guardrail_replay.py` | no count stated | 429 passed, 0 failed, 15 skipped (+37) | yes — "Mutation proof: verifier neutered → 18 tests fail; 9.2.1 prompt restored → the golden-shape test fails." | [Phase 9.2.2](build-log.md#phase-922--the-llm-citation-flag-must-quote-its-evidence-and-code-verifies-it-30-october-2026) |
| 23 | [`23-…-plan.md`](prompts/23-plain-language-documentation-plan.md) — documentation only; [*6. Verifying every pointer*](prompts/23-plain-language-documentation-plan.md#6-verifying-every-pointer) is a link check | none (`test_anonymisation.py` run, unchanged) | n/a | 429 passed, 0 failed, 15 skipped, unchanged; "207 links, 44 anchors and 41 build-log section references" verified | n/a | [Prompt 23](build-log.md#prompt-23--plain-language-documentation-3031-october-2026) |
| 10 | [*7. Tests (backend)*](prompts/24-phase-10-mcp-server-and-integrations-page-plan.md#7-tests-backend) and [*6e. Frontend tests*](prompts/24-phase-10-mcp-server-and-integrations-page-plan.md#6e-frontend-tests-vitest--testing-library-existing-style) | the nine `test_mcp_*.py` modules, `test_phase10_promotions.py`, `test_settings_mcp.py`, `test_regenerate_build_story.py`, `test_logging_setup.py`; `IntegrationsPage`, `GuidePage`, `useMcpActivity`, `guide`, `RunDetailPage`, `AgentCard`, `App` tests | "about 45 backend tests added to 429 … about 14 frontend tests added to 36" | 521 passed, 0 failed, 18 skipped; 54 frontend (point releases 0.10.0.1 and 0.10.0.2 included) | yes — "(1) `BearerGuard._authorised` returning `True` in place of the `compare_digest` call: `test_wrong_token_is_refused` fails, eight pass … (the plan had expected two failures). (2) `mount_mcp` given a dummy token when none is set: `test_unset_token_means_no_route` and `test_blank_token_counts_as_unset` fail, seven pass." | [Phase 10](build-log.md#phase-10--mcp-server-over-the-audit-trail-integrations-and-guide-pages-2-to-4-november-2026) |

Two things the table shows at a glance. Before Phase 8.4 no phase recorded a mutation proof; from 8.4 on, every phase that changed a guard did, and 9.2.1's is marked partial because the record itself says so. And the predicted figures are estimates with a tilde through Phase 8.3, exact targets from 8.4 to 8.6.1, and absent for the two infrastructure phases and the two Guardrail prompt phases, where the plan described the tests without counting them.

## 4. Model behaviour: the replay corpus and the deployed verification passes

### The replay corpus

**Why it exists.** On 26 October 2026 the Guardrail's model failed the auto-approve scenario twice on the Azure installation, and replaying the exact recorded prompt from 1 October, which had passed then, failed too: the pinned model had changed its verdict on byte-identical input ([R-16](decision-register.md#r-16)). The response was to narrow the Guardrail's question ([R-17](decision-register.md#r-17)), then to move the decision into code so that a model's objection counts only when the quoted words are found and have a provision's shape ([R-18](decision-register.md#r-18), with its accepted limit in [R-19](decision-register.md#r-19)). The corpus is the check that those two changes hold, and the tripwire that would show the next drift.

**What it is.** Seven recorded Guardrail inputs in [`backend/tests/fixtures/guardrail_replay/`](../backend/tests/fixtures/guardrail_replay/), each the literal prompt an agent sent on a real run, recovered from the audit trail by [`scripts/extract-guardrail-replay-fixture.py`](../scripts/extract-guardrail-replay-fixture.py). The script reads a deployed database through a dedicated read-only variable, proves the recovery lossless (the template re-rendered from the recovered values must equal the recorded prompt byte for byte), runs the PII patterns over the text, and never overwrites a fixture.

| Fixture | Recorded | Where | Expected verdict |
|---|---|---|---|
| `ded5557b` Harborline, Render, 21 September | 2026-09-21 | Render / Neon, Phase 8.6.1 verification | pass |
| `08d514f2` Harborline, pass one | 2026-10-01 | Azure, Phase 9.1 verification (script) | pass |
| `8590b47e` Harborline, pass two (a) | 2026-10-26 17:08 | Azure, Phase 9.2 verification through the frontend | pass |
| `f02fb888` Harborline, pass two (b) | 2026-10-26 17:28 | Azure, the same pass | pass |
| `b35b146b` Coral Bay, guardrail scenario | 2026-10-26 | Azure, the same pass | flag (hallucinated citation) |
| `8e886c66` Harborline, Render, 29 October | 2026-10-29 | Render / Neon, the 9.2.1 script run that failed | pass |
| `2c42cf40` Harborline, Vercel, 30 October | 2026-10-30 | Render / Neon through the Vercel frontend | pass |

Six are the auto-approve claim, because that is the one the model kept sending to a person; the seventh is the scenario whose invented endorsement must still be caught. An eighth gated case replays Coral Bay with the rule engine's findings blanked, to show the model catches the invented endorsement on its own.

**How it runs.** Gated, never in CI:

```
RUN_LLM_E2E_TESTS=1 uv run pytest backend/tests/test_guardrail_replay.py
```

with `ANTHROPIC_API_KEY` set. Each fixture is sent three times at temperature 0; `pass` means no citation flag in any repetition, `flag` means one in every repetition, and since 9.2.2 the verdict is judged as the agent judges it, with the model's claims verified by the same code. Three contract tests run on every ordinary run without a key: every fixture parses against a strict schema, a malformed fixture is refused, and the corpus tripwire fails if a fixture the record says must exist is missing.

**Results.** Before 9.2.2, on the shipped `0.9.1.1`: 7 passed, 1 failed (`2c42cf40` flagged *"$200,000 ceiling"* 3 of 3; `8e886c66`, which had failed 6 of 6 the day before, passed 3 of 3). After 9.2.2: **8 passed**, seven fixtures 3 of 3 and Coral Bay without the rule engine. The 9.2.1 build-log entry holds the case-by-case before-and-after table under the old and new prompts.

**The rule.** The README's *Before a demo* note: the replay is run before every demonstration, the auto-approve cases must pass and the guardrail case must still flag, and a red case means something has moved and is worth reading before the demo.

### The deployed verification passes

Each dated run of the three scripted scenarios on a live installation that the build log records, with what was checked and the result. "Script" is [`scripts/verify-demo-scenarios.py`](../scripts/verify-demo-scenarios.py), which submits each claim through the API, runs the pipeline and asserts the outcome; it drives the API, not the browser. The checks were the same from 1 October on: the three terminal states, seven audit entries per run in order, the chain verified over the whole ledger, every model call recording `provider`, `requested_model` and `model`, and the guardrail scenario's Adjuster recorded as the demo fixture.

| Date | Installation and path | Result | Record |
|---|---|---|---|
| 15 June 2026 | Render, script (Phase 7) | The script and the evidence file [`docs/verification/phase-7/scenarios.md`](verification/phase-7/scenarios.md) were created; the file's evidence blocks were left as placeholders and never filled. The build log records the two live scenarios reproducing and the third proven deterministic in test. | [Phase 7](build-log.md#phase-7--demo-polish-and-documentation) |
| 14 September 2026 | Render, script | **Failed** at the Validator: the Mistral provider refused the pinned model (`403`). | [Phase 8.5.2](build-log.md#phase-852--pin-mistral-model-to-mistral-large-2512-point-release), [R-04](decision-register.md#r-04) |
| 14 September 2026 | Render, one run | **Passed** its own check: the audit row records `requested_model = "mistral-large-2512"` on the refusal, which is what the release existed to prove. | [Phase 8.5.3](build-log.md#phase-853--record-requested_model-in-agent-audit-payloads-reset-the-deployed-db-point-release), [R-05](decision-register.md#r-05) |
| 15 September 2026 | Render, through the run endpoint | **Halted** at the auto-approve scenario, which escalated on a rule-engine false positive; no re-run, by the halt rule. | [Phase 8.6](build-log.md#phase-86--validator-and-adjuster-default-to-claude-haiku-mistral-path-retained-as-a-variant), [R-07](decision-register.md#r-07) |
| 21 September 2026 | Render, from a fresh reset | **Passed**, all three on `0.8.6.1`; three further findings on background claims, left open. | [Phase 8.6.1](build-log.md#phase-861--guardrail-citation-regex-false-positive-point-release), [R-08](decision-register.md#r-08) |
| 1 October 2026 | Azure, script (pass one of two) | **Passed**: `settled` / `awaiting_human` / `awaiting_human` with the expected rules; 7 entries each; chain ok over 21 rows; all 11 model calls Anthropic Haiku; cold start 28 s. | [Phase 9.1](build-log.md#phase-91--azure-foundation-bicep-postgres-flexible-server-container-apps-key-vault-managed-identity) |
| 26 October 2026 | Azure, through the Azure frontend (pass two) | **Passed for the deployment with a recorded exception**: both auto-approve runs ended in human review on the model's citation check; threshold and guardrail as designed; 7 entries each; chain ok over 49 rows; the live stream proven across origins. | [Phase 9.2](build-log.md#phase-92--frontend-on-static-web-apps-oidc-deploy-on-push-application-insights-second-verification-pass), [R-16](decision-register.md#r-16) |
| 29 October 2026 | Azure, through the frontend; Render, script | Azure **passed**, all three as designed, the first time since 1 October. Render **1 of 3 failed**: the script's Harborline narrative produced a different Adjuster text and the model flagged it. Closed as partially verified. | [Phase 9.2.1](build-log.md#phase-921--guardrail-false-positives-on-the-auto-approve-scenario-point-release), [R-17](decision-register.md#r-17) |
| 30 October 2026 | Render, through the Vercel frontend | Harborline **escalated** on the model's *"$200,000 ceiling"* claim; recorded as the seventh fixture. | [Phase 9.2.1 addendum](build-log.md#phase-921--guardrail-false-positives-on-the-auto-approve-scenario-point-release) |
| 30 October 2026 | Azure frontend; Vercel frontend to Render; Render, script | **Passed on all three surfaces** on `0.9.1.2`: ten runs, every auto-approve settled, each model claim refused in code and recorded; the script reported *OK: all three demo scenarios reproduced the expected outcomes*. | [Phase 9.2.2](build-log.md#phase-922--the-llm-citation-flag-must-quote-its-evidence-and-code-verifies-it-30-october-2026), [R-18](decision-register.md#r-18) |
| 4 November 2026 | Azure, through the Claude Desktop connector and the official MCP client; Render, script | **Passed**: Harborline `settled` $85,000; Northwood `awaiting_human` on the ceiling, $820,000; Coral Bay `awaiting_human` on the guardrail and the ceiling; 7 entries each; chain ok over 112 rows; the calls in the tool-call log. Render's script run OK. | [Phase 10](build-log.md#phase-10--mcp-server-over-the-audit-trail-integrations-and-guide-pages-2-to-4-november-2026), [R-20](decision-register.md#r-20) |

**What this is and is not.** The corpus and the passes are a regression harness: they detect a change from recorded behaviour on a small fixed set of inputs, and the three scenarios were written to land on three different outcomes, not to measure accuracy across a population of claims. No pass scores the model, and none would show a fault that the three scenarios and seven fixtures do not happen to exercise. The backlog entry [*Guardrail rule-engine test corpus from more than one model*](BACKLOG.md#guardrail-rule-engine-test-corpus-from-more-than-one-model) records the step from this to a corpus of real reasoning paragraphs from each model the system has run on.

## 5. What the user interface's tests do and do not cover

The 14 files in part 2 exercise the pages and components with the service mocked: `fetch` is replaced per test with recorded answers (Phase 6 chose this over a mocking library), and the live feed's `EventSource` is a test double that the test drives. What they check is what appears: that a run page shows queued cards and then an error banner when an abort event arrives, that an agent's card shows the prompt recorded in the audit entry rather than the template, that the Guardrail card lists each refused claim with its quote and reason, that the review panel will not approve without a reviewer's name, that the status badge is the right colour. Two are worth naming. The Integrations page test *renders every tool the backend reports, with its kind* builds a catalogue of tools, serves it as the API's answer and asserts each one is on the page, so a tool added to the backend cannot silently be missing from the page; the same file asserts the copied Claude Code command contains the placeholder and never a token. The copy-module tests (`copy/guide.test.ts`, `copy/tooltips.test.ts`) pin the public links, the glossary wording and the production-equivalent names, so the words a visitor reads are under test.

**What they do not do.** There is no browser-driven end-to-end test. Nothing opens the real site, fills the form, presses *Process*, watches the four cards fill from the live stream and opens the audit. That path is covered by the manual verification passes in part 4, done by a person at the Azure or Vercel frontend, and by `scripts/verify-demo-scenarios.py`, which drives the API and so proves the backend's behaviour, not the screens. The gap is recorded in the backlog, [*Browser-driven end-to-end test of the three scenarios*](BACKLOG.md#browser-driven-end-to-end-test-of-the-three-scenarios), with a proposal for a Playwright run gated like the replay corpus; it is not built.

## 6. CI as independent evidence

The three workflows in [`.github/workflows/`](../.github/workflows/) run on GitHub Actions. The run history is at `https://github.com/dcopps/agentic-claims-poc/actions`.

**`ci.yml`** runs on every pull request and every push to `main`, as two jobs in a clean environment:

- *Backend*: a PostgreSQL 17 service with pgvector (the image CI uses matches both deployed databases), `uv sync`, migrations to head, `ruff check .`, `mypy backend`, `pytest`, then `pip-audit` as an advisory step that does not fail the build.
- *Frontend*: Node 20, `npm ci`, lint, typecheck, `vitest --run`, then `npm audit` at high severity, advisory.

The backend job needs no test-database variable: its `DATABASE_URL` is the service container on `localhost`, which the harness's live-host refusal accepts.

**`deploy-backend.yml` and `deploy-frontend.yml`** are triggered by `workflow_run`: they start when the *CI* workflow completes on `main`, and each checks that the run succeeded before doing anything, so a red CI skips both deployments. The backend workflow builds the image in the Azure registry and updates the Container App only when the backend paths differ from the deployed image's commit; the frontend workflow builds and uploads on every green run. Both authenticate without a stored credential ([R-13](decision-register.md#r-13)). Infrastructure is not deployed by either; it is run from a developer's shell.

**The red period.** CI on `main` was red from 15 June to 26 October 2026 ([R-11](decision-register.md#r-11)). The frontend's dependency lock file had fallen out of step with its manifest in Phase 6, so the *Frontend* job failed at `npm ci`, before lint, typecheck or any test ran. The *Backend* job passed on every one of those runs. A reader who finds the red runs should read them as: the backend suite passed in CI throughout; the frontend suite did not run in CI during that period, and its counts for Phases 6 to 9.1 (22, 30, 36) come from local runs recorded in the reports; and nothing could have deployed from CI, which did not matter until Phase 9.2 introduced the gate and fixed the lock file first. The first fix used the wrong npm version and left CI red for two more pushes; the second, with CI's own version, went green on 26 October and the deploy workflows have run since.
