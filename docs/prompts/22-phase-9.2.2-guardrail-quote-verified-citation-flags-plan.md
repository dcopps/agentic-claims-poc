# Phase 9.2.2 — Plan: the Guardrail's LLM citation flag must quote its evidence, and code verifies it

**Prompt:** `22-phase-9.2.2-guardrail-quote-verified-citation-flags.md`. **Version:** `0.9.1.1 → 0.9.1.2`. **Status:** awaiting approval — no prompt, code or fixture has been changed.

Inputs read before planning: the prompt; `docs/BACKLOG.md` → *Phase 9.2.2*; the Phase 9.2.1 report and build-log entry with the 30 October addendum; `backend/app/agents/guardrail.py`, `guardrail_models.py`, `guardrail_rules.py`; `backend/app/prompts/system/guardrail.md`; `backend/tests/test_guardrail.py`, `test_guardrail_prompts.py`, `test_guardrail_replay.py`, `guardrail_replay_fixture.py`; `backend/app/runs/repository.py` and `backend/app/api/agents_test.py` (the two other consumers of `GuardrailFlag`); `frontend/src/api/types.ts`; the seven replay fixtures.

---

## 0. Findings that shape the plan

1. **The regex already separates the three failing phrases from a real citation.** I ran `_CITATION_CANDIDATE_RE` over the `adjuster_reasoning` of all seven fixtures. It matches nothing in any of the six Harborline texts and matches exactly one span in Coral Bay: `Endorsement Coastal Surge Rider`. So *"market range"*, *"moderate-severity band"*, *"sudden failure"*, *"supply line"* and *"$200,000 ceiling"* all fail the provision-shape test by construction, and once the check is in code **no quote from any of the six must-pass texts can be counted, whatever the model says** — the only remaining way those cases go red is a parse failure (fail-closed, unchanged behaviour). §5 states this per phrase.
2. **The flag model is a locked Phase 3 shape that reaches HTTP.** `GuardrailFlag` (`extra="forbid"`) is serialised into the audit (`rule_checks.flags[]`, `output.flags[]`), rebuilt from the audit by `runs/repository.py` for `GET /api/runs/{id}` (`guardrail_output.flags[]`), returned by `POST /api/agents/test/guardrail`, and carried in the SSE `agent_completed` payload. The prompt expects `quote: str | None` on the flag model *and* forbids changing any HTTP response shape; the two cannot both hold. §2 and §3 resolve it with a dedicated claim model and keep `GuardrailFlag` untouched (decision D1). The frontend never reads `flags` (its `GuardrailOutput` type has `passed` and `summary` only), so neither option touches the UI.
3. **The rule engine instance already carries the oracle.** `GuardrailRuleEngine.citation_pattern` is a public field; the agent holds the engine as `self._rule_engine`. The verifier takes that pattern as an argument, so nothing imports the private `_CITATION_CANDIDATE_RE`, a test engine with a custom pattern is honoured, and the regex is reused, not copied.
4. **`_parse_llm_flags` would reject a `quote` today.** It validates each item straight into `GuardrailFlag` with `extra="forbid"`, so the first model reply carrying `quote` would be a schema failure (fail-closed). The parse step therefore changes with the prompt, in the same commit.
5. **The replay test parses with `_parse_llm_flags` directly** (`_replay_once`). It must parse *and verify* the same way the agent does, or it would keep judging the model's raw claims and stay red. The seven-fixture corpus is the acceptance test only once the replay path matches the agent path.
6. **`_build_audit_payload` is already over the 50-line limit** (known debt, backlog). The new keys go in through an extracted helper rather than more lines in that function.
7. **No existing unit test sends an LLM `hallucinated_citation` flag through `evaluate`** (`test_llm_flags_are_merged_with_rule_flags` uses `bias`), so nothing in the suite is silently changed by the discard path; the new behaviour gets its own tests.

---

## 1. The prompt change — `backend/app/prompts/system/guardrail.md`

Only the *Output format* section and one bullet under *Rules* change. *Role*, *What is, and is not, a policy citation* and *How to reason* are byte-identical to the 9.2.1 text.

