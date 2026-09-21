# Phase 8.6.1 — Plan: Guardrail citation-regex false positive; re-run the Phase 8.6 verification

Prompt: [`18-phase-8.6.1-guardrail-citation-regex-fix.md`](18-phase-8.6.1-guardrail-citation-regex-fix.md). Point release `0.8.6 → 0.8.6.1`.

---

## 0. Findings that shape the plan

- **The evidence row is intact.** A read-only query against the deployed `audit_log` returned the `settlement_estimate` reasoning for run `8bff04e2-6ff7-4e74-aa5c-003008f21185` in full. The offending sentence, verbatim: *"The loss is contained to one floor section with inventory and drying as primary components, positioning it in the upper-moderate range."* The regression test uses the **whole paragraph** from that row, verbatim, because the whole paragraph is what the rule engine scanned in production.
- **The same query ran all three deployed Adjuster reasonings through the current and proposed patterns.** Threshold run `49179971`: no candidates under either pattern. Guardrail fixture run `529be3b0`: `Endorsement 'Coastal Surge Rider'` under both. Auto-approve `8bff04e2`: the false positive today, nothing after. That is a three-paragraph Haiku corpus, too small to prove anything on its own, which is the point of Part C.
- **The Phase 8.6 report was wrong about `"Section 4.2"`.** It said `"Section 4.2"` still flags after the proposed fix. It does not flag **today**: `[A-Z]` does not match a digit, with or without `re.IGNORECASE`. The correction goes in the 8.6.1 build-log entry; the 8.6 report stays as written, since it is the historical record.
- **The sample policy has no numbered provisions.** Its seven headings are all names (*General Conditions*, *Definitions*, *Named Perils Covered*, *Exclusions*, *Sub-Limits*, *Business Interruption*, *Duties After Loss*). A numeric citation such as `Section 4.2` therefore cannot refer to anything retrieval could return. This decides §1 D2.
- **The Phase 7 fixture reasoning** (`backend/data/demo_fixtures/guardrail_adjuster.json`) cites `Endorsement Coastal Surge Rider` (capital keyword, capitalised name). It matches under every candidate pattern.

---

## 1. Part A — the fix

### Behaviour table

Measured, not reasoned: each row was run through the three patterns in Python 3.11. `Current` is the shipped pattern with global `re.IGNORECASE`. `Proposed` scopes the flag to the keyword: `(?P<kind>(?i:endorsement|sub-?limit|clause|provision|section|exclusion))\s+(?P<name>[A-Z0-9][A-Za-z0-9 \-./]{1,60})`, compiled with no flags. `Letters only` is the same but keeps `[A-Z]` (the D2 alternative).

| Input | Current | Proposed (`[A-Z0-9]`) | Letters only (`[A-Z]`) | Required |
|---|---|---|---|---|
| `one floor section with inventory and drying as primary components` | **match** `section` / `with inventory and drying as primary components` (the bug) | no match | no match | no match |
| `Section 4.2` | **no match** (latent under-flag) | match `Section` / `4.2` | no match | decide (D2) |
| `endorsement Coastal Surge Rider` | match `endorsement` / `Coastal Surge Rider` | match, same | match, same | match |
| `Endorsement CSR-7` | match `Endorsement` / `CSR-7` | match, same | match, same | match |
| `the sub-limit of $25,000` | **match** `sub-limit` / `of ` (a second instance of the same bug) | no match | no match | no match |
| Fixture: `…coverage extended under Endorsement Coastal Surge Rider, which the claimant cited…` | match `Endorsement` / `Coastal Surge Rider` | match, same | match, same | match |
| Existing test: `Settlement supported by Endorsement A2025-CB extending coverage.` | match `Endorsement` / `A2025-CB extending coverage.` | match, same | match, same | match (unchanged) |

What the current pattern matches, precisely: any keyword in any case, then whitespace, then **any letter in any case**, then up to 60 name characters. So every keyword followed by a word is a candidate. It does **not** match a keyword followed by a digit, `$`, or punctuation. What the proposed pattern matches: any keyword in any case, then whitespace, then **an uppercase letter or a digit**. A lowercase word after the keyword is no longer a candidate.

### D1 — scope the case-insensitivity with `(?i:…)`

