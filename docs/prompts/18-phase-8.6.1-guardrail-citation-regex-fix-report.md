# Phase 8.6.1 — Report: Guardrail citation-regex false positive; Phase 8.6 verification re-run

Prompt: [`18-phase-8.6.1-guardrail-citation-regex-fix.md`](18-phase-8.6.1-guardrail-citation-regex-fix.md) · Plan: [`18-…-plan.md`](18-phase-8.6.1-guardrail-citation-regex-fix-plan.md) · 21 September 2026 · `0.8.6 → 0.8.6.1`

## Summary

The fix shipped, the suite is green, and the full Phase 8.6 deployed verification **passed** on the `0.8.6.1` build: all three scripted scenarios in their expected terminal states with seven audit entries each, the `v1_mistral` abort proof, a UI-triggered `v2_strict_validator` replay, and a verified chain across 41 rows. The Phase 8.4 / 8.5.2 seven-entry check, carried since June, is discharged.

The verification also surfaced **three findings unrelated to this fix**. Two are demo-visible: the demo is showable on the three scripted scenarios, and should stay off the background claims until they are addressed.

## Files

| File | Change |
|---|---|
| `backend/app/agents/guardrail_rules.py` | `_CITATION_CANDIDATE_RE`: `(?i:…)` scoped to the keyword alternation, global `re.IGNORECASE` removed, name group `[A-Z0-9]`; explanatory comment; module docstring. **The only code file.** |
| `backend/tests/test_guardrail.py` | 7 new tests; `test_legitimate_citation_does_not_flag` repaired |
| `pyproject.toml`, `uv.lock` | `0.8.6.1` |
| `docs/build-log.md` | Phase 8.6.1 entry; *Deployed verification outcome* amendment to the Phase 8.6 entry |
| `docs/BACKLOG.md` | Part C entry; pending verification discharged; three findings added; resolved regex item removed |
| `CLAUDE.md` | Current Status |
| `docs/prompts/18-…` | prompt, plan, this report |

No prompt, token, settings, wiring or frontend change. No interface change. No new dependency.

## Tests

**373 passed, 0 failed, 7 skipped** (366 → +7). `ruff check .` clean. `uv run mypy backend` — CI's command — clean on 110 files.

Mutation proofs, each applied, observed and reverted:

- **M1 — global `re.IGNORECASE` reinstated:** 3 failures. `test_haiku_floor_section_prose_is_not_a_citation` fails with the exact production flag, `section 'with inventory and drying as primary components' not in retrieved chunks`; both cases of `test_lowercase_word_after_keyword_is_not_a_citation` fail.
- **M2 — name class reverted to `[A-Z]`:** `test_citation_candidates_still_flag[numbered_section]` fails.

## Deviations from the plan

