# Report 10 — Phase 8.2: Doc-Parser Refactor (Claim Record as Source of Truth)

## Summary

**Recap.** Doc-Parser no longer asks Haiku to extract structured fields. The
`claims` row — set at submission time, the system-of-record — is now the source
of truth for `loss_date`, `jurisdiction`, `claim_type`, `claimed_amount`, and
`claimant_identifier`. Haiku is called only to generate `narrative_summary`, the
one field that genuinely needs natural-language understanding. `DocParserOutput`'s
shape is unchanged (locked Phase 3), so no downstream consumer is affected; the
audit payload gains one additive top-level field, `"fields_source": "claim_record"`,
so the trail records honestly where each field came from. Version bumped to 0.8.2.
Next: clone-and-run verification.

**Completed at:** 2026-06-15T17:50:28Z
**Phase:** 8.2 — Doc-Parser refactor (claim record as source of truth)
**Status:** Complete (no deferrals)

**Links**

- Prompt: [`docs/prompts/10-phase-8.2-doc-parser-refactor.md`](10-phase-8.2-doc-parser-refactor.md)
- Plan (approved): [`docs/prompts/10-phase-8.2-doc-parser-refactor-plan.md`](10-phase-8.2-doc-parser-refactor-plan.md) — approved 2026-06-15T17:50:28Z
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 8.2 entry)
- Repository: pushed to `main` after this commit lands; Render auto-redeploys.

**CI status.** Unchanged. No new gated categories.

---

## The refactor — what changed and why

### Why

Phase 8 rehearsal showed Haiku reliably *defaults* the structured fields to
placeholders (`1900-01-01`, `"United States"`, `"Unknown"`, `"0.00"`) even when
the narrative states them clearly. Those placeholders then trip `DocParserOutput`
validation (`claimed_amount` must be `> 0`) and abort the pipeline. Phase 8.1 tried
the prompt-engineering route — worked examples for hedged dollar figures — and the
live rehearsal proved it didn't change the model's behaviour. The architectural
answer is to stop asking Haiku to do what it isn't good at.

### What

- **`backend/app/agents/doc_parser.py`.** `DocParser` now injects a
  `ClaimsRepository` (default `ClaimsRepository()`), mirroring the Adjuster's
  `MarketDataTable` injection. `_load_narrative` became `_load_claim_record`,
  returning the typed `ClaimRecord` and raising `ValueError` on a missing claim or
  an empty narrative. `_invoke_llm` now returns a validated summary **string** —
  the JSON machinery (`_parse_output`, the `_extract_json_block` import, `json`) is
  gone. Three small module helpers carry the new logic: `_validate_summary` (the
  length/content guard), `_output_from_record` (the single place the
  `reported_amount → claimed_amount` and `claimant_name → claimant_identifier`
  mapping lives), and `_probe_output` (sentinel structured fields for the test
  bench). The file is shorter than before the refactor.
- **Prompts.** `prompts/system/doc_parser.md` is now a focused "narrative
  summariser" instruction: plain prose, one paragraph, ≤500 characters, no JSON.
  `prompts/user/doc_parser_template.md` passes the narrative and asks for the
  summary. The extraction rules and hedged-dollar examples are deleted.
- **Frontend.** `AgentTestPanel` gained an additive optional `note?` prop; the
  Doc-Parser panel on `AgentsPage` uses it to explain the sentinel behaviour: the
  probe path's structured fields are sentinels because there is no claim record to
  read.

### Validation strategy

Haiku now returns prose, so there is nothing to parse — only to bound.
`_validate_summary` strips the response, rejects empty/whitespace-only output, and
rejects anything over the 500-character cap (which mirrors
`DocParserOutput.narrative_summary`), each with the offending text in the message.
No `json.loads`. The validated string drops into `DocParserOutput` alongside the
record-sourced structured fields.

---

## The additive `"fields_source"` audit field

