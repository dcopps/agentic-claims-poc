> *Plain-language summary of this phase: see [the build story](README.md#entry-27), entry 27.*

# Prompt 27 — Report: Policy page

**Prompt:** `27-policy-page.md`. **Plan:** `27-policy-page-plan.md` (approved 10 November 2026: D1–D4, D6 and D7 as recommended; D5 no; O1 as recommended). **Version:** `0.10.0.3 → 0.10.1`, live on both stacks. **Completed at:** 2026-11-10T16:05Z. **Status:** complete; the Policy page, the run-page links and the three additions read on the Azure frontend by Dermot and confirmed as intended.

## What was built

**Backend.** `GET /api/policy` (`backend/app/api/policy.py`, registered in `api/__init__.py`): the `policy_chunks` rows for `str(settings.retrieval.policy_source_path)` — the Validator's own expression — in `chunk_index` order, grouped by section in order of first appearance. Each passage carries `chunk_id`, `section`, `chunk_index`, `position` (1-based within its section), `section_size`, `text` and `token_count`; the whole carries `source`, `embedding_model` (`null` when nothing is indexed) and `passage_count`. The query names its six columns and the views forbid extras, so no vector can leave the server. Rows naming more than one embedding model raise `ValueError` listing them. An empty index answers `200` with a count of zero. Unauthenticated like the rest of `/api`; the text is synthetic and public.

**Frontend.** The *Policy* page at `/policy` (`pages/PolicyPage.tsx`, `copy/policy.ts`, `usePolicy`, nav entry between *Integrations* and *Guide*): the opening paragraph, the count line from the endpoint, one card per section, one `<article id={chunk_id}>` per passage with the label "Section, passage n of m" (D5: no token count) and, after Dermot's additions, `Chunk <first eight>` in grey monospace with a *Copy id* button. The URL hash highlights its passage (`aria-current`, amber ring) and scrolls it to rest below the sticky navigation (`scroll-mt-20`, `scrollIntoView({ block: 'start' })`, optional-called for jsdom); a hash naming a chunk id not in the index shows a plain-words notice above the sections. Empty and failed states are sentences. Links: the Guide's *Links* card gains *The policy* and "the policy wording" in *How it works* is a link (the `how` bodies became `GuideSegment[]` with a `{ link, to }` segment); the human review panel's heading **Cited policy clauses** became **Retrieved policy passages** — it always listed `retrieval.chunks` — with each section a link to its passage and a *cited* badge where the verdict's `cited_chunks` names it; the Validator card gained a *Passages* line with the same links and "(cited)"; the Integrations caption's "the policy excerpt" links to the page. The main navigation is `sticky top-0` on every page.

**Documents.** `CLAUDE.md`: status, the tree (`api/policy.py`; the non-existent `backend/app/rag/` line corrected), and the new entry under *Locked interface extensions*.

## Decisions as applied

D1 the Validator card's *Passages* line; D2 the review panel heading, links and badge; D3 version `0.10.1`; D4 nav position; **D5 no** — the passage label carries no token count, the endpoint still returns it; D6 the mixed-model abort; D7 raw chunk id as anchor, hash-driven highlight. O1: the README has no page or endpoint list, so nothing was added.

## Tests

Backend **527 passed, 0 failed, 18 skipped** (521 before): `test_policy_api.py` — grouping and order, the empty index, scoping to the configured source, no vectors in the body, the mixed-model guard, the pure empty grouping. `ruff` and `mypy --strict` clean. Frontend **68 passed** (57 before): the Policy page (sections, labels, count line, empty state, hash highlight with scroll position and margin, chunk label and copy button, the missing-anchor notice, failed load), the Guide's two links, the review panel's links and badge, the Validator card's line, the Integrations caption link, the sticky navigation. ESLint, `tsc -b`, Prettier and `vite build` clean.

**Mutation proof (applied, observed, reverted).** `embedding` added to the router's `SELECT`, threaded through `_as_row` and emitted on each passage view: `test_response_carries_no_vectors` fails on its first assertion (`assert 'embedding' not in '{"source":…":[0.0]}]}]}'`); five pass. Restored, six pass.

## Deployed verification, 10 November 2026, Dermot present

- `7e617a9` (the build) and `ea593cb` (the additions): CI green; *Deploy backend (Azure)* and *Deploy frontend (Azure Static Web Apps)* green on both; Vercel and Render deployed automatically. Azure `/health` and Render `/health` `0.10.1`.
- **Both deployed databases hold the indexed policy**, confirmed through the endpoint before relying on it: Azure and Render each return 12 passages, model `BAAI/bge-small-en-v1.5`, seven sections (General Conditions 2, Definitions 1, Named Perils Covered 2, Exclusions 2, Sub-Limits 2, Business Interruption 1, Duties After Loss 2) — the split the local chunker produces; the Azure body carries no vector.
- The count against the database: `SELECT count(*), count(DISTINCT section), min(embedding_model) FROM policy_chunks WHERE source_path = …` on the Azure server, connection string read from Key Vault `database-url` into the process environment only, hostname echoed only: `(12, 7, 'BAAI/bge-small-en-v1.5')`.
- Both deployed bundles contain the page, the new links and the additions, and no longer contain *Cited policy clauses*.
- Dermot read the Policy page, a run-page link and the three additions on the Azure frontend: *"The Policy page and the three additions read as intended."*

**Azure is deliberately left running** at the close: the repository's About link points at the Azure frontend, so parking it would break the first thing a visitor opens. Postgres `Ready`, `minReplicas` 0 (a replica starts on the first request).

## Findings and deviations from the plan

- None from the plan as approved. Three additions were made at Dermot's request before close-out (chunk id with copy button; the missing-anchor notice; sticky navigation with scroll margin), each with tests, no version change.
- The first `gh run watch` after each push returned before GitHub had registered the run; the deploy workflows were watched by id and completed green each time.
- Prettier re-wrapped the edited frontend files before each commit; ESLint had passed before and after.

## Interface-stability events (acknowledged in the plan)

`GET /api/policy`, additive. Unchanged: every existing endpoint, payload, SSE event, table, setting, agent prompt, the retrieval query, the audit chain and the indexer. No new dependency.

## Suggestions (not in scope)

- A backend test pinning the sample policy to 12 chunks (plan O1 of Prompt 26) would guard both the Guide's "twelve" and the Policy page's expected count.
- The anonymisation test cannot read inside the compressed architecture-diagram bundle (recorded 9 November); a decode step would close that gap.
- If the policy is ever re-indexed on a deployment, links in old audit rows show the missing-anchor notice by design; a re-index should be recorded in the build log with the date so a reader can place the notice.
