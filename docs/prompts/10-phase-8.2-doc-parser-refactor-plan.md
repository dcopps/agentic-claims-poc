# Plan 10 — Phase 8.2: Doc-Parser Refactor

**Claim record as source of truth for structured fields; Haiku for `narrative_summary` only.**

## Summary

Doc-Parser currently asks Haiku to extract every field on `DocParserOutput` as a
JSON blob, then defends against malformed JSON / schema failures. Live rehearsal
proved Haiku reliably *defaults* `loss_date`, `jurisdiction`, `claimant_identifier`,
and `claimed_amount` to placeholders that then trip Pydantic and abort the pipeline.
Prompt-engineering (Phase 8.1) did not move the model.

This refactor stops asking Haiku for what it isn't good at. The structured fields are
read from the `claims` row (the system-of-record, set at submission time); Haiku is
called only to write `narrative_summary`. `DocParserOutput`'s shape is unchanged, so no
downstream consumer is affected. The audit payload gains one additive top-level field,
`"fields_source": "claim_record"`, so the trail honestly records where the structured
data came from.

`/health` version bumps `0.8.1` → `0.8.2` in the same commit.

---

## Cross-cutting questions — my answers

**Q1 — Where does the claim-record load happen? → Confirm: inject `ClaimsRepository`.**
`DocParser.__init__` gains a `claims_repository: ClaimsRepository` collaborator (default
`ClaimsRepository()` in both `__init__` and `with_defaults`), mirroring the Adjuster's
`MarketDataTable` injection. `evaluate` calls `self._claims_repository.get(conn, claim_id)`.
Note: `ClaimsRepository`'s methods are `@staticmethod`, so the injection's real value is a
clean test seam (a stub exposing `.get`) rather than instance state — which is exactly
what the Adjuster-pattern precedent gives, so I'm matching it. This also lets me delete
the bespoke `_load_narrative` SQL and reuse the typed `ClaimRecord` read the rest of the
codebase already trusts.

**Q2 — Probe path. → Confirm option (b), with one argue-back on `claim_type`.**
The probe (`parse(narrative)`) keeps its single-narrative input. It assembles a
`DocParserOutput` from **sentinel** structured fields plus the Haiku-generated summary,
and the test-bench UI labels the limitation. Sentinels:
`loss_date=1970-01-01`, `claimed_amount=Decimal("0.01")`, `jurisdiction="Unknown"`,
`claimant_identifier="Unknown"`.

- **Argue-back:** for `claim_type` I recommend a fixed sentinel token (`"unknown"`)
  rather than "derived from a minimal regex". A regex re-introduces narrative parsing —
  the exact thing this phase is removing — for a value that is, by definition, a sentinel
  in the probe. A fixed token is more honest and avoids a second extraction code path
  that would contradict the architectural thesis. Sentinels live as named module
  constants with a comment. If you'd rather keep the regex, say so and I'll add it.

**Q3 — `claim_type`. → Confirm: use `claims.claim_type` directly.** The structured column
is authoritative; the narrative-derived value was redundant. `DocParserOutput.claim_type`
is typed `str` (not the `ClaimType` Literal), so seeded background types still validate.

**Q4 — Audit payload. → Confirm: additive top-level `"fields_source": "claim_record"`.**
Shape otherwise unchanged. I'll place it at the top level (sibling of `input`/`llm_call`/
`output`/`error`), matching the Adjuster's top-level `demo_fixture` precedent. The
`output` block still carries the full field set (now sourced from the record); the
`llm_call` block now reflects a call that produced only the summary. This is an additive
interface extension — added to the locked-extensions list in `CLAUDE.md`.

**Q5 — Prompts shrink to the summary task. → Confirm.** `prompts/system/doc_parser.md`
and `prompts/user/doc_parser_template.md` are replaced with the focused versions in the
prompt (role = narrative summariser; output = one plain-prose paragraph, ≤500 chars, no
JSON/fencing). All extraction rules and hedged-dollar examples deleted.

**Q6 — Output validation. → Confirm: length + content guard, no JSON.** Haiku returns
plain text. The new guard strips the response, rejects empty/whitespace-only, and rejects
length outside `[1, 500]` chars — raising `ValueError` with the response excerpt. The
validated string drops into `DocParserOutput.narrative_summary` (whose own Pydantic bound
is `1..500`, so the guard and the model agree). No `json.loads`, no `_extract_json_block`.