The Doc-Parser `doc_extract` audit payload gains one top-level field,
`"fields_source": "claim_record"`, sibling to `input` / `llm_call` / `output` /
`error` (the same placement as the Adjuster's top-level `demo_fixture`). The
`output` block still carries the full field set; the `llm_call` block now reflects
a call that produced only the summary. This is an **additive interface extension**
— existing keys are unchanged, so the audit-log-as-trusted-record property holds —
and it joins the Phase 5/6/7 extensions on the locked list in `CLAUDE.md`.

---

## Architectural narrative

> Doc-Parser now treats the claim record as the source of truth for structured
> data — `loss_date`, `jurisdiction`, `claimant_identifier`, `claimed_amount`, and
> `claim_type` come from the database columns set at submission time, not from LLM
> extraction. The LLM is called only for `narrative_summary`, which is the one task
> in this agent that genuinely requires natural-language understanding. The audit
> payload records this honestly via the additive `"fields_source": "claim_record"`
> field. This is a stronger architectural narrative than "Doc-Parser extracts
> everything from the narrative": the data flows are explicit, the LLM is used only
> where it's reliably good, and the audit trail explains exactly where each field
> came from.

This talking-point is worth surfacing in any future demo or interview: the change
makes the system *more* honest and *more* robust at once — the placeholder-default
failure mode is structurally impossible now, and the audit trail says so.

---

## Deviations from the approved plan

The plan anticipated rewriting the four JSON-path tests in `test_doc_parser.py`. In
execution a **fifth** obsolete test surfaced: `test_prompt_loader.py`'s Phase 8.1
`test_doc_parser_prompt_covers_hedged_dollar_figures` (six parametrised cases) pinned
the few-shot dollar-extraction block into the prompt — the exact approach Phase 8.2
removes. It was deleted, with a comment pointing at the replacement summariser-prompt
golden test. This is consistent with the plan's intent (remove tests that assert
behaviour the refactor eliminates), just broader in scope than the plan named.

Two test redesigns were required by the new data flow and are worth recording:

- **`test_runs_repository.py::test_reconstruct_aborted_run`** previously aborted
  Doc-Parser with `doc_text="not valid json at all"`. With no JSON parsing left,
  that is a *valid* summary; the abort trigger is now an empty/whitespace response,
  which the summary guard rejects.
- **`test_runs_repository.py::test_compare_same_claim_reveals_diff`** expected an
  $85k→$850k settlement jump on a single claim. Once the record is authoritative,
  the Adjuster range-checks the settlement against the record's $85k water-damage
  band, so that jump is unreachable. The test now expresses the variant difference
  through the adjuster-confidence floor (a different in-band settlement plus a
  sub-0.75 confidence), preserving the same compare-feature coverage.

No other deviations.

---

## Guard clauses added beyond the spec

- `_load_claim_record` re-checks the loaded record's narrative is non-empty before
  the summary call — the spec called for the missing-claim guard; the empty-narrative
  guard is carried over from the previous `_load_narrative` behaviour so the contract
  (an empty narrative is a hard failure) is unchanged.

---

## Tests

| Suite | Count | Delta vs Phase 8 |
|---|---|---|
| Backend (`uv run pytest`) | 327 passing, 7 skipped | −3 |
| Frontend (`vitest`) | 30 passing | 0 |

The backend delta is net-negative because the refactor removes more tests than it
adds: four JSON-path tests and six hedged-dollar regression cases are deleted
(behaviour that no longer exists), while two summary-guard tests and several
record-sourcing assertions are added. Every new guard clause has a triggering test
asserting on message content. `ruff` clean; `mypy backend` clean (106 files);
frontend `tsc` / `eslint` / `vitest` clean.

---

## Optional enhancements (labelled; not built)

- **Narrative-vs-record consistency check.** Haiku could be asked to flag a
  contradiction between the narrative and the structured fields (e.g. narrative says
  "Bermuda" but the record says "United Kingdom"). A defensible regulator-flavoured
  check; needs a separate LLM call and a new audit step. Deferred to Phase 9+.
- **Vision-enabled Doc-Parser.** The original Phase 3 deferral; the
  structured-fields-from-record refactor reduces its urgency. Still deferred.

---

## Action items for the architect

1. **Confirm `/health` reports `version=0.8.2`** on the deployed backend after Render
   redeploys.
2. **Re-run the rehearsal end-to-end.** All three scenarios should reproduce live:
   scenario 1 settles (Doc-Parser populates `claimed_amount=85000.00` from the
   record), scenario 2 escalates on threshold only, scenario 3 escalates on guardrail
   (via the unchanged Phase 7 fixture path). The Neon database does **not** need
   re-seeding.
3. **Spot-check one Doc-Parser run's audit payload** in the audit viewer and confirm
   `"fields_source": "claim_record"` is present.
