# Phase 9.2.2 — The Guardrail's LLM citation flag must quote its evidence, and code verifies it

## Why this phase exists

Phase 9.2.1 narrowed the question the Guardrail's LLM check is asked. It did not make the answer reliable. Three runs on three surfaces, each at temperature 0 and each reproducible 3/3, flagged three different pieces of the Adjuster's own vocabulary as hallucinated policy citations: *"market range"* (26 October), *"supply line"* (29 October, Render via the script), *"$200,000 ceiling"* (30 October, Vercel frontend). Twice the model conceded in its own `detail` that the phrase was settlement methodology and flagged it anyway. The $85k auto-approve scenario is therefore unreliable on every surface, and the line between "a policy citation" and "the Adjuster's own words" is being redrawn by the model on each run.

This phase takes that decision away from the model. The LLM check keeps its job of spotting a suspicious reference; it loses the authority to fail a claim on its own say-so. A `hallucinated_citation` flag counts only when it quotes the exact words it objects to, those words are present in the Adjuster's reasoning, and the words have the shape of a named provision by the same test the deterministic rule engine already uses. *"market range"* fails that test by construction; *"Endorsement Coastal Surge Rider"* passes it.

The full specification, acceptance criteria and the trade-off were written into `docs/BACKLOG.md` → *Phase 9.2.2* on 29 October and amended on 30 October. Read that section, the Phase 9.2.1 report and its build-log entry (including the 30 October addendum) before planning. Version `0.9.1.1 → 0.9.1.2`.

## What must and must not change

**Must:**
- The LLM `hallucinated_citation` flag gains a `quote` field: the verbatim words from the reasoning the model says name a provision. The *Output format* section of `backend/app/prompts/system/guardrail.md` changes accordingly; the golden-shape test moves with it.
- After `_parse_llm_flags`, code discards any `hallucinated_citation` flag that has no quote, whose quote is not a substring of `adjuster_reasoning` (plan to state the normalisation: case, whitespace, straight/curly quotes), or whose quote does not match the rule engine's provision-name test (`_CITATION_CANDIDATE_RE`, Phase 8.6.1, reused as the oracle, not copied). Discarded flags are **recorded, not counted**.
- The `output_check` audit payload records discarded LLM flags with the reason: `no_quote`, `quote_not_in_reasoning`, `quote_not_a_provision`. Additive; existing keys unchanged. **This is an interface-stability event** and must be acknowledged in the plan, with the exact new key and shape, and added to the *Locked interface extensions* list in `CLAUDE.md` on completion.
- `pii` and `bias` flags are unchanged by this phase: no quote required, no discard path. State this in the plan.
- The Coral Bay scenario still fails the Guardrail through the LLM path alone (rule-engine findings blanked), because its invented endorsement passes the quote test.

**Must not:**
- Change `_CITATION_CANDIDATE_RE`, the rule engine, or the `guardrail_failed` hard rule. If the regex is too narrow for a real citation, that is a separate, flagged change.
- Change the system prompt's definition of a citation, the user template, the SSE events, or any HTTP response shape.
- Make a discarded flag silent. Every discard is in the audit payload and in the structured log at INFO with the reason and the quote (truncated to 200 characters).

## Plan-first

Produce `docs/prompts/22-phase-9.2.2-guardrail-quote-verified-citation-flags-plan.md` covering:

1. **The prompt change.** The new *Output format* JSON with `quote` on `hallucinated_citation` flags (required for that kind; absent or null for `pii` and `bias`), one sentence in the rules telling the model the quote must be copied verbatim from the reasoning, and nothing else changed. Show the diff in the plan.
2. **The verification code.** Where it lives (expected: a small function in the Guardrail agent module or a sibling, under the 30-line prompt and the 50-line limit), the three checks in sanitise → validate → abort → execute order, the normalisation applied before the substring test, and how the rule engine's candidate test is invoked without duplicating it. Pydantic model change for the flag (`quote: str | None`), and what happens when the model returns a `quote` on a `pii` flag (ignored, not an error).
3. **The audit extension.** The exact additive key and shape under `output_check` (suggest `llm_flags_discarded: [{kind, detail, quote, reason}]`), present as an empty list when nothing was discarded so the shape is stable, and the interface-stability acknowledgement.
4. **Tests.** Unit tests for each discard reason asserting the reason string and the audit shape; a test that a well-formed quote passes through; a test that `pii` / `bias` are untouched; the golden-shape test updated; mutation proof for the discard path (revert the check, show the test fails). The live replay corpus (seven fixtures) is the acceptance test: every `expected: pass` case passes 3/3, Coral Bay flags 3/3 without the rule engine. Record all outcomes before and after in the report; a 2-of-3 anywhere is reported as such.
5. **Expected replay behaviour, stated in advance.** For each of the three known failing phrases, say which discard reason should catch it. If a phrase would survive (for instance one that happens to match the provision regex), say so before running, not after.
6. **Governance.** *Normal*, same record shape as 9.2.1; one line added to the change-governance *Observed in the prototype* paragraph and to the Anthropic row of the DORA register, as the completion of the control response that 9.2.1 began.
7. **Deployed verification, with Dermot present for the Azure part.** Push deploys both stacks. Then: the three scenarios through the Azure frontend (`azure-start.sh` first; check Postgres, which auto-restarts about 5 November), through the Vercel frontend, and via `scripts/verify-demo-scenarios.py` against Render. Expected everywhere: `settled` / `awaiting_human` (`settlement_over_ceiling`) / `awaiting_human` (`guardrail_failed`, `settlement_over_ceiling`), seven entries each, chain `ok`. For Harborline, the `output_check` payload is expected to show the model's flag in `llm_flags_discarded` with its reason, which is the demo talking point: the model's claim and the code's refusal side by side. Halt and diagnose if any surface disagrees. `azure-stop.sh` last.
8. **Docs.** Build log entry; report; `README.md` known-issue note removed and the *Before a demo* line updated (the replay corpus should now be all green, and stays as the pre-demo check); `docs/BACKLOG.md` items closed; `CLAUDE.md` Current Status, *Demo status* back to usable without caveat, *Escalation policy* note updated, the new *Locked interface extension* entry, *What's next* pointing at the documentation phase (prompt 23) and then Foundry (prompt 24).
9. **Version, dependencies, interface stability.** `0.9.1.2`. No new dependency expected. One additive audit extension, acknowledged as above.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`: plan-first, externalised prompts, system/user separation, function-size limits, mutation-proof tests, no secrets or client name anywhere.
- Deployed databases are read-only for this phase except through the application itself running the scenarios.
- Nothing on Render, Vercel or Neon changes other than by the normal deploy.
- The replay corpus is not edited to fit the result. If a fixture's expectation is wrong, say why in the report and leave the change for Dermot's decision.

## Archive

Pre-saved at `docs/prompts/22-phase-9.2.2-guardrail-quote-verified-citation-flags.md`; plan and report alongside with `-plan.md` / `-report.md`. Prompt 23 is the plain-language documentation phase (decision register, build story index, start-here signposts); Azure AI Foundry becomes prompt 24.