```diff
 ```json
 {
   "flags": [
     {
       "kind": "pii | bias | hallucinated_citation",
-      "detail": "short phrase identifying what tripped the flag, ≤300 chars"
+      "detail": "short phrase identifying what tripped the flag, ≤300 chars",
+      "quote": "hallucinated_citation only: the provision's title or number, copied verbatim from the adjuster's reasoning"
     }
   ],
   "summary": "one-sentence summary of the scan, ≤500 chars"
 }
 ```

 Rules:

 - `flags` is a JSON array; emit `[]` when nothing additional was found (the empty list is the success case).
 - Each `kind` MUST be one of the three exact strings `pii`, `bias`, or `hallucinated_citation`. Anything else is rejected.
 - `detail` is non-empty, ≤300 characters, and describes *what* tripped the flag (e.g. `"references claimant's age"`), not the full snippet.
+- `quote` is required on every `hallucinated_citation` flag: the exact words of the reasoning that name the provision, copied verbatim — no paraphrase, nothing added, nothing dropped. A citation flag whose quote is not found in the reasoning does not count. Omit `quote` on `pii` and `bias` flags.
 - `summary` is non-empty, ≤500 characters, and states whether the reasoning is clean or briefly notes which categories you raised.
```

The system/user separation is unchanged; the user template is untouched. `guardrail_max_tokens` (512) has ample room for the extra field. The three existing golden-shape tests still pass; §4 adds one.

---

## 2. The verification code

**Where.** A new sibling module `backend/app/agents/guardrail_llm_flags.py` (guardrail.py is 532 lines; the verifier, its two models and its helpers are a self-contained unit with their own tests). `guardrail.py` changes in three places: `_parse_llm_flags` returns claims, `_invoke_llm` verifies them, `_build_audit_payload` records the outcome.

**Models** (Pydantic v2, `extra="forbid"`, in the new module):

```python
DiscardReason = Literal["no_quote", "quote_not_in_reasoning", "quote_not_a_provision"]

class LLMFlagClaim(BaseModel):
    """What the model asserted, before code has checked it. Never leaves the agent."""
    kind: GuardrailFlagKind
    detail: str = Field(min_length=1, max_length=300)
    quote: str | None = None

class DiscardedLLMFlag(BaseModel):
    """A claim the code refused to count, with the reason. Audit and log only."""
    kind: GuardrailFlagKind
    detail: str
    quote: str | None
    reason: DiscardReason

@dataclass(frozen=True)
class LLMCheckOutcome:
    counted: list[GuardrailFlag]        # source="llm", merged with the rule flags as today
    discarded: list[DiscardedLLMFlag]
```

`GuardrailFlag` is **not** changed (D1). A claim is promoted to a `GuardrailFlag` only after verification; a `quote` on a `pii` or `bias` claim is accepted by the schema and dropped at promotion — ignored, not an error, as the prompt requires. A `quote` of the wrong JSON type (a number, a list) is a schema failure and raises as any malformed reply does today.

**`verify_llm_flags(claims, *, reasoning, citation_pattern) -> LLMCheckOutcome`**, applied per claim in this order:

1. **Sanitise** the quote: `strip()`; remove one layer of wrapping quote characters (`'`, `"`, `‘ ’`, `“ ”`) — the model habitually writes `'supply line'`; straighten curly quotes and apostrophes inside it.
2. **Validate**, first failure wins:
   - `kind != "hallucinated_citation"` → not subject to the check; promote unchanged.
   - quote `None` or empty after sanitising → `no_quote`.
   - quote not located in the reasoning (below) → `quote_not_in_reasoning`.
   - `citation_pattern.search(located_span)` is `None` → `quote_not_a_provision`.
3. **Abort** that claim: append a `DiscardedLLMFlag`, log at INFO (below), continue with the next claim. A discard is a recorded outcome, not an exception; the exception path stays reserved for a reply the agent cannot parse.
4. **Execute**: `GuardrailFlag(kind=..., detail=..., source="llm")`.

