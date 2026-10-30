# Phase 9.2.2 — Report: the Guardrail's LLM citation flag must quote its evidence, and code verifies it

**Status: complete — 30 October 2026, verified on all three deployed surfaces.** Version `0.9.1.2`, deployed as `94b7527` (Azure revision `--0000016`; Render auto-deploy). Plan approved 30 October (D1–D5 as recommended). Build-log entry *Phase 9.2.2* carries the full record; this report is the summary.

## What was built

- `backend/app/agents/guardrail_llm_flags.py` (new): the claim and outcome models and `verify_llm_flags`. A `hallucinated_citation` claim counts only when its quote is located in the Adjuster's reasoning and the reasoning's own span matches the rule engine's provision pattern; refusals (`no_quote`, `quote_not_in_reasoning`, `quote_not_a_provision`) are recorded and logged, never raised.
- `backend/app/agents/guardrail.py`: parse into claims, verify with the agent's own rule engine pattern, record `llm_flags_counted` / `llm_flags_discarded` in the audit (always present).
- `backend/app/prompts/system/guardrail.md`: `quote` in the *Output format* and one rule. Citation definition and user template unchanged.
- Tests: `test_guardrail_llm_flags.py` (new, 29 cases), `test_guardrail.py` (+6), `test_guardrail_prompts.py` (+1), `test_guardrail_replay.py` (verifies as the agent does; prints refusals).

**Untouched by design:** `_CITATION_CANDIDATE_RE`, the rule engine, `policy.yaml`, `GuardrailFlag` / `GuardrailOutput`, every HTTP and SSE shape, the user template, the seven fixtures, the frontend.

## Tests

**429 passed, 0 failed, 15 skipped** (+37). `ruff`, `mypy` clean. Mutation proof: verifier neutered → 18 tests fail; 9.2.1 prompt restored → the golden-shape test fails.

## Replay (acceptance)

Before, on the shipped `0.9.1.1`: 7 passed, 1 failed (`2c42cf40`, *"$200,000 ceiling"*, 3/3; `8e886c66` passed 3/3 although it had failed 6/6 the day before). After: **8 passed** — seven fixtures 3/3 and Coral Bay without the rule engine 3/3, counted on a quote-verified *"Endorsement Coastal Surge Rider"*. Evidence pass: the six must-pass texts drew no flag at all under the quote requirement; `f02fb888` drew a coverage re-adjudication claim refused `quote_not_a_provision`. Full table in the build log.

## Deviations from the plan

- `CountedLLMFlag` records evidence for every promoted claim, not only citations (`quote` is `null` for `pii` / `bias`), so `llm_flags_counted` is the complete list of what the LLM contributed.
- The replay test's repetition shape became a small `Repetition` dataclass (counted details + refused claims) rather than a bare list, so the failure message carries the diagnosis.
- Two agent-level audit tests instead of one (the claim-stub helper uses a fixed claim number).

## Guard clauses added beyond the spec

- A `quote` of the wrong JSON type is a schema failure (fail-closed), while a missing or empty quote is a recorded `no_quote` refusal — stated in the parse docstring.
- One layer of wrapping quote characters is stripped before the containment test, because the model habitually writes `'supply line'`.

## Deployed verification (30 October 2026)

All three scenarios as designed on all three surfaces: Azure frontend (`00011dad` settled $82,500 / `fd9b5c20` ceiling / `c0618c74` guardrail + ceiling), Vercel frontend against Render (`0cdfa114` and `4142f33b` settled / `6197d116` ceiling / `cdf20928` guardrail + ceiling) and the script against Render (`e215acf9` / `96bb2a0c` / `fe4b1736`, `OK`). Seven entries each, Anthropic Haiku on every call, chain `ok` on both ledgers (Azure 91 rows, Render 118). **The code refused three model claims on the Vercel path** — *"inventory valuation and depreciation"*, *"sudden, verified pipe rupture causing water damage"*, *"the $1.5M ceiling"* — all `quote_not_a_provision`, all recorded in `llm_flags_discarded`, and the claims settled or escalated on the ceiling rule alone. Coral Bay's Adjuster on Render was the demo fixture (audit: `demo_fixture: true`, no model call, `latency_ms: 0`); the UI's 3.7 s is the step's wall clock including Neon round trips from Render. Full table in the build log.

## Suggestions (not in scope)

- Show `llm_flags_discarded` on the Run Detail Guardrail card (Phase 8.7).
- Run the replay corpus on a schedule against the live model (the production control the governance doc describes).
