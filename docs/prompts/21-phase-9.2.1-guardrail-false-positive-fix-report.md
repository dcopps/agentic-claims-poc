# Phase 9.2.1 — Report: Guardrail false positives on the auto-approve scenario

**Date:** 28–29 October 2026 — **closed as partially verified**
**Plan:** [`21-phase-9.2.1-guardrail-false-positive-fix-plan.md`](21-phase-9.2.1-guardrail-false-positive-fix-plan.md) (approved 28 October; D5 revised 29 October — see its *Approval* section)
**Version:** `0.9.1 → 0.9.1.1`, deployed to Azure and Render as `077f670`
**Build-log entry:** *Phase 9.2.1* in [`../build-log.md`](../build-log.md)

## Summary

The Guardrail's LLM check was narrowed to judge named citations only. The system prompt defines a citation as a provision named by title or number, lists what is not one, states that coverage was decided upstream, and reasons from the Adjuster's text outward. That alone was not enough: replayed against the four Azure runs it removed the coverage-re-adjudication and amount flags but two of three Harborline runs still flagged on the literal phrase *"market range"*. A scratchpad experiment showed the user template's framing was deciding the verdict; two edits to it (variant v3: the chunks heading loses *"(the only authoritative source)"*, the *Task* paragraph tells the model to apply the system instructions) passed all five fixtures 6 / 6 with Coral Bay still flagging 6 / 6 without the rule engine. Dermot revised D5 and v3 shipped.

Deployed verification split. Through the Azure frontend all three scenarios ran as designed for the first time since 1 October (Harborline `settled` at $78,000). Through the verification script against Render, Harborline escalated again: the LLM check flagged *"supply line"* as a covered peril on an Adjuster text outside the corpus (the script's claim narrative differs from the UI's seeded claim). Replayed, it fails 6 / 6. The verdict moves on phrasing in both directions, so the phase closes as partially verified and the remaining fix is **Phase 9.2.2**: the flag must quote its evidence and code verifies it.

The Adjuster now runs at temperature 0 on both deployed stacks through settings (Bicep parameter on Azure, dashboard variable on Render); the committed default is unchanged.

## Files

**Created:** `backend/tests/guardrail_replay_fixture.py`, `backend/tests/test_guardrail_replay.py`, six fixtures under `backend/tests/fixtures/guardrail_replay/` (`08d514f2`, `8590b47e`, `f02fb888`, `b35b146b` from Azure; `ded5557b`, `8e886c66` from Render / Neon), `scripts/extract-guardrail-replay-fixture.py`, the plan and this report.

**Modified:** `backend/app/prompts/system/guardrail.md` (rewritten; *Output format* byte-identical), `backend/app/prompts/user/guardrail_template.md` (two edits, placeholders unchanged — D5 revised); `backend/tests/test_guardrail_prompts.py` (+1); `backend/settings.py`, `backend/settings.yaml.template` (comments); `infra/bicep/modules/containerapps.bicep`, `infra/bicep/main.bicep`, `infra/bicep/main.bicepparam` (`adjusterTemperature` → `LLM__ADJUSTER_TEMPERATURE`); `pyproject.toml`, `uv.lock` (version); `README.md`, `CLAUDE.md`, `docs/build-log.md`, `docs/BACKLOG.md`, `docs/change-governance.md`, `docs/dora-third-party-register.md`.

**Not touched, by instruction:** the rule engine (`_CITATION_CANDIDATE_RE` and friends), `policy.yaml`, the Adjuster prompt, the demo fixture, any audit / SSE / HTTP shape. No new dependency.

## Tests

Suite **391 passed, 0 failed, 14 skipped** (from 382 / 0 / 7). New: contract tests over every fixture (6), the corpus tripwire, the malformed-fixture test, the golden-shape prompt test; gated live replay (6 cases) and the Coral Bay no-rule-engine case. `ruff check .`, `uv run mypy backend` (114 files), `az bicep build` + `lint` clean. No function over 30 lines in the new modules.

**The gated pre-demo replay reports one red case on purpose** — `8e886c66` — until Phase 9.2.2.

## Outcomes (the tables are in the build-log entry)

| Proof | Result |
|---|---|
| Golden-shape test on the old prompt | fails; passes on the new |
| Four Azure runs, old system prompt | three Harborline runs flagged 3 / 3 (the finding reproduced); Coral Bay flagged |
| Four Azure runs, approved system prompt, old template | `8590b47e` clean; `08d514f2`, `f02fb888` still flagged 3 / 3 on *"market range"*; Coral Bay flagged without the rule engine |
| Template variants v1 / v2 / v3 (HEAD system prompt) | v1: two clean, `f02fb888` flagged-then-self-corrected (parse failure); v2: coverage re-adjudication on all three; **v3: all clean 6 / 6, Coral Bay flagged 6 / 6** |
| Confirmation through the committed files (gated test, twice) | 6 passed, 6 passed |
| Azure, through the frontend (Dermot) | `settled` / `awaiting_human` (`settlement_over_ceiling`) / `awaiting_human` (`guardrail_failed`, `settlement_over_ceiling`); seven entries each; chain `ok` over 70 rows |
| Render, `verify-demo-scenarios.py` | 2 of 3; Harborline `8e886c66` escalated on an LLM flag (*"supply line"*); chain `ok` over 62 rows |
| `8e886c66` replayed through the committed prompts | flagged 6 / 6 |
| Cold start, zero replicas, telemetry on | 34.2 s (9.1 baseline 28.0 s) |

## Deviations from the plan

- **D5 revised** (29 October, Dermot): the user template changed in two places. Reason and evidence in the plan's *Approval* section. Consequence: recorded `prompt.user` values are not byte-comparable across the change; the fixture stores inputs, so the replay is unaffected, and the extraction script's round-trip proof holds under either template.
- **The phase closes as partially verified**, not verified: plan §7's "halt and diagnose if Harborline still escalates" fired on the Render script pass. The diagnosis is the case for 9.2.2.
- The fifth (Render) fixture was extracted before the Azure session; the sixth was not in the plan at all — it is the failing run itself.
- The Vercel-frontend-against-Render path was not observed after the fix (no run found in the Render audit log at close-out); recorded as such.

## Guard clauses added beyond the spec

- The extraction script refuses to overwrite an existing fixture; reads only `REPLAY_SOURCE_DATABASE_URL`; sets the connection read-only; proves the recovery lossless before writing.
- `test_corpus_contains_the_four_required_runs` — an always-on tripwire so a deleted fixture fails CI.
- `test_contract_rejects_a_malformed_fixture` — the contract's error names the file.
- `_assert_verdict(…, rule_engine_already_flagged=…)` — a flag fixture whose rule engine already found the citation is judged combined, as the agent judges it; the LLM-alone assertion is its own test.

## Suggestions (optional, not done)

- **Phase 9.2.2** is scheduled (prompt 22): quote-and-verify in code, discards recorded in the audit (additive, to be flagged as an interface-stability event in its plan).
- Make the verification script's Harborline narrative identical to the seeded UI claim, so the two paths exercise one text. Deliberately *not* done here: it would hide the sensitivity this phase found rather than fix it.
- The parse-failure path seen under variant v1 (a flagged JSON object followed by a corrected one in a single reply) is handled fail-closed today; 9.2.2 could record such replies distinctly so a self-correction is visible in the audit.
