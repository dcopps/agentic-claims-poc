# Prompt 08 — Phase 7: Demo Polish and Documentation

## Read first

This phase is different in rhythm from Phases 4–6 — less code, more content. The plan-first workflow still applies; the "plan" is essentially a content outline per documentation artefact, and the "execution" is mostly writing.

Before doing anything else, read these files:

- `CLAUDE.md` — global standards, locked architectural decisions, standing instructions.
- `BUILD-PLAN.md` — the phased build plan; this prompt covers Phase 7. The locked README structure (the nine-section ordering) is the spine for §3 below.
- `docs/prompts/07-phase-6-frontend-polish-report.md` — the audit-payload addendum (Adjuster full reasoning, Validator truthful provider/model, `variant` on `pipeline_started`, plus the `human` agent and `aborted` claim status from migration 0002) needs a permanent home in Phase 7.
- `docs/architecture-stack-reference.md` — the full dev-vs-production reference; the README's production-architecture section pulls from here.
- `README.md` — the current state; Phase 7 expands it.
- `infra/azure-devops-pipeline.yml` — the existing placeholder; Phase 7 expands it to a credible production CI/CD reference.
- `backend/data/seed_claims.py` and `backend/app/agents/adjuster.py` — the locked $1.4M storm guardrail-escalation seed and the Adjuster code; the scenario 3 reproducibility fix lands here.
- `frontend/src/copy/tooltips.ts` — the locked tooltip strings naming production equivalents.

The global Claude Code working protocol at `~/.claude/CLAUDE.md` applies throughout. Plan-first workflow, defensive programming, function size limits, settings architecture, no hardcoded values, externalised prompts, system/user separation, interface stability, dependency discipline, security, commit protocol, anonymisation.

## Goal

Execute Phase 7 of `BUILD-PLAN.md` — Demo polish and documentation. By the end of this phase:

- The **README** is expanded to its final, demo-ready form using the locked nine-section structure from `BUILD-PLAN.md`: 30-second elevator pitch; headline sequence diagram inline; "What this demonstrates"; one-command local setup; live demo URL + three pre-loaded scenarios; four diagrams in collapsible sections; "Design decisions and trade-offs" (pre-empting the obvious interview questions); production architecture (Azure topology + dev→prod table); change governance + DORA register links.
- **`docs/change-governance.md`** ships — the standard / normal / emergency change taxonomy applied to AI changes specifically, with one worked example of each (e.g. *standard*: prompt-template tweak via `variants.yaml`; *normal*: new variant adding a fine-tuned model; *emergency*: hotfix a guardrail regex after a live PII miss).
- **`docs/dora-third-party-register.md`** ships — every third-party provider the system depends on (Anthropic, Mistral, Neon, Render, Vercel, sentence-transformers + bge-small) with: role, substitution path, evidence the substitution has been exercised in the prototype, regulatory rationale under DORA Article 28.
- **`infra/azure-devops-pipeline.yml`** is expanded to a credible reference: build → test → security scan → CAB-approval gate → migration runner → staging deploy → smoke test → production deploy → post-deploy verification. Each stage's comment names what the production equivalent does (e.g. *"this stage runs the Bicep What-If; the prototype's GitHub Actions has no equivalent"*).
- The **scenario 3 reproducibility gap is closed**: the seeded $1.4M storm claim now deterministically reproduces the guardrail-escalation path end-to-end live, without relying on the LLM's non-determinism to surface a hallucinated endorsement. Mechanism per question 1 below.
- The **audit-payload addendum lands in a permanent home**: the three additive Phase 5/6 audit changes (Adjuster full reasoning; Validator truthful provider/model; `variant` on `pipeline_started`) plus the Phase 6 migration's `human` agent and `aborted` claim status are documented as locked interfaces in `CLAUDE.md`'s "Architectural Decisions (Locked)" section and surfaced in the README's architecture section.
- A **walkthrough script** at `docs/walkthrough.md` ships — the architect-recordable 3-minute path for the demo video: scenes, screen targets, lines to say. Not the video itself; the script the architect reads while recording.
- The **three demo scenarios all reproduce end-to-end live** via the deployed UI. The verification evidence (screenshots or a short log) is committed under `docs/verification/phase-7/` for the audit trail.
- The **final anonymisation pass** runs across the whole repo and the report enumerates any client-name occurrences found and removed (the expected count is zero, but the report should make the pass visible).

The per-phase preamble fix-up bundled into the same Phase 7 commit:

- Bump `pyproject.toml` version `0.6.0` → `0.7.0`. The `/health` `version` field then reads `0.7.0` after the Phase 7 push, confirming Phase 7 code is live.

