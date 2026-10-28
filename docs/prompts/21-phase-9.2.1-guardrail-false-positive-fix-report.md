# Phase 9.2.1 — Report: Guardrail false positives on the auto-approve scenario

**Date:** 28 October 2026 — **in progress; stopped before the Azure session** (per the approval: "stopping before the Azure deployment steps so I can be present").
**Plan:** [`21-phase-9.2.1-guardrail-false-positive-fix-plan.md`](21-phase-9.2.1-guardrail-false-positive-fix-plan.md)
**Version:** `0.9.1 → 0.9.1.1`

## Summary

The Guardrail system prompt now defines a citation as a provision named by title or number, lists what is not a citation, states that coverage was decided upstream and is not re-judged, and reasons from the Adjuster's text outward instead of from the policy inward. A gated replay test renders recorded Guardrail inputs through the current prompt against the live model; a read-only extraction script builds those fixtures from a deployed audit log with a lossless round-trip proof. The deployed Adjuster temperature becomes 0 through settings (Bicep parameter on Azure; dashboard variable on Render), default untouched. Everything that does not need Azure or a push is built, linted, type-checked and committed locally. The Azure half — the four required fixtures, the before/after replay on them, the Bicep deploy, the push and the deployed verification — is listed under *Pending* in the build-log entry.

## Files

**Created:** `backend/tests/guardrail_replay_fixture.py`, `backend/tests/test_guardrail_replay.py`, `backend/tests/fixtures/guardrail_replay/ded5557b-harborline-render-21-september.json`, `scripts/extract-guardrail-replay-fixture.py`, this report and the plan.

**Modified:** `backend/app/prompts/system/guardrail.md`; `backend/tests/test_guardrail_prompts.py` (+1); `backend/settings.py`, `backend/settings.yaml.template` (comments); `infra/bicep/modules/containerapps.bicep`, `infra/bicep/main.bicep`, `infra/bicep/main.bicepparam`; `pyproject.toml`, `uv.lock` (version); `docs/build-log.md`, `docs/BACKLOG.md`, `README.md` (pre-demo check added; known-issue note stays until verified), `CLAUDE.md`, `docs/change-governance.md`, `docs/dora-third-party-register.md`.

**Not touched, by instruction:** `guardrail_rules.py`, `policy.yaml`, `guardrail_template.md`, the demo fixture, anything on Vercel or Neon beyond one read-only query, any audit payload shape.

## Tests

Suite **385 passed, 1 failed, 9 skipped** (from 382 / 0 / 7). New: three contract tests and one golden-shape test (always run); two gated live tests (the parametrised replay and the Coral Bay no-rule-engine case). The failure is `test_corpus_contains_the_four_required_runs`, by design, until the four Azure fixtures are extracted. `ruff check .`, `uv run mypy backend` (114 files), `az bicep build` + `lint` all clean. No function over 30 lines in the new modules.

## Mutation proof so far

- Golden-shape test: fails on the old prompt (neither "coverage has already been decided" nor "market range" present), passes on the new.
- `ded5557b` (Harborline, Render, 21 September 2026): **passed 3 / 3 under the old prompt today** and 3 / 3 under the new. Recorded as observed: it does not reproduce the 26 October finding. Its text says *"moderate-severity range"*, not the *"moderate-severity band"* / *"market range"* the 26 October runs used. The four Azure runs remain the proof; the table in the build-log entry is filled in the Azure session.

## Deviations from the plan

- Execution order: the fifth (Render) fixture was extracted first because it needed no Azure session; the plan listed it as optional and last. Approved as an optional item.
- The old prompt for the Azure "before" run will come from git (`2d6ad0c`) rather than from running before the file was edited, because the Azure fixtures were not reachable today. Same comparison, different sequencing.

## Guard clauses added beyond the spec

- The extraction script refuses to overwrite an existing fixture (no `--force` flag; delete the file deliberately if a re-extraction is wanted).
- `test_corpus_contains_the_four_required_runs` — an always-on tripwire that the required corpus is present, so a deleted fixture fails CI rather than silently shrinking the pre-demo check.
- `test_contract_rejects_a_malformed_fixture` — the contract's error names the file.

## Pending

See *Pending — the Azure session* in the Phase 9.2.1 build-log entry. This report is completed after the deployed verification.