---

## Backend changes

**`backend/app/agents/doc_parser.py`** (net shrink expected):
- `__init__` / `with_defaults`: add `claims_repository: ClaimsRepository` (default
  `ClaimsRepository()`).
- Delete `_load_narrative`; add `_load_claim_record(conn, claim_id) -> ClaimRecord` using
  `self._claims_repository.get(...)`. Defensive: `None` → `ValueError` naming the
  `claim_id`; the returned record's `narrative` is re-checked non-empty (the summary call
  needs it) → `ValueError` if empty/whitespace.
- `_invoke_llm(narrative) -> (response, summary, error, latency_ms)`: builds the simplified
  prompt, calls the provider with `response_format="text"` (unchanged), runs the new
  length/content guard, returns the **summary string** (not a `DocParserOutput`).
- New module helper `_validate_summary(text) -> str` (the Q6 guard).
- New module helper `_assemble_output(*, loss_date, jurisdiction, claim_type,
  claimed_amount, claimant_identifier, narrative_summary) -> DocParserOutput` — the single
  place the `reported_amount→claimed_amount` / `claimant_name→claimant_identifier` field
  mapping lives. Used by both `evaluate` (record values) and `parse` (sentinels).
- `evaluate`: load record → `_invoke_llm` → on success `_assemble_output` from record
  columns + summary → write audit → return `DocParserResult`. Audit written on every exit
  path (unchanged contract).
- `parse` (probe): `_invoke_llm` → `_assemble_output` with sentinel structured fields.
- Delete `_parse_output` and the `_extract_json_block` / `json` imports it needed.
- `_build_audit_payload`: add top-level `"fields_source": "claim_record"`. The probe path
  writes no audit, so the sentinel source is never recorded as `claim_record` — only real
  `evaluate` runs do, which is correct.

**`backend/app/agents/doc_parser_models.py`** — **no change** (`DocParserOutput` locked).

**`backend/app/prompts/system/doc_parser.md`** — replaced (Q5).
**`backend/app/prompts/user/doc_parser_template.md`** — replaced (Q5).

**`pyproject.toml`** — version `0.8.1` → `0.8.2`.

---

## Frontend changes (minimal)

The Doc-Parser test-panel copy needs the sentinel caveat. `AgentTestPanel` is generic
(no description slot today), so:
- Add an optional `note?: string` prop to **`AgentTestPanel.tsx`**, rendered as muted
  helper text under the title.