## Current state of the project (for orientation)

Phase 6 delivered the polished routed SPA, the audit viewer with whole-ledger chain verification, the human-review panel writing audit entries under `agent='human'`, the agent test bench, and migration 0002 (audit_log `human` agent + claims `aborted` status). 333 tests passing, 7 skipped, 0 failing; `/health` reports `version=0.6.0`.

The three demo scenarios behave correctly in test, but live reproducibility of scenario 3 (guardrail escalation against a hallucinated endorsement) depends on the LLM's non-determinism. Scenarios 1 and 2 reproduce live cleanly. Phase 7 closes the gap.

The repository's documentation is partial: README is mid-form; `docs/architecture-stack-reference.md` is complete and substantive; `docs/change-governance.md`, `docs/dora-third-party-register.md`, and `docs/walkthrough.md` do not exist; `infra/azure-devops-pipeline.yml` is a stub.

## Step 1 — Produce and save the plan

Following the global plan-first standard, produce a written plan covering everything below.

### Cross-cutting questions (fewer than Phases 4–6; this phase is content-heavy)

1. **Scenario 3 reproducibility mechanism — pick one, justify, and lock.** The fix needs to make the seeded `guardrail_escalation` claim reliably trigger the Guardrail under a live run. Three plausible mechanisms; recommend one:

   - **(a) Demo-fixture Adjuster output via seed metadata.** Extend `seed_claims.py` so the `guardrail_escalation` claim carries a `demo_adjuster_fixture` reference (filename pointing into `backend/data/demo_fixtures/`). Add a small `DemoFixtureAdjuster` (or a flag on the existing Adjuster) that, when the claim carries the fixture reference, skips the live LLM call and returns the fixture output instead. The fixture's reasoning embeds a known-bad endorsement so the Guardrail's regex catches it deterministically. Pros: declarative, no agent prompt change, demo path obvious. Cons: a small leak of demo-specific logic into the Adjuster.

   - **(b) Adjuster prompt nudge.** Add an instruction to the Adjuster's system prompt that, when the claim carries a particular marker, surfaces an endorsement reference the policy doesn't carry. Pros: no new code path. Cons: still LLM-mediated, still non-deterministic, defeats the point.

   - **(c) New `demo_guardrail` variant via the Phase 5 variant registry.** Register a `demo_guardrail` variant that overrides the Adjuster to a fixture-mode implementation. The orchestrator, when running a claim with `scenario_tag='guardrail_escalation'`, auto-selects the `demo_guardrail` variant. Pros: reuses the variant mechanism. Cons: more moving parts; auto-selecting a variant by scenario_tag is a new convention.

   **Recommendation: (a).** It's the smallest, most readable change. The fixture lives in `backend/data/demo_fixtures/` and is plain JSON; the Adjuster check is one branch on the input. Document explicitly in the demo path that this is a deterministic demo affordance, not a hidden cheat — the audit trail shows the fixture-source flag in the Adjuster's audit payload (additive field `demo_fixture: bool`).

2. **Audit-payload addendum — where does it permanently live?** The three Phase 5/6 audit extensions are currently only in the Phase 5 and 6 reports. Recommended: add a "Locked interface extensions since Phase 4" subsection in `CLAUDE.md` under "Architectural Decisions (Locked)", enumerating:
   - Adjuster `settlement_estimate` audit `output` block: additive `reasoning` field (full, alongside `reasoning_excerpt`).
   - Validator `coverage_check` audit `llm_call.provider` / `model`: report `self._provider.vendor` and the actual model name (truthful, not hardcoded).
   - `pipeline_started` audit + SSE event: additive `variant` field (default `"default"`).
   - `audit_log.agent` CHECK: extended to include `'human'`.
   - `claims.status` CHECK: extended to include `'aborted'`.
   - Audit step names: `human_approval`, `human_rejection`.

   And include a one-line summary in the README's "Design decisions and trade-offs" section noting the audit log is the trusted record and these extensions preserve that property.

3. **Change-governance taxonomy criteria.** What's the test for standard / normal / emergency for an AI change specifically? Recommended:
   - **Standard:** No model swap, no prompt structural change (placeholders unchanged), no schema migration, no new API surface, no rule-name change. Example: replacing literal copy in `validator_template.md` with clearer phrasing.
   - **Normal:** Anything that changes model output behaviour at a contract level — a new variant, a new agent, a new prompt placeholder, a new escalation rule, a schema additive change. Example: adding a `v3_long_form_validator` variant.
   - **Emergency:** A live incident requires a fix faster than CAB cadence allows — typically a guardrail or escalation policy change to mitigate harm in flight. Example: a regex pattern in the Guardrail's PII rule set fails to catch a specific number format observed in production; emergency hotfix patches `guardrail_rules.py` with post-deployment review.

   Each example should sketch the actual diff being approved, who approves, what tests run, and what post-deployment verification is required.

