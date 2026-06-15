# Prompt 10 — Phase 8.2: Doc-Parser Refactor (Claim Record as Source of Truth)

## Read first

This is a small, focused architectural refactor of a single agent, prompted by a demo-rehearsal discovery. Plan-first applies but the surface is narrow.

Before doing anything else, read these files:

- `CLAUDE.md` — standing instructions, locked architectural decisions, the "Locked interface extensions since Phase 4" subsection.
- `docs/prompts/09-phase-8-demo-polish-fixes-report.md` — what Phase 8 shipped and the discovery that prompted this Phase 8.2.
- `backend/app/agents/doc_parser.py` — the current implementation; `_load_narrative`, `_invoke_llm`, and `_parse_output` are the focus of the change.
- `backend/app/agents/doc_parser_models.py` — `DocParserOutput`'s shape is **locked** (Phase 3 interface; Adjuster, audit payload, and compare view all depend on it). Don't change it.
- `backend/app/prompts/system/doc_parser.md` and `backend/app/prompts/user/doc_parser_template.md` — to be replaced with much simpler versions.
- `backend/app/claims/models.py` and `backend/app/claims/repository.py` — `ClaimRecord` and `ClaimsRepository.get` are the source-of-truth read.
- `backend/app/agents/adjuster.py` — Adjuster consumes `DocParserOutput`; verify it doesn't read any field that's about to change population semantics.
- `backend/tests/test_doc_parser.py` — existing test patterns; many tests need updating because they mock Haiku producing the full extraction.
- `backend/tests/test_pipeline_scenarios.py` — the three end-to-end scenario tests; they should still pass with mocked LLM responses for the narrative_summary task.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout: plan-first, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts, system/user separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Refactor Doc-Parser so the structured fields on `DocParserOutput` are sourced from the `claims` table directly, and Haiku is asked only for the one thing it's reliably good at: generating `narrative_summary`. The agent's interface, position in the pipeline, and audit payload shape are unchanged; only its implementation strategy changes.

Why: live testing during Phase 8 rehearsal showed that Haiku reliably fails to extract `loss_date`, `jurisdiction`, `claimant_identifier`, and `claimed_amount` from narratives, even when they're present and well-formed. Haiku defaults every uncertain field to a placeholder (`1900-01-01`, `"United States"`, `"Unknown"`, `"0.00"`), which then trips Pydantic validation and aborts the pipeline. The prompt-engineering route (worked examples, hedging-language guidance) was tried in Phase 8.1 and didn't change the model's behaviour. The architectural answer is to stop asking Haiku to do what it isn't good at.

By the end of this phase:

- `Doc-Parser` loads the full `ClaimRecord` from the database (not just the narrative), populates `DocParserOutput`'s structured fields directly from the record's columns, and calls Haiku **only** to generate `narrative_summary`.
- The system and user prompts shrink dramatically — the system prompt is now a focused "summarise this narrative" instruction; the extraction rules go away.
- All three demo scenarios reproduce live cleanly: scenario 1 settles, scenario 2 escalates on threshold only, scenario 3 escalates on guardrail (via the existing Phase 7 fixture path).
- `DocParserOutput`'s shape is unchanged — downstream consumers (Adjuster, audit payload, compare view, frontend types) are not affected.

Per-phase preamble fix-up bundled into the same commit:

- Bump `pyproject.toml` version `0.8.1` → `0.8.2`. The `/health` `version` field then reads `0.8.2` after the push, confirming this code is live.

## Current state of the project (for orientation)

Phase 8 shipped six demo-polish fixes including the live pipeline visualisation, the AgentCard running state, and the Guardrail market-vocabulary tuning. Phase 8.1 strengthened the Doc-Parser prompt with worked examples for hedged dollar figures — and the live rehearsal proved that didn't work; Haiku 4.5 still defaults the structured fields rather than extracting them. The `/health` endpoint reports `version=0.8.1`. The deployed Neon database carries the re-seeded narratives with explicit dollar figures (which Haiku still won't extract).

