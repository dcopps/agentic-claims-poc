# Phase 8.5.2 — Pin Mistral model to `mistral-large-2512` — REPORT

**Date:** 2026-09-14
**Prompt:** [`15-phase-8.5.2-pin-mistral-model.md`](15-phase-8.5.2-pin-mistral-model.md)
**Plan:** [`15-phase-8.5.2-pin-mistral-model-plan.md`](15-phase-8.5.2-pin-mistral-model-plan.md) (approved with amendments, recorded in the plan)

## Summary

Production run `26a9bf4e-44ce-49c9-bc99-aeaed33c9f8f` aborted at the Validator
with `403 tier_not_allowed`: Mistral re-pointed the `mistral-large-latest` alias
at a paid-tier release, and the account is on the Free tier. Both Mistral-backed
defaults (Validator, Adjuster) are now pinned to `mistral-large-2512` — the
release the alias resolved to when the prototype was built in May, still on the
Free tier's accessible list. Local suite unchanged at **338 passed, 0 failed,
7 skipped**. Deployed verification pending the Render redeploy.

## Files modified

| File | Change |
| --- | --- |
| `backend/settings.py` | `validator_model` / `adjuster_model` defaults → `mistral-large-2512`; pin-by-policy comment added (amendment). |
| `backend/settings.yaml.template` | Lines 62-63 pinned, with a pointer to the `settings.py` comment; commented pricing example key → `mistral-large-2512`. |
| `backend/tests/test_settings_phase1.py` | Default assertions → `mistral-large-2512`. |
| `backend/tests/test_settings_phase2.py` | Pricing-map example key → `mistral-large-2512`. |
| `pyproject.toml`, `uv.lock` | Version `0.8.5.1` → `0.8.5.2` (lock's project entry rewritten by `uv`). |
| `docs/BACKLOG.md` | *Pending verifications* updated to the combined 8.4 + 8.5.2 deployed run (version, fresh template claim, Render env-var check, both model assertions); *Future work* gains *Mistral tier upgrade path* (verbatim body) and *Startup model-access probe* (amendment); Phase 8.6 version base → `0.8.5.2`. |
| `docs/build-log.md` | Phase 8.5.2 entry. |
| `CLAUDE.md` | Current Status → Phase 8.5.2 / `0.8.5.2`. |
| `docs/prompts/15-phase-8.5.2-pin-mistral-model-plan.md` | Plan, plus approval-amendments section. |
| `docs/prompts/15-phase-8.5.2-pin-mistral-model-report.md` | This report. |

No files created in code. No production logic touched — only the two default
string values. LLM Gateway variant mechanism untouched. No Mistral account
changes.

## The pin-by-policy comment

```python
# Pinned to a dated release, never the `-latest` alias. Mistral re-points
# aliases server-side without notice: in Phase 8.5.2 `mistral-large-latest`
# moved to a paid-tier release and every Validator call failed with a 403
# `tier_not_allowed`. A pinned version also keeps the audit log's
# `llm_call.model` truthful — an alias never records which model answered.
# Move the pin forward deliberately (see docs/BACKLOG.md, "Mistral tier
# upgrade path"); do not revert it to an alias.
validator_model: str = "mistral-large-2512"
adjuster_model: str = "mistral-large-2512"
```

The Anthropic defaults already use dated identifiers for Haiku
(`claude-haiku-4-5-20251001`); the comment is scoped to the Mistral block because
that is where the incident happened and the policy was decided.

## Caller sweep

Full table with per-occurrence verdicts in the plan (§1) and the build-log
entry. Result: 4 locations updated (settings default, template values, template
pricing example, two test files); 7 occurrences deliberately left (mock inputs in
`test_api_logger.py` and `test_llm_provider_mistral.py`, three archived prompt
files, and an unrelated fine-tune identifier in `change-governance.md`).
`test_variants.py` has no literal and needed nothing. Post-change re-sweep of
`backend/` and `frontend/src` for `mistral-large-latest` finds only the "stays"
test inputs and the new explanatory comment.

## Verification

| Check | Result |
| --- | --- |
| `uv run pytest` (against `agentic_claims_test`) | **338 passed, 0 failed, 7 skipped** (345 collected) — identical to Phase 8.5.1 |
| `uv run ruff check .` | All checks passed |
| `uv run mypy` | Success: no issues found in 108 source files |
| `importlib.metadata.version("agentic-claims-poc")` | `0.8.5.2` |

**Deployed verification: pending** — see *Next* below. Outcome to be appended here.

## Design decisions that differ from the spec

- **One extra "must update" occurrence:** the commented pricing example at
  `settings.yaml.template:92`, not in the prompt's starting list. Pricing is
  keyed by exact model string, so a copied `-latest` example would silently null
  every Validator/Adjuster `cost_usd`. Comment-only change.
- **`test_settings_phase2.py` updated although string-agnostic.** The prompt's
  condition (runtime pricing lookup by model ID) is met; the test itself doesn't
  depend on the default. Updated for alignment, not correctness.
- **Pin-by-policy comment** — added at Dermot's direction (plan amendment).
- **`docs/BACKLOG.md` Pending verifications rewritten** beyond the one requested
  backlog item, so the authoritative verification checklist matches the
  approved step 2 (fresh template claim) and step 4 (both models), and names
  `0.8.5.2`. Without this the backlog would direct the next session to reuse the
  seeded Northwood row and expect `0.8.5.1`.
- **Dev-DB note removed from `CLAUDE.md` *What's next*.** It is already
  tracked in `docs/BACKLOG.md` → *Local `agentic_claims_dev` bootstrap*; the
  status line now points at the backlog for everything else pending.

## Guard clauses added

None. No logic changed.

## Interface stability

Value change only in `llm_call.model` (audit) and `model` (API-call log) for
Mistral-backed calls. No shape, field, column, HTTP or SSE change. Existing
audit rows and the hash chain untouched. Documented in the plan (§2) and build log.

## Next

1. Dermot confirms no `LLM__MISTRAL__*` env var on Render.
2. Render redeploys from the pushed commit.
3. `/health` → `0.8.5.2`.
4. Fresh claim via the *Threshold escalation ($850k fire)* template → Process.
   Validator completes, `awaiting_human`, four panels filled, no *Audit entry
   not found* banners, seven audit entries, chain verified.
5. `coverage_check` **and** `settlement_estimate` both show
   `llm_call.model = "mistral-large-2512"`.
6. Append outcome to this report and the build log; that also closes the
   Phase 8.4 carry-over.

## Suggestions for follow-on improvements

- *Startup model-access probe* — logged in `docs/BACKLOG.md` (amendment).
- **Render env-var inventory in the repo.** A short, value-free list of the
  env-var *names* the deployed backend expects (e.g. in `docs/` or a
  `render.yaml` without secrets) would make Risk 1–style checks a file read
  rather than a dashboard visit. Not actioned.
