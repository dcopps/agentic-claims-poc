> *Plain-language summary of this phase: see [the build story](README.md#entry-23), entry 23.*

# Prompt 23 — Report: plain-language documentation

**Status: complete, 31 October 2026.** Documentation only; no code, prompt, test, infrastructure or workflow change; no version bump; no deployment; no Azure session. Plan approved 30 October 2026 (D1–D6 as recommended). Build-log entry *Prompt 23 — Plain-language documentation*.

## What was built

- **`docs/decision-register.md`** (new) — *Decisions and incidents, in plain language.* Purpose, twelve-term glossary, reading guide, nineteen entries R-01 to R-19 from Phase 8.4 onward. The prompt's fourteen plus four additions flagged in the plan and approved: R-08 (the 21 September findings ruled findings, not halts), R-10 (Azure parking), R-13 (how a push may deploy), R-19 (the 9.2.2 trade-off, split out as a standing limitation).
- **`docs/prompts/README.md`** (restructured) — *The build, phase by phase, in plain language.* Purpose, the same glossary, an at-a-glance table of all 23 TL;DRs, 23 entries each with TL;DR, Technologies, body and *Technical detail* line, then the engineer sections retitled *For engineers: how the archive is organised* with the "no separate decisions file" paragraph corrected and the stale index table removed.
- **Signposts** — the one-line italic pointer at the top of all 68 files under `docs/prompts/`, of `docs/build-log.md`, and the *Not an engineer? Start here* section at the top of `README.md`.
- **`CLAUDE.md`** — *Decision register* and *Build story* standing instructions; *Build Approach* four appends; the register in the tree; known-debt line closed; *What's next* → prompt 24.
- **`docs/BACKLOG.md`** — MCP-server item under *Future work*, requested at stop 1.

## Method and deviations from the plan

- One phase per reviewed stop for prompts 01–04; at Dermot's direction prompts 05–23 were then written in one pass and reviewed as a whole. One commit per phase throughout (29 commits for the phase).
- **Format revised twice at review:** the one-line opener became a *TL;DR* paragraph of three or four plain sentences in a simpler voice; a bold *Technologies* line was added after it. Both recorded in the plan's *Approval* section.
- **The archive README was restructured at stop 1** rather than at the end, because the entries needed a home from the first stop.
- **R-09:** the written 9.1 record presents the registry build as the plan from the start and says nothing about a free-trial block; the entry says so and carries Dermot's recollection, labelled as such (decision taken 21 September to avoid a Docker Desktop prerequisite; the free-trial subscription refused registry build tasks on 1 October; upgraded to Pay-As-You-Go that day, credit kept).
- **Where the record is silent on who decided** (R-03, R-14, R-15), the entries say so rather than attribute.
- Forward references appear in build-story entries 01, 02, 04 and 09 under the rule agreed at stop 1; no register entry reaches forward.

## Verification

- Every Markdown link and anchor in both documents resolves; every build-log section named in a *Technical detail* line exists; every archive file begins with the signpost whose anchor is its own entry number. Final check: 207 links, 44 anchors, 41 build-log section references, 68 signposted files, zero problems from this phase; one pre-existing historical link in the Phase 8.5.2 build-log entry points at a backlog section Phase 8.6 removed and is left as the record stands.
- `backend/tests/test_anonymisation.py` (scans `docs/`, `README.md`, `CLAUDE.md`): passed.
- The code suite is unchanged by this phase: 429 passed, 0 failed, 15 skipped.

## Addendum (31 October 2026)

At Dermot's request after close-out: every TL;DR ends with the weekday, full date and time the phase finished (report timestamp where one exists, otherwise the closing commit, noted in the *Technical detail* line); `docs/prompts/README_TLDR.md` created and, with the at-a-glance table, regenerated from the entries; the standing rule for that regeneration added to `CLAUDE.md`. Later the same day: times of day removed from the TL;DRs (weekday and date only), rule updated and both copies regenerated; glossary term *Retrieval (and embedding)* added to both documents; two sentences on retrieval added to entry 02.

## Suggestions (not in scope)

- A plain-language *Start here* for the production-architecture column of `docs/architecture-stack-reference.md`, in the same standard.
- Keep the at-a-glance table and register count in step at every close-out; the two standing instructions now require it.