The three demo scenarios pass under unit tests (which mock the LLM at the LLMProvider boundary) but scenarios 1 and 2 abort live because Doc-Parser's schema validation fails on `claimed_amount=0.00`. Scenario 3 doesn't even reach the Guardrail because Doc-Parser aborts first.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a short plan covering everything below.

### Cross-cutting questions

Each has a recommendation; confirm or argue back.

1. **Where does the claim record load happen?** Recommended: `Doc-Parser` injects a `ClaimsRepository` collaborator (same pattern as the Adjuster's `MarketDataTable` injection) and calls `ClaimsRepository.get(conn, claim_id)`. Alternative: a direct SQL query inside Doc-Parser's `_load_*` helper (matches the current `_load_narrative` style). Recommend the repository injection — it's the established pattern and gives tests a clean seam.

2. **Does the `parse(narrative)` probe path change?** The probe path is the agent test bench: it accepts an arbitrary narrative with no claim_id and produces a typed output. **Open question**: with the refactor, the structured fields come from the claim record, so the probe path no longer has access to them. Two options:
   - (a) The probe path accepts a `ClaimSubmission`-shaped input (full structured + narrative), and the test bench UI is updated to allow that. Most architecturally consistent but breaks the test bench's existing one-field-per-agent shape.
   - (b) The probe path keeps a single-narrative input, populates the structured fields with sentinel values (`loss_date=1970-01-01`, `claimed_amount=Decimal("0.01")`, `jurisdiction="Unknown"`, `claimant_identifier="Unknown"`, `claim_type` derived from a minimal regex, `narrative_summary` from Haiku as today). Probe output is then explicitly labelled as "summary only — structured fields are sentinels".
   - Recommend **(b)** — preserves the test bench's interface contract and labels the limitation honestly. The frontend's `AgentTestPanel.tsx` gets one copy-string update explaining the sentinel behaviour for Doc-Parser's panel. Confirm.

3. **What happens to the `claim_type` field?** It's currently extracted by Haiku from the narrative; it's also a structured column on `claims.claim_type` set at submission time (Phase 5 constrains it to a `Literal` of six market-data keys). Recommended: use `claims.claim_type` directly. The narrative-derived value was redundant; the structured field is authoritative.

4. **The Doc-Parser audit payload — change implication.** The `output` block in the audit payload currently contains all extracted fields. With the refactor, those fields come from the claim record, not from Haiku. The audit still records what Doc-Parser produced (which is correct and consistent with the upstream record), but the `llm_call` block now reflects a call that only generated `narrative_summary`. Recommended: leave the audit payload shape unchanged, but add one additive field at the top level: `"fields_source": "claim_record"` (vs the historical implicit `"llm_extraction"`). This makes the audit honestly say "the structured fields came from the database, not the LLM" without changing the shape. **This is an additive interface extension; flag it on the locked-extensions list in `CLAUDE.md` alongside the Phase 5/6 additions.**

5. **The system + user prompts shrink to one focused task.** The new `prompts/system/doc_parser.md` should be roughly:

   ```
   # Role

   You are the narrative summariser for a commercial property insurance carrier. Your single job is to read a free-text first-notice-of-loss claim narrative and produce a one-paragraph plain-prose summary of what happened.

   # Output format

   Return only the summary text. No JSON, no Markdown, no preamble, no fencing. Plain prose, one paragraph, ≤500 characters, capturing the cause, the affected location, and the loss in your own words. Do not quote the narrative verbatim. Do not include speculation, coverage opinions, or settlement amounts beyond what the narrative states.
   ```

   And the user template:

   ```
   # Claim narrative

   {claim_narrative}

   # Task

   Produce the one-paragraph summary specified in your system instructions. Plain prose only — no JSON, no fencing, no preamble.
   ```

   The structured-field extraction rules and the hedged-dollar-figure examples are deleted entirely. The prompt is now ~10 lines.

6. **Validation of the LLM output.** Currently `_parse_output` does JSON parsing + schema validation. With the new prompt, Haiku returns a plain text summary, no JSON. Recommended: a simple length guard (1-500 chars after strip, raises `ValueError` if out of bounds) and a basic content guard (rejects empty/whitespace-only). No JSON parsing. The narrative_summary string then drops into `DocParserOutput` alongside the structured fields from the claim record.

### Backend changes

- `backend/app/agents/doc_parser.py`:
  - Inject `ClaimsRepository` in `__init__`.
  - `_load_narrative` becomes `_load_claim_record` returning a `ClaimRecord`.
  - `_invoke_llm` simplifies: builds the simplified prompt, calls the provider, gets back a text response, runs the length+content guards, returns the summary string. No JSON parsing.
  - `evaluate` and `parse` assemble `DocParserOutput` from the structured fields + the LLM-generated summary.
  - `parse` probe path uses sentinel values per cross-cutting Q2.
  - Audit payload gains the additive `"fields_source": "claim_record"` field per Q4.
- `backend/app/agents/doc_parser_models.py`: **no change**. `DocParserOutput`'s shape is locked.
- `backend/app/prompts/system/doc_parser.md`: replaced with the simplified version per Q5.
- `backend/app/prompts/user/doc_parser_template.md`: replaced with the simplified version per Q5.
- `pyproject.toml`: version `0.8.1` → `0.8.2`.

### Frontend changes

Minimal:

- `frontend/src/components/AgentTestPanel.tsx` (or wherever the Doc-Parser test-panel copy lives): update the description/help text on the Doc-Parser panel to say *"Generates a narrative summary. Structured fields are populated from sentinel values in the test bench (the live pipeline uses the claim record's structured columns)."*

### Settings

- `doc_parser_max_tokens`: can be reduced from its current value to something appropriate for a 500-character summary (~150 tokens, generously). Recommend keeping current value to avoid a settings change; note in the plan that it's now over-provisioned but not wrong.
- No other settings change.

### Testing strategy

Aim ~6–10 changed or new tests:

- **Doc-Parser unit tests** (`backend/tests/test_doc_parser.py`):
  - Existing tests that mocked Haiku producing the full JSON extraction need rewriting to mock Haiku producing just the summary text and verify the structured fields come from the injected `ClaimsRepository` stub.
  - One new test: missing claim (the repo returns `None`) → `ValueError` with the claim_id.
  - One new test: provider error → wrapped and audited.
  - One new test: provider returns an empty/whitespace summary → `ValueError` with the response excerpt.
  - One new test: provider returns a summary >500 chars → `ValueError`.
  - One new test: happy path — structured fields populated from a fake `ClaimRecord`, summary populated from a mocked Haiku response, full audit entry written with `"fields_source": "claim_record"`.
- **Probe path test** (`test_doc_parser.py` or `test_agent_probe.py`): verify the probe accepts a raw narrative and returns a `DocParserOutput` with sentinel structured fields plus an LLM-generated summary.
- **Integration scenario tests** (`backend/tests/test_pipeline_scenarios.py`): the three scenarios should still pass with their existing LLM mocks (now returning summary strings instead of JSON blobs). Update the mock provider's Doc-Parser response accordingly.
- **Audit regression**: assert the audit payload now contains `"fields_source": "claim_record"` under the `output` block (or wherever the additive field lands).

Every guard clause gets a triggering test asserting on message content.

### CI changes

None. No new gated test categories.

### New dependencies — flag each one

Expected answer: **none**. The refactor moves logic, doesn't introduce new capability.

### Risks and downstream impacts

**Locked at end of Phase 8.2** (added to the existing list):

- The additive `"fields_source"` field on the Doc-Parser `doc_extract` audit payload. Joins the Phase 5/6 extensions in `CLAUDE.md`.

**Not changed:**

- `DocParserOutput` Pydantic shape.
- Adjuster's input shape (still reads `DocParserOutput`).
- Pipeline orchestrator's call to `DocParser.evaluate(claim_id, correlation_id)`.
- SSE event payloads.
- Frontend types.

**Risk to flag:** the existing audit-trail story is now *strictly more honest* — the audit log says explicitly that the structured fields came from the claim record, not the LLM. This is a *win* for the architectural narrative ("the claim record is the source of truth for structured data; the LLM is used only for what it's reliably good at"), but Phase 8.2's report should articulate that talking point so it surfaces in any future demo or interview conversation.

### Deployment steps requiring architect involvement

- Verify the Render redeploy completes and `/health` reports `version=0.8.2`.
- The Neon database does not need re-seeding (Phase 8 already did that; the narratives in the database are fine).
- Re-run the rehearsal end-to-end. All three scenarios should reproduce live: scenario 1 settles cleanly (Doc-Parser populates `claimed_amount=85000.00` from the record); scenario 2 escalates on threshold only (no Doc-Parser failure); scenario 3 escalates on guardrail (via the Phase 7 fixture path, unchanged).

### Optional enhancements (labelled; not built)

Carried forward (still deferred): retry via `tenacity`; pricing-table population; real PII redactor; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings` fields; idempotent re-run helper exposed on UI; `claim_status_history` table; auth on the human decision endpoint; audit pagination; dark mode; prompt-diff in the comparison view; standalone ADR log; eager orchestrator construction option.

New for Phase 8.2 (labelled, not built):

- **Doc-Parser narrative-vs-record consistency check** — Haiku could be asked to flag any contradiction between the narrative and the structured fields (e.g., narrative says "Bermuda" but record says "United Kingdom"). Defensible regulator-flavoured check; would require a separate LLM call and a new audit step. Deferred; useful as a Phase 9+ enhancement if the demo benefits.
- **Vision-enabled Doc-Parser** — the original Phase 3 deferral; Haiku 4.5 has vision; could extract from uploaded FNOL form images. Still deferred; the structured-fields-from-record refactor reduces the urgency.

### Save the plan

Save the plan **before** asking me to review it. Write to:

```
docs/prompts/10-phase-8.2-doc-parser-refactor-plan.md
```

Top-level heading: `# Plan 10 — Phase 8.2: Doc-Parser Refactor`. Below that, the body of the plan.

After saving the file, point me at it and ask for my verdict. Do not write any other code yet.

## Step 2 — Approval or rejection

Same workflow as previous phases.

**If I approve:**

Append a horizontal rule and an `## Approval` section to the plan file. Order so the timestamp closes the file:

```
## Approval

**Approval message:** "<my exact approval message, quoted>"

---

**Approved by:** Dermot Copps
**Approved at:** <ISO 8601 timestamp in UTC>
```

Then proceed to Step 3.

**If I reject**, append a `## Rejection` footer, rename to `10-phase-8.2-doc-parser-refactor-plan-rejected-NN.md`, produce a revised plan, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 8.2. Constraints from `CLAUDE.md` apply throughout:

- Defensive programming on the new claim-record load path (`ClaimsRepository.get` returning `None` → `ValueError` with claim_id; record fields validated as expected types).
- Function size limits — the refactor should shrink Doc-Parser overall, not grow it.
- Type hints throughout.
- Tests per the strategy above.
- Anonymisation: client name does not appear anywhere.
- Externalised prompts: the new system and user prompts live in the existing `.md` files; no inline strings.
- Interface stability: `DocParserOutput` shape locked; `"fields_source"` field is additive.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.8.1` → `0.8.2`.

## Step 4 — Log

Append a new entry to `docs/build-log.md` with the standard fields:

- Date.
- Phase / Prompt: link to this prompt.
- Plan (approved): link to the plan.
- Plan iterations: count of rejected revisions.
- Report: link to the report file.
- Prompt summary.
- What changed: every file created or modified, one line each.
- Tests: count and pass rate.
- Issues discovered.
- Architectural talking-point added to the report (see Step 5).
- Next: clone-and-run verification (per the original BUILD-PLAN end state).

## Step 5 — Write the report

Save to `docs/prompts/10-phase-8.2-doc-parser-refactor-report.md`. Standard `## Summary` block in the established order:

- Recap — done plus next.
- Completed at — ISO 8601 UTC.
- Phase — `8.2 — Doc-Parser refactor (claim record as source of truth)`.
- Status — Complete / Complete with deferrals.
- Links to prompt, approved plan, repository.
- CI status if relevant.

Body sections cover the refactor (what changed and why), the additive `"fields_source"` audit field, deviations from the plan, any optional enhancements newly recommended.

**Include an explicit "Architectural narrative" subsection** articulating the talking-point this refactor introduces:

> *Doc-Parser now treats the claim record as the source of truth for structured data — `loss_date`, `jurisdiction`, `claimant_identifier`, `claimed_amount`, and `claim_type` come from the database columns set at submission time, not from LLM extraction. The LLM is called only for `narrative_summary`, which is the one task in this agent that genuinely requires natural-language understanding. The audit payload records this honestly via the additive `"fields_source": "claim_record"` field. This is a stronger architectural narrative than "Doc-Parser extracts everything from the narrative": the data flows are explicit, the LLM is used only where it's reliably good, and the audit trail explains exactly where each field came from.*

That paragraph belongs in the report so future you (or any reviewer of the prompts archive) can find the rationale without re-reading the plan.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section:

- Date: today's date in ISO format.
- Phase: "Phase 8.2 complete; clone-and-run verification next".
- What works: a one-line summary noting Doc-Parser now sources structured fields from the claim record; all three demo scenarios reproduce cleanly live.
- What's next: "Clone-and-run verification."

Also add the additive `"fields_source": "claim_record"` field to the "Locked interface extensions since Phase 4" subsection.

## Step 7 — Git

Single commit covering all the Phase 8.2 work, message:

```
Phase 8.2: Doc-Parser refactor — claim record as source of truth

- DocParser sources structured fields (loss_date, jurisdiction, claim_type, claimed_amount, claimant_identifier) from ClaimRecord directly; Haiku is called only for narrative_summary
- prompts/system/doc_parser.md and prompts/user/doc_parser_template.md shrunk to the focused summary task
- DocParserOutput shape unchanged (locked Phase 3 interface)
- Audit payload gains additive "fields_source": "claim_record" — honest about where each field came from
- Probe path keeps single-narrative input with sentinel structured fields, labelled in the test-bench UI
- All three demo scenarios now reproduce live cleanly (auto-approve, threshold escalation, guardrail escalation)
- pyproject.toml version bumped 0.8.1 -> 0.8.2
- Approved plan archived; build log appended; report written
- CLAUDE.md Current Status updated; locked-extensions list extended
```

Push to `main`; Render auto-deploys.

## Step 8 — Report back

Per the global "After coding" section:

- Files created and modified.
- Test count and pass rate, with breakdown.
- Any design decisions that differ from the spec.
- Any guard clauses added that were not in the spec.
- Any optional enhancements you recommend.

End with the action items I still need to handle:

- Verify the Render redeploy completes and `/health` reports `version=0.8.2`.
- Re-run the rehearsal end-to-end. Confirm scenarios 1/2/3 all reproduce cleanly. The agent cards should light up progressively (Phase 8's UI fix is unchanged); the Doc-Parser card should now show all expected fields populated; the pipeline should settle (scenario 1), escalate on threshold (scenario 2), and escalate on guardrail (scenario 3).
- Spot-check one Doc-Parser run's audit payload (via the audit viewer) and confirm `"fields_source": "claim_record"` is present.

## Save this prompt

Per the "Save every prompt" standing instruction in `CLAUDE.md`, save this prompt verbatim to `docs/prompts/10-phase-8.2-doc-parser-refactor.md` if it isn't already there.