4. **DORA register format.** Recommended structure: a table per provider with rows for *role* / *substitution path* / *substitution exercised in prototype (Y/N + how)* / *regulatory rationale*. Cover Anthropic (Sonnet, Haiku), Mistral (Large), Neon (Postgres + pgvector), Render (backend host), Vercel (frontend host), and the embedding model (bge-small-en-v1.5). For each, name the production-target replacement explicitly (Azure SQL MI for Neon, Azure Container Apps for Render/Vercel, Azure AI Foundry for Anthropic/Mistral, Azure AI Search for the vector index, Azure-hosted embedding for bge). The "substitution exercised" column is honest about the prototype: the LLM Gateway has been exercised across Anthropic and Mistral; the rest are design-level only.

5. **Walkthrough script structure.** Recommended:
   - **Opening (15s):** "This is a multi-agent insurance claims processing prototype for a regulated specialty insurer. The Pages site you're looking at is live."
   - **Demo path (2m 30s):** Submit → process auto-approve scenario (15s) → process threshold-escalation scenario, watch the SSE-driven agent cards complete (30s) → expand a card to show the prompt + response (15s) → process guardrail-escalation scenario, narrate the deterministic-demo affordance (30s) → audit viewer, click "Verify chain (whole ledger)" (15s) → human review on the escalated claim, approve (30s) → agent test bench (15s).
   - **Closing (15s):** "Architecture diagram, production target, change governance, and DORA register are all in the repo."
   Save at `docs/walkthrough.md`. Includes the URLs to navigate to, the buttons to click, and the lines to read. The architect records the video separately.

6. **Verification evidence — what gets committed?** Recommended: a short markdown log at `docs/verification/phase-7/scenarios.md` with one section per scenario, each containing: the claim submitted (input shape), the resulting PipelineResult (key fields), and either a screenshot of the live UI's final state or the raw output from a `curl` against `/api/runs/{cid}`. Optional but useful: a small Python script `scripts/verify-demo-scenarios.py` that, given a `BACKEND_URL`, submits each scripted scenario and asserts the expected outcome — runnable from the architect's terminal, not in CI. Recommend the script.

### Content specifications per artefact

For each documentation artefact, the plan should specify the outline (section headings), the key claims each section makes, and any internal cross-references. Do not write the prose in the plan — that's execution.

The artefacts and their target lengths (so the plan can calibrate):

| Artefact | Target length | Notes |
|---|---|---|
| `README.md` (expanded) | 400–600 lines | Follows the locked nine-section structure |
| `docs/change-governance.md` | 200–300 lines | Three worked examples; CAB workflow table |
| `docs/dora-third-party-register.md` | 200–300 lines | Per-provider tables + a substitution-exercised summary |
| `infra/azure-devops-pipeline.yml` | 200–350 lines | Stages with rich comments naming production equivalents |
| `docs/walkthrough.md` | 100–150 lines | Scene-by-scene script |
| `docs/verification/phase-7/scenarios.md` | 100–200 lines | Three scenarios, each with input + result + evidence |
| `scripts/verify-demo-scenarios.py` | 150–250 lines | Submits, exercises, asserts; runnable locally |
| `backend/data/demo_fixtures/guardrail_adjuster.json` | ~30 lines | The fixture for scenario 3 |
| `backend/app/agents/adjuster.py` change | additive | One branch + `demo_fixture: bool` in audit |
| `CLAUDE.md` update | additive ~25 lines | Locked-interface extensions subsection |

### Backend changes

Minimal. The scenario 3 fix introduces:

- `backend/data/demo_fixtures/guardrail_adjuster.json` — the fixture (Adjuster output with a known-bad endorsement embedded in `reasoning`).
- `backend/app/agents/adjuster.py` — one branch in `evaluate` / `estimate` (probe) that detects the demo_fixture path on the seeded claim and returns the fixture instead of calling the LLM. The audit payload gains an additive `demo_fixture: bool` field.
- `backend/data/seed_claims.py` — the `guardrail_escalation` claim carries a `demo_adjuster_fixture` reference pointing at the JSON file.
- Tests: a triggering test that the seeded guardrail claim, run end-to-end with mocked Validator + Guardrail providers (real Guardrail regex), produces `awaiting_human` with `guardrail_failed` fired, deterministically, with no live LLM call to the Adjuster.