**Locating the quote — the normalisation, stated.** Both sides are straightened (curly → straight quotes and apostrophes); the quote is split on whitespace and rebuilt as a pattern of `re.escape(token)` joined by `\s+`, compiled with `re.IGNORECASE`, and searched in the reasoning. So the containment test is **case-insensitive**, **tolerant of whitespace runs and line breaks**, and **tolerant of curly/straight quote differences**; no other character mapping (dashes, ligatures, NFKC) is applied, and the plan says so because every tolerance is a way for a non-verbatim quote to pass. The match returns **the reasoning's own span**, and the provision-shape test runs on that span, not on the model's string — so a model that capitalises *"endorsement x"* cannot manufacture the capital letter the regex requires. `search`, not `fullmatch`, because the quote may legitimately carry a few surrounding words (*"coverage extended under Endorsement Coastal Surge Rider"*); what is tested is whether the quoted span contains a named provision.

**A property worth stating.** A counted LLM citation flag is, by construction, a span of the reasoning that matches the rule engine's own candidate regex. The rule engine has therefore already seen it and either flagged it (the LLM duplicates nothing, per the prompt) or allowed it because the name is a substring of a retrieved chunk. The LLM path's remaining independent contribution is the case where the model disagrees that an allowed name really is the provision the chunk carries — which is the semantic judgement the LLM was kept for. The backlog's stated trade-off stands: a hallucinated citation written without a provision keyword (*"the coastal surge rider"* in lower case) no longer counts from the LLM path alone; the regex is the place to widen, separately.

**Function sizes.** `verify_llm_flags` ≈ 20 lines; `_discard_reason` ≈ 15; `_locate_quote` ≈ 10; `_sanitise_quote` ≈ 8. All under the 30-line prompt.

**Logging.** The module takes `_logger = logging.getLogger(__name__)` (the pattern `pipeline.py` and `event_bus.py` use; stdlib records are what the Azure Monitor distro exports, so these land in App Insights as traces). One INFO record per discard: `Guardrail discarded an LLM hallucinated_citation flag: reason=%s quote=%r detail=%r`, quote truncated to a named constant `_LOG_QUOTE_CHARS = 200` through the existing `_excerpt` helper. Never silent.

**Agent wiring.** `_parse_llm_flags` keeps every guard it has (block, JSON, object, `flags` key, list, item objects) and validates items into `LLMFlagClaim` instead of `GuardrailFlag` (the `source` stamp moves to promotion). `_invoke_llm` calls `verify_llm_flags(claims, reasoning=adjuster_result.output.reasoning, citation_pattern=self._rule_engine.citation_pattern)` and returns the outcome. Its five-element tuple would become six, so it returns a small frozen dataclass `LLMCall(response, outcome, error, latency_ms, request)` instead — a module-private signature, no interface. Both `evaluate` and the test-bench `check` go through `_invoke_llm`, so the probe endpoint applies the same check; its response model (`GuardrailTestResult`) is unchanged.

---

## 3. The audit extension — interface-stability event, acknowledged

Additive keys at the top level of the `output_check` payload, alongside `rule_checks`, `llm_call`, `output`, `error`:

```json
"llm_flags_discarded": [
  {"kind": "hallucinated_citation",
   "detail": "references '$200,000 ceiling' as a policy limit; no such limit appears in retrieved chunks",
   "quote": "$200,000 ceiling",
   "reason": "quote_not_a_provision"}
],
"llm_flags_counted": [
  {"kind": "hallucinated_citation",
   "detail": "reasoning assumes coverage under 'Endorsement Coastal Surge Rider' …",
   "quote": "Endorsement Coastal Surge Rider"}
]
```

- Both keys are **always present** and are `[]` when empty — including on the provider-error and parse-failure paths, where nothing was verified (the `error` block says why) — so the shape is stable across every row written from this version on. Rows written before `0.9.1.2` lack the keys; readers treat absence as "no verification was performed" (the runs repository does not read them).
- `llm_flags_discarded` is the key the prompt asks for. `llm_flags_counted` (decision D2) records the verified quote for the flags that *did* count; without it the audit would carry the evidence for every refusal and none for any acceptance, which contradicts the audit-log-as-trusted-record property. For `pii` / `bias` flags from the LLM, `quote` is `null`.
- **Existing keys unchanged**, byte for byte: `input`, `rule_checks`, `llm_call` (with `prompt`, `requested_model`, `provider`), `output` (`passed`, `flag_count`, `flags[]` still `{kind, detail, source}`), `error`.
- **No SSE and no HTTP change.** `GuardrailFlag` and `GuardrailOutput` are untouched; `GET /api/runs/{id}`, `POST /api/agents/test/guardrail` and the stream carry exactly what they carry today. (Under the alternative in D1 the serialised flag would gain an optional `quote` key on all three surfaces; that is why it is not recommended.)
- On completion the entry goes into `CLAUDE.md` → *Locked interface extensions since Phase 4*: "Guardrail `output_check` audit gains top-level `llm_flags_discarded: [{kind, detail, quote, reason}]` and `llm_flags_counted: [{kind, detail, quote}]` — Phase 9.2.2. Always present, `[]` when empty. Additive; `output.flags[]` unchanged."