1. **Seven new tests, not six.** The first run of M1 showed that the planned `"the sub-limit of $25,000"` test **passed with the defect reinstated**: the old pattern's `of` candidate is a substring of a retrieved chunk (*"25% of direct damage"*), so the allow-set swallowed it and no flag was raised. A flag-level assertion could not detect the bug. The test became a two-case parametrised test that asserts at *candidate* level (`citation_pattern.search(...) is None`) as well as flag level. The mutation proof earned its place: it caught a worthless green test, written by the same hand that wrote the fix.
2. **Positive-test sentences place the citation mid-sentence.** The name class contains `.`, so a sentence-final citation captures the full stop (`'4.2.'`). Pre-existing behaviour, unchanged, and not what those tests pin.
3. **`test_legitimate_citation_does_not_flag` repaired** (the plan's optional suggestion, folded in on approval). It was vacuous — its sentence never formed a candidate. It now cites a real chunk section and also asserts that an invented section name in the same sentence *does* flag.
4. **Step 4's prior default run aborted** rather than completing (finding F1). The abort proof is unaffected — see below.
5. **Step 5 ran on Background Claimant 03**, the only background claim able to complete, and its replay aborted on finding F2. Ruled by Dermot a new finding, not a halt.

## Correction to the Phase 8.6 report

The 8.6 report stated that `"Section 4.2"` would still flag under the recommended fix. It never flagged: `[A-Z]` does not match a digit, with or without the global flag. `[A-Z0-9]` (decision D2) is what makes it flag. The 8.6 report is left as written; the correction is recorded here and in the build log.

## Deployed verification

| | Auto-approve ($85k) | Threshold ($850k) | Guardrail ($1.4M) |
|---|---|---|---|
| Correlation id | `ded5557b-ffa7-410c-8ce9-c6ed7eeb5480` | `7b800947-1b38-4776-9fbb-e364c93abdce` | `2c181430-dfd5-434a-865a-210cc8b1735d` |
| Terminal status | `settled` ✓ | `awaiting_human` ✓ | `awaiting_human` ✓ |
| Fired rules | none ✓ | `settlement_over_ceiling` ✓ | `guardrail_failed`, `settlement_over_ceiling` ✓ |
| Audit entries | 7 ✓ | 7 ✓ | 7 ✓ |
| Validator / Adjuster | 0.92 / $85,000, 0.88 | 0.92 / $820,000, 0.85 | 0.72 / fixture $1,400,000 |
| Guardrail | passed | passed | failed, `source: "rule"`, `endorsement 'Coastal Surge Rider'` |
| Providers / models | all `anthropic`, `requested_model` = `model` = Haiku, `prompt` present ✓ | same ✓ | same, except `settlement_estimate`: `demo_fixture: true`, no `prompt` / `requested_model` ✓ |

Auto-approve was triggered from the Claims page by Dermot, with all four agent panels inspected in the UI — the first time the panels have been looked at on the Haiku default.

**What this does and does not prove.** Haiku's fresh auto-approve reasoning contained no citation keyword, so the deployed run did not exercise the fix. The fix is proven by the verbatim regression test and M1. The deployed runs prove that the scenario is green on the build carrying the fix, and that the narrowed pattern still catches the planted endorsement in production.

- **`v1_mistral` abort proof — passed.** Run `6f03b619-4377-4ab6-b0df-5dbae2921525`: `aborted` at the Validator, `provider = "mistral"`, `requested_model = "mistral-large-2512"`, no `model`, `403 tier_not_allowed`.
- **`v2_strict_validator` replay from the UI — control and template proven.** Run `74513bca-2fc7-497e-9fff-b574d1d6c210`: `pipeline_started.variant = "v2_strict_validator"`; the captured `llm_call.prompt.user` carries the strict template's `# Task — strict review` block (confirmed by diffing against the default run's audit row — the system prompts are byte-identical by design, since the strict template is a user-message template). The run then aborted on F2.
- **Chain:** `{"ok": true, "rows_checked": 41, "first_break": null}`.

## Findings (all in `docs/BACKLOG.md`)

- **F1 — five of six background claims abort at the Adjuster.** Their claim types are missing from `market_data.yaml`. Only `theft` completes.
- **F2 — no pipeline path for `covered = false`.** The Adjuster runs regardless; a model that correctly reasons "no payment" returns `0.00`; the schema refuses it; the run aborts instead of reaching a human. The claim is left at status `coverage_verified` despite a *not covered* verdict. Fixing this is an interface-stability event.
- **F3 — retrieval missed *Named Perils Covered* for a theft narrative**, which is what produced `covered: false` in the first place.

## Guard clauses added beyond the spec

None.

## Suggestions (not built)

- The Part C corpus would have caught this defect in CI. F3 suggests a sibling corpus for retrieval: one narrative per claim type, asserting the governing section is in the top-k.
- Two rule-engine false-positive classes remain, noted in the plan §4: greedy name capture through trailing lowercase words, and no leading word boundary on the keyword (`intersection Main Street`). Best built together with the Part C corpus that would prove them.
- `mypy .` over the whole repository reports 2 errors in `scripts/verify-demo-scenarios.py` (Phase 7). CI only checks `backend`, so it has never failed. Not logged in the backlog — say so and it will be.
