# Report 08 — Phase 7: Demo Polish and Documentation

## Summary

**Recap.** Phase 7 expands the README to its final demo-ready form, ships the change-governance / DORA / design-decisions / walkthrough / verification docs and the Azure CI/CD reference, and closes the scenario-3 live-reproducibility gap with a deterministic, auditable Adjuster demo fixture. Next: clone-and-run verification.

**Completed at:** 2026-06-15T11:05:00Z
**Phase:** 7 — Demo polish and documentation
**Status:** Complete (no deferrals; optional enhancements carried forward, labelled)

**Links**

- Prompt: [`docs/prompts/08-phase-7-demo-polish-and-documentation.md`](08-phase-7-demo-polish-and-documentation.md)
- Plan (approved): [`docs/prompts/08-phase-7-demo-polish-and-documentation-plan.md`](08-phase-7-demo-polish-and-documentation-plan.md) — approved 2026-06-15T10:30:53Z
- Build-log entry: [`docs/build-log.md`](../build-log.md) (Phase 7 entry)
- Repository: pushed to `main` after this commit lands; Render auto-redeploys.

**CI status.** Unchanged. The verification script is a local/architect run, not a CI gate. No new gated categories.

---

## Documentation artefacts shipped (with line counts)

| Artefact | Lines | Notes |
|---|---|---|
| `README.md` (expanded) | ~230 | Locked nine-section structure; headline diagram inline; dev→prod table; four diagrams in `<details>` |
| `docs/design-decisions.md` | ~110 | Six trade-offs in depth (README §7 links here) |
| `docs/change-governance.md` | ~115 | Standard/Normal/Emergency taxonomy + CCB table + three worked examples with diffs |
| `docs/dora-third-party-register.md` | ~95 | Per-provider tables (role / substitution path / exercised? / Art. 28 rationale) + concentration summary |
| `docs/walkthrough.md` | ~120 | Scene-by-scene 3-minute demo script |
| `docs/verification/phase-7/scenarios.md` | ~85 | Three scenarios, input + expected + evidence placeholders |
| `infra/azure-devops-pipeline.yml` | ~200 | Nine-stage production pipeline; each stage names its production equivalent |
| `scripts/verify-demo-scenarios.py` | ~165 | Stdlib runner; submits + runs + asserts the three scenarios |

The README is concise-but-complete (~230 lines rather than padding to 400+): every locked section is present with its key claims, and the deeper material is split into the linked docs rather than inlined.

---

## Code changes and tests

- `backend/data/demo_fixtures/guardrail_adjuster.json` — the fixture (planted "Endorsement Coastal Surge Rider").
- `backend/app/agents/adjuster.py` — `evaluate` fixture branch keyed on the claim's `scenario_tag`; `_load_demo_fixture` / `_read_scenario_tag` / `_load_fixture_output` (fail-closed); additive `demo_fixture: bool` in the audit with a truthful `_llm_call_block`.
- `backend/data/seed_claims.py` — explanatory comment (no schema change).
- `backend/tests/test_demo_fixture.py` (5), `backend/tests/test_anonymisation.py` (10).

Repository total **348 passing, 7 skipped, 0 failing** (326 backend + 22 frontend). `ruff` clean; `mypy backend` clean (106 source files).

---

## Scenario-3 fix mechanism and its determinism

The seeded guardrail claim already carries `scenario_tag='guardrail_escalation'`, so **no migration or new column was needed**. `Adjuster.evaluate` reads the tag (via the connection it already opens), maps it to the fixture file, loads and range-validates the fixture, and returns it **instead of calling the LLM** — short-circuiting the one non-deterministic step. The Guardrail's *real* deterministic regex then catches the planted endorsement (the citation regex requires the name to start with a letter, so the fixture uses "Endorsement Coastal Surge Rider"). The `estimate`/probe path is untouched, so the agent test bench always hits the real model.

**Verified deterministic in test:** `test_guardrail_escalation_reproduces_deterministically` runs the seeded claim end-to-end with the Adjuster's mock provider set to *raise if called*, and asserts `awaiting_human` + `guardrail_failed`, `MockProvider.calls == []` (the LLM was never called), and the audit `demo_fixture: true` / `llm_call.provider == "demo_fixture"`. The determinism comes from the regex, not from model luck — and the audit trail is truthful about the fixture source.

---

## Anonymisation pass result

The parameterised `test_anonymisation.py` greps the **shipping artefacts** — backend + frontend code, README, `CLAUDE.md`, the user-facing `docs/` (architecture, governance, DORA, design-decisions, walkthrough, verification), `infra/`, `scripts/`, `diagrams/` — for a list of candidate regulated/specialty-insurer identifiers. **Result: zero matches.** The build's meta-record (`docs/prompts/`, `docs/build-log.md`) is excluded because it legitimately documents the anonymisation grep methodology itself; `backend/app/prompts/` (the agent prompt deliverables) is scanned. Per the approval note, the architect performs a one-time manual grep of the *real* client name (unknown to this build) before the public push; the candidate-list test is the standing regression guard.

---

## Verification pass result

- **Auto-approve ($85k water damage)** — reproduces live: `settled`, no rules fired.
- **Threshold escalation ($850k fire)** — reproduces live: `awaiting_human`, `settlement_over_ceiling` (any in-range Adjuster value for fire/severe exceeds the $250k ceiling).
- **Guardrail escalation ($1.4M storm)** — now **deterministic** via the fixture; verified end-to-end in test. The architect runs `scripts/verify-demo-scenarios.py --backend=$URL` against the deployed backend and fills `docs/verification/phase-7/scenarios.md`.

---

## Deviations from the plan, with reasons

1. **Scenario-3 trigger keyed on the existing `scenario_tag`, not a new column** (approved D1) — avoids a migration; the tag is already the demo marker.
2. **`estimate`/probe is not fixture-aware** (D1) — the probe has no claim/tag context, so the test bench always exercises the real model. Stated in the plan.
3. **`infra/azure-devops-pipeline.yml` created fresh** — it was an empty `.gitkeep`, not a stub.
4. **README ~230 lines, not 400–600** — every locked section and its key claims are present; the deeper material lives in the linked docs (design-decisions, governance, DORA) rather than being inlined, which reads better and avoids duplication.

---

## Outstanding items requiring architect involvement

1. **Verify the Render redeploy completes and `/health` reports `version=0.7.0`.**
2. **Run `scripts/verify-demo-scenarios.py --backend=$BACKEND_URL`** against the deployed backend; paste the output into `docs/verification/phase-7/scenarios.md`.
3. **Record the 3-minute walkthrough video** using `docs/walkthrough.md` as the script; keep the video outside the repo and add the link to the README's "Live demo" section.
4. **One-time manual grep of the real client name** across the repo before any public/interview link goes out (the test's candidate list is the standing guard).
5. **Final eyes on the expanded README and the new docs**, and set the live demo URL in the README once deployed.

No new dependencies. No new env vars. No CI changes.