`pii` and `bias` flags are unchanged by this phase: no quote required, no discard path, same counting as today.

---

## 4. Tests

**New — `backend/tests/test_guardrail_llm_flags.py`** (no database, no network):

| Test | Asserts |
|---|---|
| `test_citation_without_quote_is_discarded` | one discarded, `reason == "no_quote"`, counted empty; the same for `quote: ""` and `quote: "  "` |
| `test_quote_absent_from_reasoning_is_discarded` | `reason == "quote_not_in_reasoning"` |
| `test_quote_without_provision_shape_is_discarded` (parametrised over `market range`, `moderate-severity band`, `sudden failure`, `supply line`, `$200,000 ceiling`, each embedded in a reasoning) | `reason == "quote_not_a_provision"` |
| `test_well_formed_quote_is_counted` | `Endorsement Coastal Surge Rider` → one `GuardrailFlag`, `source == "llm"`, discarded empty |
| `test_quote_with_surrounding_words_is_counted` | `"coverage extended under Endorsement Coastal Surge Rider"` counts (`search`, not `fullmatch`) |
| `test_containment_normalisation` (parametrised) | wrapping `'…'`/`“…”` stripped; curly vs straight apostrophe; case difference; line break inside the quote — all locate |
| `test_shape_is_judged_on_the_reasoning_span` | reasoning says `endorsement coastal surge rider` (lower case), model quotes it capitalised → `quote_not_a_provision` |
| `test_pii_and_bias_pass_through_untouched` | with and without a `quote`; promoted unchanged, nothing discarded, `quote` dropped |
| `test_first_failing_check_names_the_reason` | a quote that is both absent and shapeless reports `quote_not_in_reasoning` (order is part of the contract) |
| `test_discard_is_logged_at_info_with_truncated_quote` | `caplog`: one INFO record, reason and detail present, a 400-char quote truncated to 200 |
| `test_custom_citation_pattern_is_honoured` | a narrower pattern passed in changes the verdict (proves the oracle is the argument, not the module constant) |

**Modified — `backend/tests/test_guardrail.py`** (agent level, mock provider, real Postgres):

- `test_llm_citation_claim_without_provision_shape_does_not_fail_the_claim`: reasoning with *"market range"*, mock LLM returns a citation flag quoting it → `passed is True`; audit `llm_flags_discarded == [{…, "reason": "quote_not_a_provision"}]`, `llm_flags_counted == []`, `output.flags == []`.
- `test_llm_citation_claim_with_verified_quote_fails_the_claim`: reasoning cites `Sub-Limits Debris removal` (allowed by the rule engine because *debris removal* is in a chunk, so the rule engine is silent); mock LLM flags it with that quote → counted, `passed is False`, `llm_flags_counted[0]["quote"]` is the span. This is the LLM-only path that still works.
- `test_audit_records_empty_verification_lists_on_clean_and_error_paths`: both keys `[]` on the clean path and on the provider-exception path.
- `test_quote_on_pii_flag_is_ignored`: counted as `pii`, no `quote` anywhere in `output.flags`.
- The three parse-failure tests keep passing unchanged (the guard order in `_parse_llm_flags` is preserved).

**Modified — `backend/tests/test_guardrail_prompts.py`:** `test_system_prompt_requires_a_verbatim_quote_on_citation_flags` — `"quote"` appears in the output format and the rules say `verbatim`; verified to fail on the 9.2.1 prompt.

