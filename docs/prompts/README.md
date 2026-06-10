# Prompts Archive

Every prompt used to build this prototype is archived here in numerical order, paired with the plan that was approved before execution and the report that was produced after execution. Together with the build log, this gives a complete audit trail per phase: intent, design, outcome.

## Convention

- One prompt per logical step (typically one per build phase).
- Numbered sequentially with zero-padded prefixes: `01-`, `02-`, etc.
- Descriptive filename, lowercase with hyphens: `01-phase-0-repository-scaffold.md`.
- Each prompt is self-contained — it can be read and executed without external context beyond the repository itself and the global standards at `~/.claude/CLAUDE.md`.
- Prompts are authored by the architect and saved here directly. Claude Code is invoked by referencing the file (for example: *"Read and execute docs/prompts/01-phase-0-repository-scaffold.md"*).
- Each prompt opens by referencing `CLAUDE.md` and the relevant section of `BUILD-PLAN.md` (the build plan is kept locally and is not committed to the public repository).
- Each prompt follows the global plan-first workflow: produce a written plan, wait for confirmation, then execute.
- Each prompt's execution ends by appending an entry to `docs/build-log.md`, saving a report file alongside the plan, and updating the "Current Status" section of `CLAUDE.md`. The build-log entry references the prompt, the plan, the report, and any rejected plan iterations.

## The four artefacts per phase

| Artefact | When | Authored by | Captures |
|---|---|---|---|
| **Prompt** — `NN-phase-N-name.md` | Before execution | Architect | What was asked. |
| **Plan** — `NN-phase-N-name-plan.md` | Before execution, after planning | Claude Code, approved by architect | What was agreed. Approval footer at the bottom of the file with verbatim approval message and ISO 8601 UTC timestamp. Decisions made during planning live here in "Approach and key design decisions". |
| **Report** — `NN-phase-N-name-report.md` | After execution | Claude Code | What was actually built. One-line `Recap`, `Completed at` ISO 8601 UTC timestamp, files created/modified, test counts, deviations from the plan with reasons, guard clauses added, optional enhancements recommended, outstanding items. |
| **Build-log entry** — appended to `docs/build-log.md` | After execution | Claude Code | One-paragraph chronological summary linking to the other three artefacts. |

There is no separate "decisions" file. Decisions naturally split across three locations:

- **Pre-execution design decisions** — in the plan body's "Approach and key design decisions" section.
- **Decisions made at the approval gate** — in the plan's `## Approval` footer (overrides, amendments to the plan, the verbatim approval message).
- **In-flight deviations forced by reality during execution** — in the report's "Deviations from spec" section.

Tracing the lineage end-to-end: open the plan to see what was originally proposed → scroll to the Approval section to see what was actually approved → open the report to see what was actually executed.

## Plan workflow

The plan-first standard is implemented as follows:

1. **Plan saved before approval.** Claude Code writes the plan verbatim to `NN-phase-N-name-plan.md` *before* asking for approval. This lets the architect read it in their editor rather than scrolling through a chat transcript.
2. **Approval recorded in the plan file.** When the architect approves, Claude Code appends an `## Approval` footer to the plan file. The footer's order ends with the timestamp so it sits at the very bottom of the file:

   ```
   ## Approval

   **Approval message:** "..."

   ---

   **Approved by:** Dermot Copps
   **Approved at:** <ISO 8601 UTC>
   ```

3. **Rejected plans preserved.** When the architect rejects (any feedback short of unambiguous approval), Claude Code appends a `## Rejection` footer to the current plan file (timestamp, summary of feedback, pointer to the next iteration), renames it to `NN-phase-N-name-plan-rejected-MM.md` where `MM` is the iteration number, and saves a revised plan as the new canonical `NN-phase-N-name-plan.md`. Iteration repeats until the canonical plan carries an `## Approval` footer.
4. **Execution proceeds against the approved plan only.** Claude Code does not write code until the canonical plan file is approved.

