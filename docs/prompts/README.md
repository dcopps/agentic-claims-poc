# Prompts Archive

Every prompt used to build this prototype is archived here in numerical order, paired with the plan that was approved before execution and any plan iterations that were rejected along the way. Re-running the prompts in sequence against an empty directory in a fresh Claude Code session reproduces the entire repository.

## Convention

- One prompt per logical step (typically one per build phase).
- Numbered sequentially with zero-padded prefixes: `01-`, `02-`, etc.
- Descriptive filename, lowercase with hyphens: `01-phase-0-repository-scaffold.md`.
- Each prompt is self-contained — it can be read and executed without external context beyond the repository itself and the global standards at `~/.claude/CLAUDE.md`.
- Prompts are authored by the architect and saved here directly. Claude Code is invoked by referencing the file (for example: *"Read and execute docs/prompts/01-phase-0-repository-scaffold.md"*).
- Each prompt opens by referencing `CLAUDE.md` and the relevant section of `BUILD-PLAN.md` (the build plan is kept locally and is not committed to the public repository).
- Each prompt follows the global plan-first workflow: produce a written plan, wait for confirmation, then execute.
- Each prompt's execution ends by appending an entry to `docs/build-log.md` and updating the "Current Status" section of `CLAUDE.md`. The build-log entry references the prompt file, the approved plan file, and any rejected plan iterations.

## Plan workflow

The plan-first standard is implemented as follows:

1. **Plan saved before approval.** Claude Code writes the plan verbatim to `NN-<phase-name>-plan.md` *before* asking for approval. This lets the architect read it in their editor rather than scrolling through a chat transcript.
2. **Approval recorded in the plan file.** When the architect approves, Claude Code appends an `## Approval` footer with the approval timestamp (ISO 8601 UTC), the approver name, and the verbatim approval message.
3. **Rejected plans preserved.** When the architect rejects (any feedback short of unambiguous approval), Claude Code appends a `## Rejection` footer to the current plan file (timestamp, summary of feedback, pointer to the next iteration), renames it to `NN-<phase-name>-plan-rejected-MM.md` where `MM` is the iteration number, and saves a revised plan as the new canonical `NN-<phase-name>-plan.md`. Iteration repeats until the canonical plan carries an `## Approval` footer.
4. **Execution proceeds against the approved plan only.** Claude Code does not write code until the canonical plan file is approved.

## Index

| # | Prompt | Plan | Phase |
|---|---|---|---|
| 01 | [`01-phase-0-repository-scaffold.md`](01-phase-0-repository-scaffold.md) | `01-phase-0-repository-scaffold-plan.md` (saved before approval; approval/rejection appended) | Phase 0 — Repository scaffold |

(Further prompts are added as the build progresses.)

## What the artefacts capture

- **Prompt** — what was asked. Authored by the architect before the work begins.
- **Plan (approved)** — what was agreed before execution. Authored by Claude Code, approved by the architect, with the approval timestamp and message appended.
- **Plan iterations (rejected)** — any plan versions the architect rejected before final approval. Each carries a `## Rejection` footer with the reason and a pointer to the superseding plan.
- **Build-log entry** — what was actually built. Authored by Claude Code after execution, recording files changed, test counts, plan iteration count, and any issues discovered.

Together these give a complete audit trail per phase: intent, design (with the full revision history), and outcome.

## Reproducibility note

The pre-build setup work — restructuring `CLAUDE.md` to follow the global standards, creating `BUILD-PLAN.md`, creating `docs/build-log.md`, adding the four diagrams under `diagrams/`, copying the stack reference under `docs/`, and seeding this prompts archive — was performed manually before the prompts archive was opened. That work is recorded in the first entry of `docs/build-log.md`. From `01-phase-0-repository-scaffold.md` onward, every change to the repository is driven by a prompt in this folder.
