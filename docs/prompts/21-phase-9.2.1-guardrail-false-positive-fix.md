# Phase 9.2.1 — Guardrail false positives on the auto-approve scenario: prompt tightening, replay regression fixture, Adjuster temperature

## Why this phase exists

The $85k Harborline auto-approve scenario no longer settles. In Phase 9.2's second verification pass (26 October 2026) both Harborline runs ended `awaiting_human` on `guardrail_failed`, raised by the Guardrail's LLM check alone; the rule engine found nothing. The investigation is recorded in the *Recorded exception* of the Phase 9.2 entry in `docs/build-log.md` and in `docs/BACKLOG.md` → *Findings from the 26 October 2026 verification*. Read both before planning. The short version:

- The LLM check flagged the Adjuster's settlement vocabulary (*"moderate-severity band"*, *"market range"*) and a paraphrase of the covered peril (*"sudden failure"*, judged against the exclusion for *"rupture or bursting caused by centrifugal force"*) as hallucinated policy citations.
- Replaying the recorded Guardrail prompts to `claude-haiku-4-5-20251001` at temperature 0 reproduced the flag 5/5 for the 26 October prompt and **3/3 for pass one's 1 October prompt (`08d514f2`), which passed on 1 October**. The verdict on byte-identical input changed under an unchanged model id. Nothing on our side changed.
- The system prompt `backend/app/prompts/system/guardrail.md` **already contains** a note that market-data vocabulary is not a policy citation. The stricter model ignores it. Restating the same instruction more loudly is not the fix.

This is demo-visible on both deployments (same model id, same prompts on Render and Azure) and must be resolved before the next demo. It is a small phase: `0.9.1 → 0.9.1.1`, following the 8.6.1 pattern.

## What the fix must and must not do

**Must:**
- Make the Guardrail's LLM check judge **only** whether the reasoning names a specific policy provision (a section, endorsement, sub-limit, clause or exclusion, identified by name or number) that is absent from the retrieved chunks. Two things it must explicitly stop doing: (a) treating settlement-method language, severity bands, market ranges, lookup-table references and contractor or claimant findings as citations; (b) **re-adjudicating coverage** — deciding whether the peril described is covered or excluded is the Validator's job, already done upstream, and the Guardrail second-guessing it is how *"sudden failure"* became a flag.
- Keep the guardrail scenario (Coral Bay, `b35b146b`: an invented endorsement) failing. The fix is a narrowing of what counts as a citation, not a loosening of the check.
- Be proven against the live model, not asserted: the recorded prompts from the audit log are the test data.

**Must not:**
- Touch the hallucinated-citation **rule engine** (`_CITATION_CANDIDATE_RE` and friends, Phase 8.6.1) or the `guardrail_failed` hard rule in `policy.yaml`. The Coral Bay scenario depends on both.
- Add a demo fixture for Harborline. The auto-approve scenario is the one that must be real.
- Change the audit payload shape, the SSE events or any HTTP response. None of this is an interface change; if the plan finds otherwise, that is an interface-stability event to flag.

## Plan-first

Produce `docs/prompts/21-phase-9.2.1-guardrail-false-positive-fix-plan.md` covering:

1. **Diagnosis of the prompt.** Read `backend/app/prompts/system/guardrail.md` and `user/guardrail_template.md` and the four recorded prompts (below) and state *why* the current instruction fails on the stricter model: which sentence invites coverage re-adjudication ("Any policy reference in the reasoning that does not appear in the chunks ... is a hallucination, regardless of how plausible it sounds" reads as licence to judge the substance), and why the market-data note is not being honoured (an aside in step 2, after the broad rule, rather than part of the definition of a citation).
2. **The prompt change.** Proposed new text for the relevant sections, in full, in the plan. Expected shape: a precise definition of what a *citation* is (a named or numbered provision), an explicit list of what is *not* a citation (peril descriptions and paraphrases, settlement-method vocabulary, severity or market bands, third-party findings, the recommended amount), an explicit statement that coverage has been determined upstream and is not to be re-judged, and a two-step procedure: first list every candidate citation found in the reasoning (name or number), then flag only those absent from the chunks. The output JSON is unchanged. System/user separation unchanged: the definition lives in the system prompt; the template carries only the dynamic content.
3. **Replay regression fixture.** A test module (suggest `backend/tests/test_guardrail_replay.py`) gated by `RUN_LLM_E2E_TESTS=1` like the other real-LLM tests, never run in CI, that replays recorded Guardrail inputs through the **current** prompt against the live model and asserts the verdict. Fixture data: the `adjuster_settlement`, `adjuster_reasoning`, `retrieved_chunks` and `rule_flags_already_found` values recovered from the audit `llm_call.prompt.user` of four runs on the Azure database (read-only), stored as JSON under `backend/tests/fixtures/guardrail_replay/`: `8590b47e` and `f02fb888` (Harborline, must pass), `08d514f2` (Harborline pass one, must pass), `b35b146b` (Coral Bay, **must still flag** `hallucinated_citation`). The fixture replays the *inputs* through the current template, not the recorded full prompt, so the test exercises the new system prompt. The plan states how the data is extracted (hostname-only echo, read-only session, as in 9.2) and confirms the fixtures contain no PII and no client name. Also state the run cost per execution (a dozen Haiku calls, cents).
4. **Mutation proof.** Before the prompt change, the three must-pass fixtures must *fail* under the old prompt (reproducing the finding); after it, they pass and Coral Bay still flags. Record all eight outcomes in the report. If the three must-pass cases do not fail under the old prompt on the day, say so — the model may have moved again — and record what was observed rather than forcing the narrative.
5. **Adjuster temperature.** `llm.adjuster_temperature` is `0.2`. The plan proposes how the scripted scenarios get temperature 0 and recommends one option with reasons: (a) set it to `0.0` on the deployed environments only, through the existing settings hierarchy (`LLM__ADJUSTER_TEMPERATURE=0` on Render and in the Container App's env via Bicep) with no code change and the default untouched; (b) a per-scenario override keyed on the demo claims; (c) a new variant. Note that (c) does not help the default *Process* button the demo uses, and (b) adds a code path for three claims. State the trade-off in the comment on `adjuster_temperature` in `settings.py` if the default changes; if it does not, state where the deployed value is set so the next session can find it.
6. **Change governance.** Under `docs/change-governance.md` this is at least a *Normal* change (output behaviour at a contract level). The plan says which class it is and what the record looks like. The DORA register entry from 9.2 (pinned model changed behaviour) gets a one-line follow-up pointing at this phase as the control response.
7. **Verification on the deployed stacks.** After the push deploys the backend (first real backend change through the corrected *Verify the rollout* step after `2b662da`), run the three scripted scenarios on Azure through the UI with Dermot present, and the same three on Render via `scripts/verify-demo-scenarios.py --backend <render-url>`. Expected: `settled` / `awaiting_human` (`settlement_over_ceiling`) / `awaiting_human` (`guardrail_failed`, `settlement_over_ceiling`), seven entries each, chain `ok`. Azure first: `scripts/azure-start.sh`, check Postgres state (it restarts itself on about 2 November). `azure-stop.sh` last. Halt and diagnose if Harborline still escalates.
8. **Docs.** `docs/build-log.md` entry (diagnosis, the before/after prompt diff summary, the eight replay outcomes, deployed verification), `docs/BACKLOG.md` (close the two 26 October items; add the fixture to the pre-demo checklist if one exists, or create that line in `README.md`'s demo section), `README.md` (remove the known-issue note once verified), `CLAUDE.md` (Current Status; *Demo status* back to usable; a one-line note under *Architectural Decisions → Escalation policy* or *Models* that the Guardrail judges citations only, not coverage), `docs/prompts/21-…-plan.md` / `-report.md`.
9. **Version, dependencies, interface stability.** `0.9.1.1`. No new dependency expected. No interface change expected.

Wait for explicit confirmation before changing any prompt or writing any code.

## Constraints

- Standing conventions per `CLAUDE.md`: plan-first, externalised prompts only (no inline prompt text in Python), system/user separation, 50-line function limit, mutation-proof tests, no secret or client name in fixtures or logs.
- The Azure Postgres is a deployed database: read-only session for fixture extraction, hostname-only echoes.
- Nothing on Render, Vercel or Neon is changed except by the normal deploy of the new backend version to Render, and the temperature setting if option (a) is chosen.
- Renumbering: Azure AI Foundry (formerly prompt 21) becomes prompt 22; update the reference in `docs/BACKLOG.md` and `CLAUDE.md` *What's next*.

## Archive

Pre-saved at `docs/prompts/21-phase-9.2.1-guardrail-false-positive-fix.md`; plan and report alongside with `-plan.md` / `-report.md`.