## Report workflow

After Phase execution completes:

1. Claude Code writes the report verbatim to `NN-phase-N-name-report.md`.
2. The report opens with a `## Summary` block containing, in this order:
   - **Recap** — one sentence stating what's done plus one sentence stating what comes next. The kind of single-paragraph elevator pitch a reader can scan in five seconds. (Example: *"Phase 0 of the agentic-claims-poc build is complete and pushed to dcopps/agentic-claims-poc with CI green. Next: provision the Render Web Service via the committed `render.yaml` blueprint and the Vercel project so deployments go live."*)
   - **Completed at** — ISO 8601 UTC timestamp at the moment of report-writing (e.g. `2026-05-09T14:32:18Z`). This is the precise time the phase concluded.
   - **Phase** — the phase number and title.
   - **Status** — Complete / Complete with deferrals / etc.
   - Links to the prompt, the approved plan, and the repository.
   - CI status if relevant.
3. Body sections cover files created and modified by tier, test counts and pass rates, deviations from the plan with reasons, guard clauses added, optional enhancements recommended for future phases, and any outstanding items requiring architect involvement.
4. The build-log entry references the report file alongside the plan and prompt.

**Why the recap line.** It's the highest-leverage element in the file — anyone scanning the report (an interview reviewer, a future Claude session, a stakeholder updating themselves) gets the "what got done, what's next" in one line without reading further. Carries the same role for the report that the build-log entry's `Prompt summary` line carries for the chronological log.

**Timestamp format.** Both the plan's `## Approval` footer and the report's `Completed at` field use ISO 8601 UTC (e.g. `2026-05-08T11:50:06Z`). This pairs cleanly with the build-log entry's ISO date heading and gives the audit trail consistent timestamps end-to-end.

## Index

| # | Prompt | Plan | Report | Phase |
|---|---|---|---|---|
| 01 | [`01-phase-0-repository-scaffold.md`](01-phase-0-repository-scaffold.md) | [`01-phase-0-repository-scaffold-plan.md`](01-phase-0-repository-scaffold-plan.md) | [`01-phase-0-repository-scaffold-report.md`](01-phase-0-repository-scaffold-report.md) | Phase 0 — Repository scaffold |
| 02 | [`02-phase-1-data-layer.md`](02-phase-1-data-layer.md) | [`02-phase-1-data-layer-plan.md`](02-phase-1-data-layer-plan.md) | [`02-phase-1-data-layer-report.md`](02-phase-1-data-layer-report.md) | Phase 1 — Data layer and settings infrastructure |
| 03 | [`03-phase-2-llm-gateway-and-validator.md`](03-phase-2-llm-gateway-and-validator.md) | [`03-phase-2-llm-gateway-and-validator-plan.md`](03-phase-2-llm-gateway-and-validator-plan.md) | [`03-phase-2-llm-gateway-and-validator-report.md`](03-phase-2-llm-gateway-and-validator-report.md) | Phase 2 — LLM Gateway and Validator agent |
| 04 | [`04-phase-3-remaining-agents.md`](04-phase-3-remaining-agents.md) | [`04-phase-3-remaining-agents-plan.md`](04-phase-3-remaining-agents-plan.md) | [`04-phase-3-remaining-agents-report.md`](04-phase-3-remaining-agents-report.md) | Phase 3 — Remaining agents (Doc-Parser, Adjuster, Guardrail) |

(Further prompts are added as the build progresses.)

## Reproducibility note

The pre-build setup work — restructuring `CLAUDE.md` to follow the global standards, creating `BUILD-PLAN.md`, creating `docs/build-log.md`, adding the four diagrams under `diagrams/`, copying the stack reference under `docs/`, and seeding this prompts archive — was performed manually before the prompts archive was opened. That work is recorded in the first entry of `docs/build-log.md`. From `01-phase-0-repository-scaffold.md` onward, every change to the repository is driven by a prompt in this folder and recorded by the matching plan, report, and build-log entry.