**Modified — `backend/tests/test_guardrail_replay.py`:** `_replay_once` parses *and verifies* with the default rule engine's pattern, returning counted flags; `_describe` also prints the discarded claims with their reasons so a red case is diagnosable from the failure message; `test_invented_endorsement_is_caught_without_the_rule_engine` additionally asserts the counted flag was quote-verified (i.e. appears in `counted`, not only in the raw claims). Docstring: seven fixtures, 24 calls, and the sentence about the two red tripwires is replaced by the acceptance statement.

**Mutation proof** (recorded in the report): with the `verify_llm_flags` call replaced by "promote every claim", the five `quote_not_a_provision` cases, `test_citation_without_quote_is_discarded` and the agent-level discard test fail; with the prompt's `quote` line removed, the golden-shape test fails. Both reverted before commit.

**Acceptance — the live corpus.** `RUN_LLM_E2E_TESTS=1`: every `expected: pass` fixture passes 3/3 and Coral Bay flags 3/3 without the rule engine. Outcomes recorded **before** (current code, current prompt — the 29/30 October state, for the record) and **after**, per fixture, in the report; a 2-of-3 anywhere is reported as 2-of-3.

---

## 5. Expected replay behaviour, stated before running

| Fixture | Model's flag under 9.2.1 | Expected quote | Expected outcome under 9.2.2 |
|---|---|---|---|
| `08d514f2` (1 Oct) | *market range / market band* | `market range` or `market band` | discarded `quote_not_a_provision` → **pass** |
| `f02fb888` (26 Oct) | *moderate-severity band / market range*; earlier also *no section authorising the amount* | the phrase; the amount flag likely has no quotable provision | `quote_not_a_provision`; the amount flag `no_quote` or `quote_not_a_provision` → **pass** |
| `8590b47e` (26 Oct) | passed under 9.2.1 (*sudden failure* under the old prompt) | `sudden failure` if raised | `quote_not_a_provision` → **pass** |
| `8e886c66` (29 Oct, script) | *supply line* | `supply line` | `quote_not_a_provision` → **pass** |
| `2c42cf40` (30 Oct, Vercel) | *$200,000 ceiling* | `$200,000 ceiling` | `quote_not_a_provision` (no keyword precedes the number; the digit rule applies to the name *after* a keyword) → **pass** |
| `ded5557b` (21 Sep) | clean | — | **pass** |
| `b35b146b` Coral Bay, no rule engine | *Endorsement Coastal Surge Rider* | `Endorsement Coastal Surge Rider` | located, matches → **counted, flags 3/3** |

**What would survive.** Nothing in the six must-pass texts can: §0.1 shows the regex matches none of them, so no span the model can quote from them passes the shape test. The one risk runs the other way: if the model quotes Coral Bay's provision *without* its keyword (*"Coastal Surge Rider"* alone, or *"the coastal surge rider"*), the no-rule-engine test fails on `quote_not_a_provision`. That outcome is reported as the trade-off the backlog named, not fixed by widening the regex in this phase. The as-recorded Coral Bay case is unaffected either way (the rule engine's flag carries it). A model that answers with two JSON objects (*"Actually, let me reconsider"*, seen on 29 October) is still a parse failure and fail-closed; that behaviour is unchanged and would show as a red case with a parse error, not a discard.

---

## 6. Change governance

**Class: Normal.** Same reasoning as 9.2.1: the placeholders do not change, but the change moves an eval result (the auto-approve scenario from `awaiting_human` to `settled` on two surfaces). Record in the Phase 9.2.2 build-log entry in the worked-example shape: *Change* — a `quote` field on the LLM citation flag and a code-side verification of it; *Trigger* — the 9.2.1 outcome (three distinct phrases, three surfaces); *Evidence* — the seven-fixture replay before and after, the mutation proof, the deployed runs; *Interface* — the additive audit keys; *Rollback* — revert the commit (no migration, no schema).

**Two doc touches.** One paragraph under *Observed in the prototype* in `docs/change-governance.md`: the control response completed in 9.2.2 — the model's judgement is kept for *finding* a suspicious reference and removed from *deciding* that it counts; the decision is a deterministic check that the audit records either way. One sentence appended to the Anthropic row's *Observed change* cell in `docs/dora-third-party-register.md`: control response completed in Phase 9.2.2 (`0.9.1.2`), the flag now counts only when code verifies its quote.