Python 3.11 supports scoped inline flags, so the keyword alternation stays case-insensitive (`Section`, `SECTION`, `section` all count) and the name group's character class means exactly what it says. The code comment above the pattern explains *why* the flag is scoped: a global flag silently turns the `[A-Z]` class into `[A-Za-z]`. The module docstring's description of the check is updated to state the capital-or-digit rule. `_citation_flags` is unchanged: `match.group("kind")` and `match.group("name")` behave identically.

### D2 — name group becomes `[A-Z0-9]` (recommended)

**Recommendation: adopt `[A-Z0-9]`.** Justification:

1. It closes a real miss. `Section 4.2`, `Clause 7` and `Exclusion 3` are the most typical shape of a hallucinated citation, and the rule engine does not see them today.
2. On this policy, a numeric citation is unverifiable by construction (§0: no numbered provisions). Flagging it is correct, not just cautious.
3. It points the same way as the module's stated design: *"false positives lean toward escalation, which is the safe direction for a guardrail."*
4. It does not reopen the 8.6 bug. That bug is lowercase *words*; digits are a separate, narrower class.

**Risk, stated honestly:** this widens flagging in the one scenario that depends on the model, auto-approve. Ordinary prose that puts a number straight after a keyword (for example *"the Business Interruption section 12 months"*) would now flag. None of the three deployed Haiku paragraphs does this, but three paragraphs is a small sample. If Dermot prefers zero new flagging surface in a halt-sensitive release, the alternative is **keep `[A-Z]`** and add the numeric miss to `docs/BACKLOG.md`. Both options satisfy "no loosening", because neither widens the miss rate.

### 2. Other patterns in `guardrail_rules.py`: no same defect

- **PII** (`ssn`, `email`, `phone_us`, `credit_card_like`): compiled with **no** flags. Where case matters, the character classes are explicit (`[A-Za-z]` in `email`). **No defect; unchanged.**
- **Bias** (`_PROTECTED_TERMS`): each is compiled with `re.IGNORECASE`, but every pattern is a lowercase literal term wrapped in `\b`. Case-insensitivity is **intended for the whole pattern**, and there is no case-sensitive sub-part for the flag to corrupt. **No defect; unchanged.**

### 3. LLM half untouched

Only `_CITATION_CANDIDATE_RE`, its comment and the module docstring change. No change to `guardrail.py`, the Guardrail system/user prompts, token limits, settings, wiring or frontend.

### 4. Pre-existing behaviour observed but not changed (out of scope)

Recorded so that the verification does not mistake them for regressions. Each is a candidate follow-on (§9), **not built**:

- **Greedy name capture.** The name group runs on through lowercase words (`A2025-CB extending coverage.`), so a real capitalised section followed by prose is compared as a longer string: `section Named Perils Covered for this loss` → `Named Perils Covered for this loss` → not a substring of the allow-set → false positive. This is a latent false-positive class for *capitalised* citations.
- **No leading word boundary.** `intersection Main Street` yields `section` / `Main Street`.
- **`test_legitimate_citation_does_not_flag` is vacuous.** Its sentence (`…the Sub-Limits Debris removal cap…`) produces no candidate at all (`sub-?limit` must be followed by whitespace, and here it is followed by `s`), so the test never exercises the allow-set.

---

## 5. Part B — tests

All new tests go in `backend/tests/test_guardrail.py`, in a new section *"Phase 8.6.1 — citation keyword case-insensitivity is scoped to the keyword"*. They call `GuardrailRuleEngine.with_defaults().scan(...)` directly against `_retrieved_chunks()`. That follows the existing direct-engine test at `test_guardrail.py:531`: no DB, no LLM, and the failure points at the rule engine rather than the agent.

| # | Test | Asserts |
|---|---|---|
| 1 | `test_haiku_floor_section_prose_is_not_a_citation` | The full reasoning paragraph from run `8bff04e2`, verbatim, yields **no** `hallucinated_citation` flag. The docstring cites the run id and the matched phrase. |
| 2 | `test_lowercase_word_after_sub_limit_is_not_a_citation` | `the sub-limit of $25,000` yields no `hallucinated_citation` flag. |
| 3–6 | `test_citation_candidates_still_flag` (parametrised) | Each *must match* row yields exactly one `hallucinated_citation` flag whose `detail` equals the expected string: `endorsement 'Coastal Surge Rider' not in retrieved chunks`; `endorsement 'CSR-7' not in retrieved chunks`; `section '4.2' not in retrieved chunks` (**D2 only**); and, for the fixture reasoning **loaded from `guardrail_adjuster.json`** (not copied, so fixture drift is caught), `endorsement 'Coastal Surge Rider' not in retrieved chunks`. |

