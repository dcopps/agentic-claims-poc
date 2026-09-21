# Phase 8.6.1 — Guardrail citation-regex false positive; re-run the Phase 8.6 verification

## Context

Phase 8.6 deployed cleanly (`0.8.6`) and its verification halted at step 3: the auto-approve scenario landed at `awaiting_human` with `guardrail_failed` (run `8bff04e2-6ff7-4e74-aa5c-003008f21185`) while both confidences were above floor (0.92, 0.88) and the settlement ($82,500) was in range. Threshold and guardrail scenarios passed. The root cause is diagnosed in the Phase 8.6 report (`docs/prompts/17-phase-8.6-validator-adjuster-on-claude-haiku-report.md`) and is not repeated here beyond the essentials:

- `backend/app/agents/guardrail_rules.py` → `_CITATION_CANDIDATE_RE` is
  `(endorsement|sub-?limit|clause|provision|section|exclusion)\s+(?P<name>[A-Z][A-Za-z0-9 \-./]{1,60})`
  compiled with **`re.IGNORECASE`**.
- The flag applies to the whole pattern, so the name group's leading `[A-Z]` — written to mean *"a cited name starts with a capital"* — also matches lowercase. Any keyword followed by any word becomes a citation candidate.
- The Haiku Adjuster wrote *"The loss is contained to one floor **section with** inventory and drying as primary components…"* and the rule engine flagged `section 'with inventory and drying as primary components' not in retrieved chunks`.
- Latent since Phase 3. Mistral's phrasing never put a keyword in front of a lowercase word. Phase 8 fix #5 tuned the *LLM* half of the Guardrail, not this regex.

This is a bug in the deterministic layer, not a prompt or model-quality issue. The Phase 8.6 halt rule (no prompt or token retuning) was correctly applied and still holds: **the Adjuster prompt is not to be changed to avoid the phrasing.**

## Part A — the fix

Scope the case-insensitivity to the keyword alternation only, so the name group's capital-letter requirement means what it says. Something of the shape:

```
(?i:endorsement|sub-?limit|clause|provision|section|exclusion)\s+(?P<name>[A-Z][A-Za-z0-9 \-./]{1,60})
```

compiled **without** the global flag. The plan must:

1. **State precisely what the current pattern matches and does not**, then what the new one does, against at least these strings — the plan is not approved until this table exists:
   - `"one floor section with inventory and drying as primary components"` → today: match (the bug); after: **no match**.
   - `"Section 4.2"` → check today's behaviour honestly: `[A-Z]` does not match a digit, so if this does *not* match today that is a second latent defect (under-flagging), and the name group should become `[A-Z0-9]`. Decide and justify.
   - `"endorsement Coastal Surge Rider"` (lowercase keyword, capitalised name) → must match after.
   - `"Endorsement CSR-7"` → must match after.
   - `"the sub-limit of $25,000"` → should **not** match (lowercase "of").
   - Whatever hallucinated citation the Phase 7 `guardrail_escalation` fixture emits (read it from `adjuster.py` / the fixture data) → **must still match**, or the $1.4M scenario stops escalating.
2. **Confirm the LLM half of the Guardrail is untouched.** Only `guardrail_rules.py` changes.
3. **Confirm no other regex in `guardrail_rules.py` has the same global-flag defect** (PII and bias patterns). Fix in the same way if so; say so in the plan either way.

## Part B — tests

- **Regression test with the exact Haiku sentence** from run `8bff04e2` (quoted above) asserting **no** `hallucinated_citation` flag from the rule engine. The sentence must be verbatim — that run is the evidence.
- **Positive tests** for each *must match* row in the Part A table, so the fix cannot be "loosened until green".
- **The Phase 7 fixture test** (`test_demo_fixture.py` or wherever the $1.4M fixture's `guardrail_failed` outcome is asserted) must still pass unchanged.
- **Mutation proof:** reinstate the global `re.IGNORECASE`, confirm the Haiku-sentence test fails, restore. Record in the report.
- State the expected count from the 366 / 0 / 7 baseline.

## Part C — record the lesson

Add to `docs/BACKLOG.md` → *Future work*: **"Guardrail rule-engine test corpus from more than one model."** The rule engine's tests use hand-written sentences in one model's idiom; a provider swap is precisely the event that exposes an overfit heuristic. Proposal: keep a small corpus of *real* Adjuster reasoning paragraphs from each model the prototype has run on (Mistral Large, Claude Haiku — pulled from audit rows, anonymised as they already are), and run the rule engine over all of them as a no-false-positive suite. Not built here.

## Version

Point release `0.8.6 → 0.8.6.1`. One file plus tests.

## Plan-first

Produce `docs/prompts/18-phase-8.6.1-guardrail-citation-regex-fix-plan.md` covering Part A's table and decisions, Part B's test list and expected count, Part C, and the verification sequence below. Wait for approval before writing code.

## Deployed verification — the full Phase 8.6 sequence, from scratch

The 8.6 verification was halted at step 3, so it is re-run in full. Steps 4 and 5 have never run.

0. Render env check (Dermot): no `LLM__*` variables; `MISTRAL_API_KEY` present. Unchanged from 15 September unless someone touched it.
1. `/health` → `0.8.6.1`.
2. **Reset Neon** (hostname gate; `seed_claims --allow-truncate`; 9 claims at `received`; `audit_log` cleared — this discards the `8bff04e2` evidence run, which is now recorded in the 8.6 report and build log; `policy_chunks` untouched; no `index_policy`).
3. **All three scenarios**, per the Phase 8.6 plan §5 table. Auto-approve must now land at `settled` with no fired rules. **At least the auto-approve run is to be triggered from the Claims page by Dermot and its four agent panels inspected in the UI** — the 8.6 runs were API-driven and the panels were never looked at. Threshold and guardrail may be API-driven.
4. **`v1_mistral` abort proof** on a background claim (default run first, then `POST /api/pipeline/replay/{claim_id}?variant=v1_mistral`): `aborted`, `coverage_check.llm_call.provider = "mistral"`, `requested_model = "mistral-large-2512"`, 403 in `error`.
5. **One live `v2_strict_validator` replay** on the auto-approve claim, after step 3 is recorded — proves the UI's *Re-process* control works on the new default.
6. Chain verified across the whole ledger.
7. Record in the build log: a Phase 8.6.1 entry (fix, tests, mutation proof) **and** a *Deployed verification outcome* amendment to the Phase 8.6 entry (passed on the 8.6.1 build, with the three-scenario table and the two variant proofs). Clear *Demo status: blocked* in `CLAUDE.md`. Discharge the Phase 8.4 / 8.5.2 seven-entry item in `docs/BACKLOG.md` → *Pending verifications* — it has been carried since June and this run closes it.

A wrong terminal state on any scenario halts again; report with audit rows, no retuning.

## Constraints

- **`guardrail_rules.py` only** for the code change. No prompt, token, settings, wiring or frontend edits.
- **No loosening.** The fix narrows a false positive; it must not widen the miss rate. The positive tests in Part B exist to hold that line.
- **Halt on any test failure** before commit.
- Standing conventions per `CLAUDE.md`.

## Archive

Pre-saved at `docs/prompts/18-phase-8.6.1-guardrail-citation-regex-fix.md`; plan and report alongside with `-plan.md` / `-report.md`.