### Testing strategy

Phase 7 is documentation-heavy; expect ~5–10 new tests covering only:

- The scenario 3 fixture path (the deterministic guardrail trigger).
- An anonymisation test that greps the repo for any pre-known client-name strings and fails if found (a parameterised regex test; harmless if the list is empty in the eventual repo).
- A schema-shape test for the demo fixture JSON (Pydantic-validatable against `AdjusterOutput`).

### CI changes

None expected. The `verify-demo-scenarios.py` script is a local-run, not a CI gate.

### New dependencies — flag each one

**Expected answer: none.** If you find yourself adding one, surface why before writing code.

### Risks and downstream impacts

This is the last code phase before clone-and-run verification. No new locked interfaces — Phase 7 documents existing interfaces and adds the deterministic demo affordance. The `demo_fixture: bool` audit field is additive and follows the established pattern.

The anonymisation pass is non-trivial: it scans every committed file. The plan should specify which patterns are checked (the obvious client name plus common misspellings and adjacent identifiers).

### Deployment steps requiring architect involvement

- Verify `/health` reports `version=0.7.0` after the Render auto-redeploy.
- Run the verification script (`uv run python scripts/verify-demo-scenarios.py --backend=$BACKEND_URL`) against the deployed backend; confirm all three scenarios produce the expected outcomes.
- Record the 3-minute walkthrough video using `docs/walkthrough.md` as the script. Save the file outside the repo (it's a binary and shouldn't be committed); add a placeholder note in the README pointing at where the video lives for the interview.

### Optional enhancements

Carried forward (still deferred): retry via `tenacity`; pricing-table population; real PII redactor; prompt golden fixtures; per-agent timeout; SSE heartbeat; consolidate superseded `EscalationSettings` fields; idempotent re-run helper exposed on UI; `claim_status_history` table; auth on the human decision endpoint; audit pagination; dark mode; prompt-diff in the comparison view.

New for Phase 7 (labelled, not built):

- **A CI smoke test of the deployed Render backend after every push** — currently the architect verifies `/health` manually. A small GitHub Actions job would automate it.
- **`docs/architecture-decisions.md` as a separate ADR log** — currently locked decisions live in `CLAUDE.md`; a dedicated ADR folder with one file per decision is the more standard pattern. Deferred unless the demo benefits.
- **A pre-recorded demo video committed in the repo** — currently the script is committed and the video is recorded separately. Committing the video (under Git LFS) would make the demo self-contained but adds a binary asset.

### Save the plan

Save the plan **before** asking me to review it. Write to:

```
docs/prompts/08-phase-7-demo-polish-and-documentation-plan.md
```

Top-level heading: `# Plan 08 — Phase 7: Demo Polish and Documentation`. Below that, the body of the plan.

After saving the file, point me at it and ask for my verdict. Do not write any other code or documentation yet.

## Step 2 — Approval or rejection

Same workflow as previous phases (per `docs/prompts/README.md`).

**If I approve** (any reply along the lines of "yes", "go ahead", "approved", or similar):

Append a horizontal rule and an `## Approval` section to the plan file. Order the section so the timestamp closes the file:

```
## Approval

**Approval message:** "<my exact approval message, quoted>"

---

**Approved by:** Dermot Copps
**Approved at:** <ISO 8601 timestamp in UTC>
```

Then proceed to Step 3.

**If I reject**, append a `## Rejection` footer, rename the file to `08-phase-7-demo-polish-and-documentation-plan-rejected-NN.md`, produce a revised plan as the fresh canonical file, return to Step 2.

## Step 3 — Execute

After plan approval, execute Phase 7. Constraints from `CLAUDE.md` apply throughout:

- **Defensive programming** on the scenario 3 fixture path (the additive `demo_fixture` check must fail-closed: a referenced fixture file that doesn't exist or doesn't deserialise into a valid `AdjusterOutput` raises clearly, doesn't silently fall through to a live call).
- **Function size:** unchanged limits. The Adjuster branch is small.
- **Settings hierarchy:** no new settings expected. If one creeps in, both `settings.py` and `settings.yaml.template` get the update.
- **Type hints** on every new function signature.
- **Tests:** every new function gets tests; every guard has a triggering test asserting on message content.
- **Anonymisation:** the client name does not appear anywhere — code, comments, tests, fixtures, prompt files, docs, walkthrough script, commit message. The anonymisation pass is a Phase 7 deliverable.
- **Security:** no new credentials. The fixture is plain data, not secret.
- **Externalised prompts:** no new prompt files in Phase 7 (the scenario 3 fix bypasses the LLM for the demo path).
- **Interface stability:** the audit `demo_fixture: bool` field is additive; document on the locked-interfaces list. No other contract changes.

### Preamble fix-up — version bump

Bump `pyproject.toml` version `0.6.0` → `0.7.0`. The `/health` `version` field then reflects Phase 7 once deployed.

## Step 4 — Log

When the work is complete, append a new entry to `docs/build-log.md`. The entry must include:

- Date.
- Phase / Prompt: link to `docs/prompts/08-phase-7-demo-polish-and-documentation.md`.
- Plan (approved): link to `docs/prompts/08-phase-7-demo-polish-and-documentation-plan.md`.
- Plan iterations: count of rejected revisions.
- Report: link to `docs/prompts/08-phase-7-demo-polish-and-documentation-report.md`.
- Prompt summary.
- What changed: every file created or modified, one line each (documentation files included).
- Tests: count and pass rate, with the scenario 3 fixture test broken out.
- Anonymisation pass result.
- Verification pass result (which scenarios reproduced cleanly).
- Issues discovered.
- Next: clone-and-run verification.

## Step 5 — Write the report

Save the report to `docs/prompts/08-phase-7-demo-polish-and-documentation-report.md`. The report opens with a `## Summary` block in the established order:

- **Recap** — one sentence stating what's done plus one sentence stating what comes next.
- **Completed at** — ISO 8601 UTC timestamp.
- **Phase** — `7 — Demo polish and documentation`.
- **Status** — Complete / Complete with deferrals.
- Links to the prompt, the approved plan, and the repository.
- CI status if relevant.

Body sections cover documentation artefacts shipped, the scenario 3 fix, anonymisation pass results, verification pass results, deviations from the plan with reasons, and any outstanding items requiring architect involvement.

## Step 6 — Update CLAUDE.md status

Update the "Current Status" section of `CLAUDE.md` to reflect end of Phase 7:

- Date: today's date in ISO format.
- Phase: "Phase 7 complete; clone-and-run verification next".
- What works: a one-line summary of the end state (e.g. "The full demo is reproducible end-to-end live for all three scripted scenarios. README tells the architectural story without external context. Change governance and DORA third-party register are documented. The audit-payload addendum is on the locked-interfaces list. Clone-and-run verification is the next and final task.").
- What's next: "Clone-and-run verification."

Also add the "Locked interface extensions since Phase 4" subsection per question 2.

## Step 7 — Git

Make a single commit covering all the Phase 7 work, with the commit message:

```
Phase 7: demo polish and documentation

- README expanded to the locked nine-section structure (elevator pitch through DORA)
- docs/change-governance.md: standard / normal / emergency taxonomy for AI changes
- docs/dora-third-party-register.md: provider list + substitution paths + regulatory rationale
- infra/azure-devops-pipeline.yml: credible production CI/CD reference
- docs/walkthrough.md: 3-minute screen-recording script
- docs/verification/phase-7/: scenarios.md + screenshots/log
- scripts/verify-demo-scenarios.py: deployed-backend verification runner
- Scenario 3 reproducibility: backend/data/demo_fixtures/ + Adjuster fixture branch + seed reference
- Audit-payload addendum landed in CLAUDE.md "Locked interface extensions since Phase 4"
- Final anonymisation pass run; results in report
- pyproject.toml version bumped 0.6.0 -> 0.7.0
- Approved plan archived; build log entry appended; report written
- CLAUDE.md Current Status updated
```

Push to `main` so Render auto-deploys.

## Step 8 — Report back

Per the global "After coding" section, report:

- Documentation artefacts shipped (with line counts).
- Code changes and test additions.
- Scenario 3 fix mechanism and the verification that it reproduces deterministically.
- Anonymisation pass result.
- Verification pass result for each of the three live scenarios.
- Any deviations from the plan with reasons.

End the report with the action items I still need to handle:

- Verify the Render redeploy completes and `/health` reports `version=0.7.0`.
- Run `scripts/verify-demo-scenarios.py --backend=$BACKEND_URL` against the deployed backend.
- Record the 3-minute walkthrough video using `docs/walkthrough.md` as the script.
- Final eyes on the expanded README and the new docs before any interview link goes out.

## Save this prompt

Per the "Save every prompt" standing instruction in `CLAUDE.md`, save this prompt verbatim to `docs/prompts/08-phase-7-demo-polish-and-documentation.md` if it isn't already there.