The exact `detail` strings are what prevent a "loosened until green" fix: a pattern that matched the wrong span, or no span, fails on content and not just on count.

**Unchanged and must stay green:** `test_demo_fixture.py::test_guardrail_escalation_reproduces_deterministically` (the $1.4M `guardrail_failed` outcome), `test_hallucinated_citation_fires`, `test_legitimate_citation_does_not_flag`, `test_market_vocabulary_is_not_flagged`, and `test_pipeline_scenarios.py`.

**Mutation proofs** (run by hand, restored, recorded in the report):

- (M1) Reinstate the global `re.IGNORECASE`: tests 1 and 2 fail.
- (M2, D2 only) Revert the name class to `[A-Z]`: the `Section 4.2` case fails.

**Expected count:** 366 / 0 / 7 baseline + **6** new = **372 passed, 0 failed, 7 skipped (379 collected)**. If D2 is declined, the count is +5, giving **371 passed (378 collected)**. `ruff` and `mypy` must be clean. **Halt on any failure before commit.**

---

## 6. Part C — the lesson, recorded

Add to `docs/BACKLOG.md` → *Future work*: **"Guardrail rule-engine test corpus from more than one model"**, with the prompt's rationale and proposal (real Adjuster reasoning paragraphs from Mistral Large and Claude Haiku, pulled from audit rows, run through the rule engine as a no-false-positive suite). The entry notes that the three 8.6 Haiku paragraphs were the first informal use of this idea (§0) and that the entry is **not built**.

In the same edit, the resolved *"Guardrail citation-regex false positive — blocks the Phase 8.6 verification"* item is removed from *Pending verifications*. It points to the 8.6.1 build-log entry.

---

## 7. Version

`pyproject.toml` and the project entry in `uv.lock` go from `0.8.6` to `0.8.6.1`, the same two places as previous bumps. `/health` reads the package version, so it needs no code change. This is a single-file hotfix, so it is numbered as a point release, per the *Phase-numbering convention*.

---

## 8. Deployed verification: the full Phase 8.6 sequence, from scratch

Field checks per scenario are the Phase 8.6 plan §5 table, unchanged.

0. **Render env check (Dermot):** no `LLM__*` variables; `MISTRAL_API_KEY` present.
1. `GET /health` → `version = 0.8.6.1` (after the push and the Render deploy).
2. **Reset Neon.** Hostname gate (`.neon.tech`), then `uv run python -m backend.data.seed_claims --allow-truncate`. Expect 9 claims at `received`, `audit_log` empty, `policy_chunks` untouched. **No `index_policy`.** This discards the `8bff04e2` evidence rows, which are already recorded in the 8.6 report and build log and quoted verbatim in test 1.
3. **Three scenarios.**
   - **Auto-approve: Dermot triggers it from the Claims page and inspects the four agent panels in the UI.** It must land at `settled` with **no** fired rules. I read the audit rows via the API.
   - Threshold and guardrail: API-driven by me. Expected `awaiting_human`, with `settlement_over_ceiling` and `guardrail_failed` respectively.
   - Every run: 7 entries, and every §5 field checked.
4. **`v1_mistral` abort proof** on a `Background Claimant NN` claim. Run on `default` first (replay needs a prior terminal run), then `POST /api/pipeline/replay/{claim_id}?variant=v1_mistral`. Expect `aborted`, `coverage_check.llm_call.provider = "mistral"`, `requested_model = "mistral-large-2512"`, and 403 in `error`.
5. **One live `v2_strict_validator` replay on the auto-approve claim**, after step 3 is recorded. Proposed: triggered from the Run Detail *Re-process* control (Dermot), since the step exists to prove that control. Pass criteria:
   - a new run exists
   - `pipeline_started.variant = "v2_strict_validator"`
   - `coverage_check` on `anthropic` / Haiku with the strict template
   - 7 entries
   - a non-`aborted` terminal state

   The strict template may legitimately lower validator confidence and escalate, so `settled` vs `awaiting_human` is **recorded, not judged**. See risk R2.