---

## 7. Deployed verification — Dermot present for the Azure part

Push deploys both stacks (`deploy-backend` rebuilds because `backend/` changes; Render auto-deploys). Then, in this order:

1. **Azure:** `scripts/azure-start.sh`; record the Postgres state first (auto-restart due about 5 November — it may already be `Ready`). The three scenarios through the Azure frontend.
2. **Vercel frontend against Render:** the three scenarios.
3. **Script against Render:** `scripts/verify-demo-scenarios.py --backend <render-url>`.

Expected on every surface: `settled` / `awaiting_human` (`settlement_over_ceiling`) / `awaiting_human` (`guardrail_failed`, `settlement_over_ceiling`); seven audit entries per run; chain `ok` over the whole ledger; every LLM call `anthropic` / `claude-haiku-4-5-20251001`. For Harborline the `output_check` payload is read back (read-only through the API) and expected to show either the model's flag in `llm_flags_discarded` with its reason — the talking point: the model's claim and the code's refusal side by side — or an empty list if the quote requirement itself disciplines the model into not flagging; both are a pass. For Coral Bay `output.flags` carries the rule-engine flag as today and `llm_flags_counted` may carry the model's quote-verified duplicate only if it ignored the no-duplicate instruction (acceptable, recorded). Halt and diagnose if any surface disagrees. `azure-stop.sh` last.

---

## 8. Docs

- `docs/build-log.md`: Phase 9.2.2 entry — diagnosis recap, the prompt diff, the verifier's three checks and normalisation, before/after replay table, mutation proof, deployed verification on the three surfaces, governance record.
- `docs/prompts/22-…-report.md`.
- `README.md`: known-issue note **removed**; *Before a demo* line updated — the seven-run replay is expected all green and stays as the pre-demo check; the sentence about the two red tripwires goes.
- `docs/BACKLOG.md`: the 26 October findings and the Phase 9.2.2 item closed (moved to the build log as the convention says); the Phase 9 paragraph renumbered (prompt 23 documentation phase, prompt 24 Foundry).
- `CLAUDE.md`: *Current Status* (date, phase, suite counts, live image); *Demo status* back to usable without caveat; *Escalation policy* note updated (the LLM check finds, code decides); the new *Locked interface extension* entry (§3); *What's next* → prompt 23 (plain-language documentation) then prompt 24 (Foundry).
- `docs/change-governance.md`, `docs/dora-third-party-register.md` as §6.

---

## 9. Version, dependencies, interface stability

- **Version:** `0.9.1.2` in `pyproject.toml` and `uv.lock`'s project entry. `/health` reports it on both stacks.
- **Dependencies:** none.
- **Interface stability:** one additive audit extension (§3), two keys, always present. `GuardrailFlag`, `GuardrailOutput`, SSE events, HTTP responses, `policy.yaml`, the rule engine, `_CITATION_CANDIDATE_RE` and the DB schema untouched. The system prompt's *Output format* changes (a prompt-contract change recorded as in 9.2.1); the user template does not.

---

## 10. Execution order

