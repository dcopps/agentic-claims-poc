# Plan 08 — Phase 7: Demo Polish and Documentation

Content-heavy phase: expand the README to its final demo-ready form, ship the
governance/DORA/walkthrough/verification docs and the Azure pipeline reference,
close the scenario-3 live-reproducibility gap with a deterministic demo fixture,
land the audit-payload addendum permanently in `CLAUDE.md`, and run a final
anonymisation pass. One small additive backend change; the rest is writing.

This plan gives the outline (headings + key claims) per artefact — not the prose.
Decisions and the scenario-3 mechanism are settled below; everything else is
execution.

---

## 1. Decisions needing confirmation

### D1 — Scenario 3 mechanism: option (a), keyed off the existing `scenario_tag` (no migration)
**Approved direction: (a) demo-fixture Adjuster output.** Refinement: the trigger
is the **existing** `claims.scenario_tag = 'guardrail_escalation'` column — *not* a
new `demo_adjuster_fixture` column (which would need a migration). The seeded
guardrail claim already carries that tag.

Mechanism:
- New file `backend/data/demo_fixtures/guardrail_adjuster.json` — an `AdjusterOutput`
  whose `reasoning` embeds a known-bad endorsement reference (e.g. *"coverage
  extended under Endorsement 7"*) that the seeded policy does not contain, sized so
  `recommended_settlement` sits inside the storm_complex/severe market range
  (`[600000, 1800000]`) — e.g. `1400000.00`.
- `Adjuster.evaluate` gains one branch: read `scenario_tag` for `claim_id` (via the
  connection it already opens), and a small `_SCENARIO_FIXTURES` map
  (`{"guardrail_escalation": "guardrail_adjuster.json"}`). If matched, load + validate
  the fixture into `AdjusterOutput`, assert it is within the looked-up market range,
  and return it **instead of** calling the LLM. Otherwise the path is unchanged.
- The audit payload gains an additive top-level `demo_fixture: bool`. When true, the
  `llm_call` block records no model call (provider `"demo_fixture"`, latency 0) so the
  audit stays truthful — the trail shows plainly that this Adjuster output came from a
  fixture, not a model. This is the demo affordance made auditable, not hidden.
- **Defensive (fail-closed):** a referenced fixture that is missing, unreadable,
  non-JSON, fails `AdjusterOutput` validation, or falls outside the market range
  raises `ValueError` — it never silently falls through to a live call.
- **`estimate` (probe) is untouched** — it has no claim/`scenario_tag` context, so the
  agent test bench always exercises the real model. (Minor deviation from the prompt's
  "evaluate / estimate"; the fixture is inherently claim-bound.)

The Guardrail then catches the planted endorsement deterministically via its existing
hallucinated-citation regex → `passed=False` → `awaiting_human` with `guardrail_failed`.

### D2 — Audit-payload addendum permanent home: `CLAUDE.md` (per prompt q2)
A new **"Locked interface extensions since Phase 4"** subsection under
`CLAUDE.md` → "Architectural Decisions (Locked)", enumerating the six items from the
prompt (Adjuster full `reasoning`; Validator truthful provider/model; `variant` on
`pipeline_started` audit+SSE; `audit_log.agent` +`human`; `claims.status` +`aborted`;
audit steps `human_approval`/`human_rejection`) **plus** the new `demo_fixture` field.
README §7 gets a one-line note that the audit log is the trusted record and these
extensions preserve it.

### D3 — Anonymisation test: greps a list of candidate names (the real client name is already absent)
The actual client name has been kept out of the repo throughout, so it is unknown to
this build. The anonymisation test is a parameterised regex grep over committed
source/docs for a **list of plausible regulated/specialty-insurer identifiers** (the
candidates earlier phases grepped: `aspen`, `axa`, `chubb`, `swiss re`, `munich re`,
plus a few adjacent specialty names) — failing if any appear. Expected: zero matches.
I'll flag in the report that the list is candidate-based; the architect can add the real
name to the list (it is already absent). The test excludes its own source and
`docs/learning/` (uncommitted).

### D4 — `infra/azure-devops-pipeline.yml` is created fresh (the "stub" is an empty `.gitkeep`)
The prompt calls it a stub; in fact `infra/` holds only `.gitkeep`. I'll create the
file fresh per the §2 outline. No deviation of substance.

### D5 — Design decisions: README §7 + a fuller `docs/design-decisions.md`
The prompt folds design decisions into README §7; `CLAUDE.md`'s target structure and
`BUILD-PLAN` also list a standalone `docs/design-decisions.md`. I'll write the fuller
treatment in `docs/design-decisions.md` and have README §7 summarise the top ~6
trade-offs and link to it. Satisfies both.

**Net new dependencies: none.**

---

## 2. Documentation artefacts — outlines

### 2.1 `README.md` (expanded, ~400–600 lines) — locked nine/ten-section order
1. **30-second elevator pitch** — multi-agent claims processing for a regulated
   specialty insurer; RAG coverage, settlement, guardrails, tamper-evident audit,
   human-in-the-loop; live URL.
2. **Headline sequence diagram inline** — embed `diagrams/1-headline-agent-flow.mmd`
   (mermaid fenced block) with the mermaid.live link.
3. **"What this demonstrates"** — bullets: tiered models, RAG-with-citations,
   hash-chained audit, decoupled submit→event→pipeline, replay, escalation policy,
   LLM-Gateway provider substitutability, human-in-the-loop, agent test bench.
4. **One-command local setup** — condense the existing setup into the fast path
   (`setup-dev-db.sh` → migrate → seed → index → `uv run uvicorn` / `npm run dev`),
   keeping the detailed prerequisites.
5. **Live demo URL + three pre-loaded scenarios** — the deployed Vercel URL, the three
   scripted scenarios (auto-approve $85k, threshold $850k, guardrail $1.4M), and the
   "Load demo claim" buttons. Note scenario 3 is deterministic via the demo fixture.
6. **Four diagrams in collapsible `<details>` sections** — headline, RAG zoom,
   decoupling, production topology (the four `.mmd` files), each with its mermaid.live
   link (matching the existing diagram-embedding pattern).
7. **Design decisions and trade-offs** — ~6 pre-empted interview questions
   (why hash-chain not Ledger Tables in the prototype; why an LLM Gateway; why
   Mistral + Claude; why fixture for scenario 3; why in-process event bus; audit-as-
   trusted-record). Summary + link to `docs/design-decisions.md`.
8. **Production architecture** — the Azure topology (embed
   `4-production-architecture.mmd`) + the dev→prod table pulled from
   `architecture-stack-reference.md`'s "Stack at a glance" + "Key dev → prod
   transitions".
9. **Reproducible build** — link `docs/prompts/` + `docs/build-log.md` (largely
   existing copy).
10. **Change governance + DORA register** — links to the two new docs; one-line each.
Plus: a "Demo video" placeholder note (the video lives outside the repo).

### 2.2 `docs/change-governance.md` (~200–300 lines)
- **Intro** — why AI changes need a change taxonomy; CAB cadence.
- **The taxonomy** — Standard / Normal / Emergency, with the criteria from prompt q3
  (model swap? prompt-structural? migration? new API/rule? → classification).
- **CAB workflow table** — for each class: who approves, what tests run, deploy gate,
  post-deploy verification.
- **Three worked examples**, each sketching the actual diff, approver, tests,
  post-deploy check:
  - *Standard*: reword `validator_template.md` (placeholders unchanged).
  - *Normal*: add a `v3_long_form_validator` variant to `variants.yaml`.
  - *Emergency*: hotfix a `guardrail_rules.py` PII regex after a live miss.
- **Cross-refs** — `variants.yaml`, `policy.yaml`, the DORA register.

### 2.3 `docs/dora-third-party-register.md` (~200–300 lines)
- **Intro** — DORA Article 28 ICT third-party risk; why substitutability matters.
- **Per-provider tables** (role / substitution path / substitution exercised in
  prototype (Y/N + how) / regulatory rationale) for: Anthropic (Sonnet, Haiku),
  Mistral (Large), Neon (Postgres+pgvector), Render, Vercel, embedding model
  (bge-small-en-v1.5). Each names the Azure production replacement (Azure AI Foundry,
  Azure SQL MI, Azure Container Apps, Azure AI Search, Azure-hosted embedding).
- **Substitution-exercised summary** — honest: the LLM Gateway has been exercised
  across Anthropic↔Mistral (the `v2_haiku_validator` variant + truthful provider audit
  prove it); the rest are design-level.

### 2.4 `infra/azure-devops-pipeline.yml` (~200–350 lines)
A credible reference pipeline: stages **build → test → security scan → CAB-approval
gate → migration runner → staging deploy → smoke test → production deploy → post-deploy
verification**. Each stage carries a rich comment naming the production equivalent and,
where relevant, what the prototype's GitHub Actions does/doesn't do (e.g. Bicep
What-If, `sys.sp_verify_database_ledger`, CCB work-item linkage). YAML is illustrative
(not run); a header comment states this.

### 2.5 `docs/walkthrough.md` (~100–150 lines)
Scene-by-scene 3-minute script per prompt q5: Opening (15s) → demo path (2m30s:
submit → auto-approve → threshold w/ live SSE cards → expand a card → guardrail
(narrate the deterministic fixture) → audit viewer + Verify chain (whole ledger) →
human review approve → agent test bench) → closing (15s). Each scene: URL to navigate,
buttons to click, lines to read.

### 2.6 `docs/verification/phase-7/scenarios.md` (~100–200 lines)
One section per scenario: input shape submitted, resulting `PipelineResult` key fields,
and evidence (a `curl /api/runs/{cid}` excerpt placeholder the architect fills from the
live run). Includes how to regenerate via the script.

### 2.7 `scripts/verify-demo-scenarios.py` (~150–250 lines)
Given `--backend=$URL`, for each scripted scenario: submit a claim (or use the seeded
one), trigger the run, poll the runs API, assert the expected outcome (auto-approve →
`settled`; threshold → `awaiting_human` + `settlement_over_ceiling`; guardrail →
`awaiting_human` + `guardrail_failed`). Defensive (timeouts, clear failure messages);
local-run only, not CI. Uses stdlib `urllib` + the project venv (no new dep).

### 2.8 `docs/design-decisions.md` (~150 lines)
The fuller trade-off treatment README §7 links to.

---

## 3. Backend change (scenario 3 fix) — files + tests

- **created** `backend/data/demo_fixtures/guardrail_adjuster.json` (~30 lines) — the
  `AdjusterOutput` fixture (planted endorsement; in-range settlement).
- **modified** `backend/app/agents/adjuster.py` — the one fixture branch in `evaluate`
  (read `scenario_tag` → fixture map → load/validate/return), additive `demo_fixture`
  in the audit payload, fail-closed guards. A module constant `_DEMO_FIXTURES_DIR` and
  `_SCENARIO_FIXTURES` map (no new setting; no magic strings).
- **modified** `backend/data/seed_claims.py` — no schema change; a comment noting the
  `guardrail_escalation` tag drives the demo fixture (the tag already exists).
- **Tests** (`backend/tests/`):
  - `test_demo_fixture.py`: the fixture JSON deserialises into a valid `AdjusterOutput`
    (schema-shape test); the seeded guardrail claim run end-to-end (real Guardrail
    regex, mocked Validator provider, **no Adjuster LLM call**) → `awaiting_human` +
    `guardrail_failed`, deterministically; the audit shows `demo_fixture: true`.
    Guard tests: missing fixture file → ValueError; out-of-range fixture → ValueError.
  - `test_anonymisation.py`: parameterised grep over committed files for the candidate
    name list → asserts zero matches (D3).

Expected ~6–8 new tests.

---

## 4. `CLAUDE.md` updates
- New "Locked interface extensions since Phase 4" subsection (D2) — ~25 lines.
- Current Status → "Phase 7 complete; clone-and-run verification next" (Step 6).

---

## 5. Testing / CI / deps
- ~6–8 new tests (§3). No CI changes. **No new dependencies.**

---

## 6. Risks / locked interfaces
- Only one additive interface change: the Adjuster audit `demo_fixture: bool` field
  (additive, on the locked-extensions list). No other contract changes.
- The anonymisation test is candidate-based (D3) — flagged.
- The verification script and walkthrough are architect-run/record; not CI.

---

## 7. Optional enhancements (labelled; not built)
Carried forward (unchanged list) + new for Phase 7: a CI smoke test of the deployed
backend after each push; a standalone ADR log (`docs/architecture-decisions.md`); a
committed demo video under Git LFS.

---

## 8. Execution order
1. `pyproject.toml` 0.6.0→0.7.0.
2. Scenario-3 fix: fixture JSON + Adjuster branch + seed comment + tests (green).
3. Anonymisation test + run the pass.
4. `CLAUDE.md` locked-extensions subsection.
5. Docs: README, change-governance, dora-register, design-decisions, walkthrough,
   verification/scenarios, azure pipeline, verify script.
6. Backend full green (ruff/mypy/pytest); frontend unaffected (quick check).
7. Build-log, report, `CLAUDE.md` Current Status, single commit, push.

---

**Verdict requested.** Please review — especially **D1** (scenario-3 fixture keyed off
the existing `scenario_tag`, no migration; `estimate`/probe untouched; truthful
`demo_fixture` audit), **D3** (the anonymisation test is candidate-based since the real
client name is already absent — confirm the candidate list approach), and **D5**
(design decisions in README §7 + a standalone `docs/design-decisions.md`). On approval
I'll record the `## Approval` footer and proceed to Step 3.

---

## Approval

**Approval message:** "Approved as written. One thing I'll handle myself outside Claude Code's reach: a final manual grep of the real client name across the repo before the commit pushes — the candidate list is the regression guard; the manual check is the one-time verification. Then append the ## Approval footer and proceed to Step 3."

**Approval note:** The architect performs a one-time manual grep of the actual client name across the repo before the push (outside Claude Code's reach). The Phase 7 `test_anonymisation.py` candidate-list grep is the standing regression guard (D3); the manual check is the one-time verification that the real name — unknown to this build — is absent. All decisions (D1–D5) approved as written.

---

**Approved by:** Dermot Copps
**Approved at:** 2026-06-15T10:30:53Z