6. `GET /api/audit/verify/{any correlation id}` → `ok: true` across the whole ledger.
7. **Record:**
   - Build log: a Phase 8.6.1 entry (the fix, D2, tests, both mutation proofs, and the `Section 4.2` report correction), plus a *Deployed verification outcome* amendment to the Phase 8.6 entry (passed on 8.6.1; three-scenario table and both variant proofs).
   - `CLAUDE.md`: clear *Demo status: blocked*.
   - `docs/BACKLOG.md`: discharge the Phase 8.4 / 8.5.2 seven-entry item in *Pending verifications*.
   - Write `18-…-report.md`.

**Halt rule:** a wrong terminal state on any scenario in step 3 halts again. I report with the audit rows, and do no retuning.

**Commits** (per the commit-and-push-after-verified-deliverable standing preference):

- (C1) Code, tests, version, the 8.6.1 build-log entry, BACKLOG Part C, `CLAUDE.md` and this plan, after the suite is green. Push, which triggers the Render deploy.
- (C2) The verification record and the report, after step 7.

---

## Files

| File | Change |
|---|---|
| `backend/app/agents/guardrail_rules.py` | `_CITATION_CANDIDATE_RE` scoped flag (+ `[A-Z0-9]` if D2); comment; module docstring. The only code file. |
| `backend/tests/test_guardrail.py` | 6 new tests (5 without D2). |
| `pyproject.toml`, `uv.lock` | `0.8.6.1` |
| `docs/BACKLOG.md` | Part C entry; remove the resolved regex item; later, discharge the seven-entry item |
| `docs/build-log.md` | 8.6.1 entry; 8.6 verification amendment |
| `CLAUDE.md` | Current Status |
| `docs/prompts/18-…-plan.md` / `-report.md` | this plan; the report |

No interface change: flag `kind`/`detail` format, audit payload shape, and HTTP responses are all unchanged. The only behavioural change is which reasoning strings produce a `hallucinated_citation` flag. No new dependencies.

---

## Risks

- **R1 — D2 new flagging surface** on the auto-approve scenario (§1 D2). Mitigated by the three-paragraph corpus check; not eliminated. If it fires, the halt rule applies.
- **R2 — step 5 changes the auto-approve claim's demo state.** Replaying `v2_strict_validator` on the auto-approve claim may leave it at `awaiting_human` rather than `settled`. The claim's latest run is what the Claims page shows. If the demo needs a clean auto-approve afterwards, that means another Neon reset and a single default auto-approve run, which is outside this phase unless you ask.
- **R3 — Haiku non-determinism.** Auto-approve could fail on confidence rather than the Guardrail. That is a halt, not a retune, and the audit rows would show which.
- **R4 — §4 greedy capture** could flag a capitalised, genuine section name that Haiku writes. It would show as a `detail` with trailing lowercase words, distinct from the 8.6 signature. Halt.

---

## Decisions for Dermot

1. **D2:** name group `[A-Z0-9]` (recommended) or keep `[A-Z]` and backlog the numeric miss.
2. **Step 5 trigger:** Re-process from the UI by you (recommended), or API-driven by me. Also: accept R2 (the auto-approve claim may not stay `settled`)?

## Optional suggestions (not in scope; not built)

- Backlog the two §4 false-positive classes (greedy name capture; missing leading `\b`) as a follow-on rule-engine hardening item, ideally built together with the Part C corpus that would prove it.
- Give `test_legitimate_citation_does_not_flag` a sentence that actually produces a candidate found in the allow-set (for example `per section Named Perils Covered, which…`), so the allow-set path is really tested.

---

## Decisions taken (approved 21 September 2026)

- **D2:** `[A-Z0-9]` — adopted.
- **Step 5:** run on a **second** `Background Claimant` claim, distinct from step 4's and from the scenario claims, triggered from the UI's *Re-process* control by Dermot. **R2 therefore no longer applies** — no scenario claim's recorded terminal state is disturbed.
- **Optional suggestion folded in:** `test_legitimate_citation_does_not_flag` rewritten so it actually forms a citation candidate and the allow-set is what keeps the flag away.
- **Test count:** 7 new tests, not 6 — M1 showed that the single `sub-limit of $25,000` case passed *with the defect reinstated*, because the allow-set happened to contain "of". It became a two-case parametrised test asserting at candidate level. Final suite: **373 passed, 0 failed, 7 skipped**.