1. **Before-state replay** on the current code and prompt, recorded (the 29/30 October state, for the report's table).
2. New module + tests; `_parse_llm_flags` → claims; `_invoke_llm` verifies; audit helper; golden-shape test; prompt change. Full suite, `ruff`, `mypy`. Mutation proof run and reverted.
3. Replay module updated; **after-state replay** 3/3 per case, recorded.
4. Version bump; docs drafted (build log, backlog, CLAUDE.md incl. the locked-extension entry, governance, DORA). Commit; push. CI → `deploy-backend` → Render auto-deploy; `/health` `0.9.1.2` on both.
5. §7 verification: Azure (UI, Dermot present), Vercel (UI), Render (script). Harborline `output_check` payloads read back.
6. README note removed; report; build log and CLAUDE.md finalised; commit; push; `azure-stop.sh`.

---

## Files

**Created**
- `backend/app/agents/guardrail_llm_flags.py`
- `backend/tests/test_guardrail_llm_flags.py`
- `docs/prompts/22-phase-9.2.2-guardrail-quote-verified-citation-flags-plan.md` (this file), `-report.md`

**Modified**
- `backend/app/prompts/system/guardrail.md` — *Output format* and one rule (§1)
- `backend/app/agents/guardrail.py` — `_parse_llm_flags` → `list[LLMFlagClaim]`; `_invoke_llm` verifies and returns `LLMCall`; `_build_audit_payload` gains the two keys via an extracted `_llm_verification_block` helper; module docstring step 4 updated
- `backend/tests/test_guardrail.py`, `test_guardrail_prompts.py`, `test_guardrail_replay.py` (§4)
- `pyproject.toml`, `uv.lock` — version
- `README.md`, `CLAUDE.md`, `docs/build-log.md`, `docs/BACKLOG.md`, `docs/change-governance.md`, `docs/dora-third-party-register.md`

**Untouched, deliberately:** `guardrail_rules.py`, `guardrail_models.py`, `policy.yaml`, `user/guardrail_template.md`, `runs/repository.py`, `api/agents_test.py`, every fixture, the frontend.

---

## Risks

- **Coral Bay without the keyword** (§5): the one way the acceptance can go red for a reason the design accepts. Reported, not patched.
- **Parse failures stay fail-closed.** A two-object reply still escalates; the quote field does not change that. The replay would show it as an error, distinguishable from a discard.
- **Tolerances in the containment test** are each a route for a non-verbatim quote to be located. They are limited to case, whitespace and quote glyphs, and the shape test runs on the reasoning's own span, so a located-but-reworded quote cannot gain a capital letter or a keyword it does not have in the text.
- **`_build_audit_payload`** must not grow; the helper extraction keeps it where it is (still over the limit — the backlog item to split all four builders stands).
- **Old audit rows** lack the two keys; nothing reads them today, and the reconstruction in `runs/repository.py` reads `output` only.

---

## Decisions requested at the approval gate

- **D1 — Flag model.** *Recommended:* keep `GuardrailFlag` untouched and verify through an internal `LLMFlagClaim`; the quote lives in the audit only (§2, §3). *Alternative:* `quote: str | None = None` on `GuardrailFlag` as the prompt's item 2 expects — simpler, but it adds an optional `quote` key to every serialised flag in the audit `output.flags[]` / `rule_checks.flags[]`, in `GET /api/runs/{id}`, in the probe endpoint and in the SSE payload, which the prompt's *must not* forbids.
- **D2 — Record counted quotes too** (`llm_flags_counted`). *Recommended:* yes, so the audit holds the evidence for acceptances as well as refusals. The prompt asks only for the discarded list; saying no leaves one key.
- **D3 — Normalisation** as stated in §2 (case, whitespace runs, curly/straight quotes, one layer of wrapping quotes; shape judged on the reasoning's span; no dash or Unicode folding). *Recommended:* yes.
- **D4 — New module** `guardrail_llm_flags.py` rather than growing `guardrail.py`. *Recommended:* yes.
- **D5 — Replay judges counted flags** (the agent's verdict), with discards printed in the failure message. *Recommended:* yes; it is the only way the corpus is the acceptance test.

---

## Optional enhancements (clearly labelled; not in scope unless approved)

- **Run Detail UI:** show `llm_flags_discarded` on the Guardrail card ("the model said / the code refused"). Fits Phase 8.7 UI polish; the audit already carries everything needed.
- **Replay as a scheduled job** against the live model (the production control described in `change-governance.md`), as a GitHub Actions workflow on a schedule with the API key as a secret. Out of scope; noted for the documentation phase's gap list.
- **Regex widening** for provision names without a keyword — a separate, flagged change to the rule engine if a real citation ever misses; not this phase.

---

## Approval

**Approved 30 October 2026 (Dermot).** D1: `GuardrailFlag` untouched, verification through the internal claim model, quote in the audit only. D2: yes — `llm_flags_counted` recorded as well. D3, D4, D5 as recommended. The Coral Bay no-rule-engine risk is accepted as the stated trade-off: if the model quotes the provision without its keyword, report it as observed; do not widen the regex. Execution in the order of §10, stopping before the push so Dermot is present for the deployed verification on all three surfaces.