- In **`AgentsPage.tsx`**, pass `note` to the Doc-Parser panel only:
  *"Generates a narrative summary. Structured fields are populated from sentinel values in
  the test bench (the live pipeline uses the claim record's structured columns)."*

This is additive and touches no other panel.

---

## Settings

`doc_parser_max_tokens` is now over-provisioned for a ≤500-char summary but not wrong.
**Recommend leaving it unchanged** to avoid a settings-schema churn for no behavioural
gain. No settings added or removed.

---

## Testing strategy (~8–10 changed/new)

**`backend/tests/test_doc_parser.py`** — the suite currently mocks Haiku emitting full
JSON; rewrite to mock Haiku emitting a summary string and read structured fields from the
inserted `claims` row (the suite already inserts real rows via `_insert_claim`):
- Rewrite `test_evaluate_returns_typed_result`: mock summary text; assert structured
  fields equal the inserted columns (`claimed_amount == reported_amount`,
  `claimant_identifier == claimant_name`, `loss_date`, `jurisdiction`, `claim_type`);
  assert `narrative_summary` came from the mock; assert audit `output` + new
  `fields_source == "claim_record"`; assert prompt is the summariser ("summar" in system).
- Keep/adjust `test_claim_not_found_raises` (now via the repository read).
- Keep `test_empty_narrative_raises` (record narrative empty → `ValueError`).
- **New** `test_empty_summary_raises_and_audits`: provider returns `"   "` → `ValueError`
  ("empty"/"whitespace") with excerpt; audit error row written.
- **New** `test_oversized_summary_raises`: provider returns 600 chars → `ValueError`
  (length) with excerpt.
- **New** `test_provider_error_wrapped_and_audited`: keep existing provider-error test
  (verifies wrap + audit).
- **Delete** the now-impossible JSON-path tests (`test_non_json_response_raises_and_audits`,
  `test_non_object_json_raises`, `test_schema_failing_json_raises`, `test_bad_date_raises`)
  — Haiku no longer returns JSON, so those guards no longer exist. Their *intent* (bad
  model output is a hard, audited failure) is preserved by the two new summary-guard tests.
- Keep `test_audit_payload_truncates_long_narrative` (narrative excerpt logic unchanged).
- Update the gated real-call test to assert a non-empty `narrative_summary` and that the
  structured fields equal the inserted record (not model-extracted).

**`backend/tests/test_agent_probe.py`** — `test_doc_parser_probe_no_audit`: mock returns a
summary string; assert `output.narrative_summary` populated, structured fields equal the
sentinels, and `_audit_count == 0`.

**`backend/tests/test_pipeline_scenarios.py`** — replace `_doc_json(...)` with a
`_doc_summary(...)` returning plain text; the three scenarios already insert rows whose
`claim_type`/`reported_amount` match the previous mock JSON, so downstream assertions
hold. The Phase-5 replay test uses the same swap.

**`backend/tests/test_demo_fixture.py`** — its `DocParser(...)` construction (line ~134)
will get the default repository; check its mock provider response is updated to a summary
string if it drives Doc-Parser. (Will confirm during execution.)

Every guard clause gets a triggering test asserting on message content.

---

## CI / dependencies

- **CI:** no change; no new gated categories.
- **Dependencies:** **none.** The refactor moves logic; `ClaimsRepository`, `ClaimRecord`
  are already in the codebase.

---

## Interface stability

- `DocParserOutput` Pydantic shape: **unchanged** (locked Phase 3).
- Adjuster input, orchestrator call `DocParser.evaluate(claim_id, correlation_id)`, SSE
  payloads, frontend types: **unchanged**.
- **Additive only:** audit payload top-level `"fields_source": "claim_record"`. Joins the
  Phase 5/6/7 extensions in the `CLAUDE.md` locked list.

---

## Risks / talking point

- **Risk (low):** the field-name mapping (`reported_amount→claimed_amount`,
  `claimant_name→claimant_identifier`) is the one place a silent wrong-wiring could hide.
  Mitigated by the single `_assemble_output` helper and an explicit equality test against
  the inserted row.
- **Architectural win to articulate in the report:** the audit trail is now *strictly more
  honest* — it states the structured fields came from the claim record, not the LLM. The
  claim record is the source of truth for structured data; the LLM is used only where it's
  reliably good (natural-language summary).

## Anonymisation note

Confirmed the client name appears nowhere in the touched surface; fixture names
(`Harborline Logistics Ltd`, `Synthetic Manufacturing Ltd.`, `Acme Ltd`) are generic
inventions and will stay. (Flagging because the session opened on a "names to search for"
reference — no action needed in this phase.)

---

## Optional enhancements (labelled; not built)

- **Narrative-vs-record consistency check** (carried from the prompt): Haiku could flag a
  contradiction between narrative and structured fields. Separate LLM call + new audit
  step. Deferred to Phase 9+.
- **Vision-enabled Doc-Parser**: original Phase 3 deferral; lower urgency now. Deferred.

---

## Execution order after approval

1. Backend: prompts → `doc_parser.py` → `pyproject.toml`.
2. Backend tests rewritten/added; `uv run pytest`, `ruff`, `mypy backend` clean.
3. Frontend: `AgentTestPanel.tsx` note prop + `AgentsPage.tsx` copy; `tsc`/`eslint`/vitest.
4. `docs/build-log.md` entry; report `…-report.md`; `CLAUDE.md` status + locked list.
5. Single commit per the prompt's message; push to `main`.

## Approval

**Approval message:** "Approved as written. Q2: pick option 1, the fixed "unknown" sentinel token. Confirmed sign-off on deleting the four JSON-path tests (their intent survives in the two new summary-guard tests). Confirmed the note? prop addition to AgentTestPanel. Then append the ## Approval footer and proceed to Step 3."

---

**Approved by:** Dermot Copps
**Approved at:** 2026-06-15T17:50:28Z
