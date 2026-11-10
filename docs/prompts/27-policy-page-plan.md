> *Plain-language summary of this phase: see [the build story](README.md#entry-27), entry 27.*

# Prompt 27 — Plan: Policy page

**Prompt:** `27-policy-page.md`. **Scope:** one read endpoint, one page, links from the places that name a passage. **Written:** 10 November 2026. **Status:** approved 10 November 2026.

## 0. What the survey found

- **The table.** `policy_chunks` (migration 0001): `chunk_id`, `source_path`, `section`, `chunk_index` (document-global, `UNIQUE (source_path, chunk_index)`), `content`, `token_count`, `embedding VECTOR(384)`, `embedding_model`, `created_at`. The Validator scopes retrieval with `WHERE source_path = %s` using `str(settings.retrieval.policy_source_path)` (`backend/app/agents/validator.py`, `_retrieve_top_chunks`). "Position within the section" is not stored; it is the passage's rank by `chunk_index` among its section's rows.
- **Where a passage renders today** (prompt §3; `frontend/src`, excluding fixtures and JSON dumps):
  1. `components/HumanReviewPanel.tsx`, *Evidence*: the heading reads **Cited policy clauses** but the list is `payload.retrieval.chunks` of the `coverage_check` row, that is the three *retrieved* passages (`chunk_id`, `section`, `similarity`, `content_excerpt`), not the verdict's `cited_chunks`. The file's own comment explains why: `cited_chunks` carries ids without text. Each item renders `section: content_excerpt`. **Untested today:** `HumanReviewPanel.test.tsx` has no `coverage_check` fixture.
  2. `components/AgentCard.tsx`, the Validator card: collapsed, the SSE summary `{"covered": true}`; expanded, the whole `verdict` as a JSON block. No section name renders as text, so there is nothing to turn into a link without adding a line (D1).
  3. `pages/AgentsPage.tsx` (the test bench) renders a result JSON block with fixture ids: not a link target.
  4. `pages/ComparePage.tsx` and `pages/AuditPage.tsx` show no passages (the Audit page shows payload JSON).
  5. `copy/integrations.ts` `promptsCaption`: "the resource is the policy excerpt the Validator searches" — the one mention of the resource in prose; the resources table lists `policy://excerpt` with the description the server supplies.
- **The MCP resource** `policy://excerpt` (`backend/app/mcp/templates.py`) reads the text file, not the table. Two representations of one source; the Policy page shows the indexed one, which is what retrieval searches, and says so.
- **Deployed databases.** The record says both hold the indexed policy: Azure's bootstrap on 1 October 2026 logged `Indexed 12 chunks (2388 total tokens)` (Phase 9.1 report); Neon was re-indexed at the 8.5.3 reset and has served every Render run since. Live confirmation is in §6 and needs no database credential: the new endpoint itself answers it.
- **Azure today** (read-only, 10 November): revision `--0000027` on `0.10.0.3`, no replicas, `minReplicas` 0, Postgres `Ready`. No start needed; the first request cold-starts a replica in about half a minute. Render `/health` also `0.10.0.3`.
- **Test environment.** Vitest runs under jsdom, which has no `scrollIntoView`; the page guards the call (D7).

## 1. The endpoint

`GET /api/policy`, in a new `backend/app/api/policy.py` (`policy_router`, prefix `/policy`), registered in `backend/app/api/__init__.py`. Unauthenticated like every other `/api` route: the policy text is synthetic and already public in the repository, and the response carries no secret and no vector.

**Response shape (full):**

```json
{
  "source": "backend/data/sample_policy.txt",
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "passage_count": 12,
  "sections": [
    {
      "name": "General Conditions",
      "passages": [
        {
          "chunk_id": "7d0b…",
          "section": "General Conditions",
          "chunk_index": 0,
          "position": 1,
          "section_size": 2,
          "text": "…",
          "token_count": 281
        }
      ]
    }
  ]
}
```

Pydantic views with `extra="forbid"`: `PolicyPassageView`, `PolicySectionView`, `PolicyIndexView`. `embedding_model` is `null` when nothing is indexed. `position` is 1-based within the section; `section_size` is that section's passage count, so the page can say "passage 2 of 3" without counting.

**Query** (the only SQL; no `embedding` column is named):

```sql
SELECT chunk_id, section, chunk_index, content, token_count, embedding_model
FROM policy_chunks
WHERE source_path = %s
ORDER BY chunk_index
```

**Source resolution.** `str(settings.retrieval.policy_source_path)`, the same expression the Validator uses, so the page and retrieval cannot disagree. The value is echoed as `source`.

**Grouping.** A pure function `group_passages(rows) -> PolicyIndexView` keeps sections in order of first appearance by `chunk_index`, numbers positions within each section, and takes `embedding_model` from the rows. Guard: if the rows carry more than one `embedding_model`, raise `ValueError` naming the models found — a mixed index would make every similarity meaningless and must be visible, not averaged away. Sanitise → validate → abort → execute, as the other routers do; `run_in_threadpool` + `open_connection(settings)`, the `audit.py` pattern.

**Empty case.** No rows for the source → `200` with `passage_count: 0`, `sections: []`, `embedding_model: null`. Not an error: an un-indexed deployment is a state the page explains.

**Interface stability.** A new HTTP surface, additive: no existing endpoint, payload, SSE event, table or setting changes. Acknowledged here; added to *Locked interface extensions* in `CLAUDE.md` at close-out as "`GET /api/policy` — Prompt 27".

## 2. The page

**Files.** `frontend/src/pages/PolicyPage.tsx` (new), `frontend/src/copy/policy.ts` (new), `api/types.ts` (`PolicyIndex`, `PolicySection`, `PolicyPassage`), `api/client.ts` (`getPolicy`), `hooks/queries.ts` (`usePolicy`, long `staleTime`: the index changes only on re-index), `App.tsx` (route `/policy`; nav link *Policy* between *Integrations* and *Guide*, D4).

**Layout.** Title *Policy*. A card with the opening paragraph. A line with the count, the model and the source, from the endpoint. Then one card per section: an `h2` with the section name and, inside, one block per passage: `<article id={chunk_id}>` with a small label and the text in `whitespace-pre-wrap`. Loading shows the spinner; a failed load shows the error banner; an empty index shows the empty-state paragraph in place of the sections.

**Anchors and highlight (D7).** The anchor is the raw chunk id (a UUID is a valid element id), so `/policy#<chunk_id>` is stable across deployments of the same index. A small hook reads `useLocation().hash`; when it names a rendered passage, the block is scrolled into view (`element.scrollIntoView?.({ block: 'center' })`, guarded for jsdom) and carries `aria-current="true"` plus an amber ring and background while the hash matches. Changing the hash moves the highlight; clearing it removes it.

**Copy, for approval** (`copy/policy.ts`):

> **Title:** Policy
>
> **Opening:** This is the commercial property policy excerpt the system checks claims against. It is a sample written for the demonstration, not a real policy. It is shown here split into the passages the Validator searches: when a claim is processed, the three passages closest in meaning to the claim's description are retrieved and given to the Validator, and nothing else.
>
> **Count line (template):** {count} passages from {source}, embedded with {model}.
>
> **Passage label (template, D5):** {section}, passage {position} of {size} · {tokens} tokens
>
> **Empty state:** No policy is indexed on this deployment, so there is nothing to show here, and the Validator cannot run until one has been indexed.
>
> **Load failure:** Could not load the policy.

## 3. Links

| Place | Today | Change |
|---|---|---|
| Guide, *Links* card | four external links + the Integrations line | A new internal link *The policy* — "the wording every claim is checked against, split into the passages the Validator searches" — rendered with `<Link to="/policy">` like the Integrations line, listed before it (`guideCopy.policyLink`). The external-links test keeps its `https` rule for `guideLinks`. |
| Guide, *How it works*, first part | plain string | The body becomes segments (the `GuideSegment` shape from Prompt 26, extended with `{ link, to }`): "Before any claim arrives, [the policy wording](/policy) is split into twelve short passages. …". The `Sentence` component renders a link segment as `<Link>`. |
| Human review panel, *Evidence* (D2) | heading *Cited policy clauses*; `section: excerpt` per retrieved passage; nothing links | Heading becomes **Retrieved policy passages**, which is what the list is. Each section name is `<Link to="/policy#<chunk_id>">`. A passage whose `chunk_id` is in the verdict's `cited_chunks` carries a *cited* badge, so the panel finally shows the distinction its old heading implied. |
| Run page, Validator card (D1) | passages only inside the JSON response block | A one-line list under the header, shown without expanding, in the style of the Guardrail card's *Refused objections* line: **Passages:** *General Conditions* (cited) · *Named Perils Covered* (cited) · *Exclusions*, each section name a `<Link>` to its passage. Read from the `coverage_check` entry's `retrieval.chunks` and `verdict.cited_chunks`; absent or malformed → nothing rendered. |
| Integrations page, prompts-and-resource caption | "… the resource is the policy excerpt the Validator searches." | "the policy excerpt" becomes `<Link to="/policy">`; the caption is split into before / link text / after in `copy/integrations.ts`. The resources table itself is unchanged (its rows come from the server). |
| Test bench, Compare, Audit | JSON blocks | No change: no section name renders as text, and the test bench's ids are fixtures. |

## 4. Guide consistency

The Guide's "twelve short passages" stays prose. The Policy page is the source of the true number, and the Guide's words now link to it, so a reader can check in one click. If a re-index ever changed the count, the Guide sentence is edited by hand; the copy test pins the word *twelve*, so the change is deliberate and reviewed, and the Policy page needs no edit. The Guide does not fetch data.

## 5. Tests

**Backend — `backend/tests/test_policy_api.py`** (the `test_audit_api.py` style: `clean_db` + `db_settings`, `TestClient(create_app(db_settings))`, rows inserted by SQL). A helper inserts a chunk with a deterministic 384-float vector (the `test_validator.py` insert), under `str(db_settings.retrieval.policy_source_path)` unless told otherwise.

1. *populated, in document order, grouped by section* — four passages inserted out of index order across three sections (A0, B1, A2, C3): sections come back `A, B, C` by first appearance; A has positions 1 and 2 with `section_size` 2; `passage_count` 4; `embedding_model` the inserted value; `text` and `token_count` round-trip.
2. *empty index* — `200`, `passage_count` 0, `sections` `[]`, `embedding_model` `null`, `source` echoed.
3. *scoped to the configured source* — a chunk under another `source_path` is not returned.
4. *no vectors in the response* — `"embedding"` does not occur anywhere in `resp.text`, and every passage's key set equals exactly `{chunk_id, section, chunk_index, position, section_size, text, token_count}`.
5. *mixed embedding models abort* — `group_passages` on rows naming two models raises `ValueError` whose message names both (tested on the function, because `TestClient` re-raises server exceptions).
6. *grouping is pure* — `group_passages([])` returns the empty index without touching the database.

**Mutation proof for "no vectors"** (applied, observed, reverted): add `embedding` to the `SELECT` and to the passage dict the row becomes; test 4 fails on both assertions (the key set differs, and `"embedding"` appears in the body). Recorded in the report.

**Frontend.**

- `pages/PolicyPage.test.tsx` (new): with `stubFetch` serving a two-section index — section headings and passage texts render, the label reads "Exclusions, passage 2 of 3 · 116 tokens", the count line reads from the stub ("3 passages … embedded with BAAI/bge-small-en-v1.5"); the empty index shows the empty-state sentence and no sections; the route `/policy#<chunk_id>` marks that article `aria-current="true"` and no other; `scrollIntoView` is stubbed on the prototype and asserted called once.
- `copy/guide.test.ts`: `policyLink` label and detail; the first *How it works* body contains a link segment with `to: '/policy'` and text "the policy wording"; the flattened text is unchanged.
- `pages/GuidePage.test.tsx`: *The policy* link has `href="/policy"`; the *How it works* link renders.
- `components/HumanReviewPanel.test.tsx`: a `coverage_check` fixture with two retrieved chunks, one cited — the heading *Retrieved policy passages*, two section links with `href="/policy#<id>"`, the *cited* badge on one.
- `components/AgentCard.test.tsx`: a Validator entry — the *Passages* line lists both sections as links, marks the cited one, and is absent when the entry has no `retrieval` block.
- `pages/IntegrationsPage.test.tsx`: the caption's "the policy excerpt" is a link to `/policy`.

Expected counts: backend 521 → 527 (plus 18 skipped); frontend 57 → about 66.

## 6. Version (D3)

`0.10.1`. The project's pattern: a phase that adds a capability takes a minor bump (9.1 → `0.9.0`, 9.2 → `0.9.1`, 10 → `0.10.0`); point releases have been fixes and text (`0.10.0.1`, `0.10.0.2`, `0.10.0.3`). A new HTTP surface and a new page are a capability. Bumped in `pyproject.toml` and `uv.lock`; the backend must redeploy in any case for the endpoint.

## 7. Deployed verification, Dermot present

1. Push → CI green → `deploy-backend.yml` rolls the image, `deploy-frontend.yml` publishes; Vercel and Render deploy automatically.
2. **Confirm both deployed databases hold an indexed policy before relying on them**, with the endpoint itself (read-only, no credential): `GET /api/policy` on the Azure backend and on Render, expecting `passage_count` 12 and the bge-small model. If either returns 0, stop and index it (`python -m backend.data.index_policy` against that database is an operational act taken with Dermot, as on 1 October), then continue.
3. Azure frontend: the Policy page read through, seven sections, twelve passages, the count line.
4. From an Azure run page (the Coral Bay run `e9566e92` or a fresh Harborline run): the Validator card's *Passages* line → a passage on the Policy page, scrolled into view and highlighted; the same from the human review panel of the Northwood claim.
5. The count line against the database: `SELECT count(*) FROM policy_chunks WHERE source_path = …` on Azure, connection string read from Key Vault `database-url` into the process environment only, hostname echoed only, as Phase 10 did. Expected 12 = 12.
6. Vercel and Render in passing (Policy page, `GET /api/policy`).
7. `azure-stop.sh` only if Dermot says so.

## 8. Contradictions and loose ends in the record

- **Prompt 26** said a Policy page "belongs to the UI phase" (Phase 8.7); this prompt builds it on its own. A change of sequencing, not of fact; the Phase 8.7 backlog entry does not list a Policy page, so nothing there needs amending.
- **The human review panel's heading** *Cited policy clauses* names the verdict's citations but lists the retrieved passages (§0). D2 corrects the heading and shows the citations.
- **`CLAUDE.md`'s project tree** shows `backend/app/rag/`, which does not exist: retrieval lives in `agents/validator.py` and the indexer in `backend/data/index_policy.py`. The tree is labelled a target; one line is corrected at close-out while the tree is being edited anyway.
- **The backlog's route list** for Phase 8.7 names "Human Review (`/human-review` or similar)" as a route; it is a panel on the claim page. Left as is; noted.
- **`policy://excerpt`** serves the text file while the page serves the table. Not a contradiction while the two agree; the page's opening says which one it shows.

## 9. Files

| Area | Files |
|---|---|
| Backend | `backend/app/api/policy.py` (new), `backend/app/api/__init__.py`, `backend/tests/test_policy_api.py` (new) |
| Frontend | `api/types.ts`, `api/client.ts`, `hooks/queries.ts`, `App.tsx`, `pages/PolicyPage.tsx` (new), `pages/PolicyPage.test.tsx` (new), `copy/policy.ts` (new), `copy/guide.ts`, `copy/guide.test.ts`, `pages/GuidePage.tsx`, `pages/GuidePage.test.tsx`, `components/HumanReviewPanel.tsx`, `components/HumanReviewPanel.test.tsx`, `components/AgentCard.tsx`, `components/AgentCard.test.tsx`, `copy/integrations.ts`, `pages/IntegrationsPage.tsx`, `pages/IntegrationsPage.test.tsx` |
| Version | `pyproject.toml`, `uv.lock` |
| Close-out | `docs/build-log.md`, `docs/prompts/README.md` (+ regenerated table and `README_TLDR.md`), `docs/prompts/27-policy-page-report.md`, `CLAUDE.md` (status, tree, *Locked interface extensions*), signposts |

**Unchanged:** the agents, the retrieval query, the audit chain, the indexer, every existing HTTP and SSE shape, every setting. No new dependency.

## 10. Risks

- **Function size.** `PolicyPage` splits into `PolicyPage`, `SectionCard`, `PassageBlock` and a `useAnchorHighlight` hook; the backend router into the route, `group_passages` and the row reader. Each under 30 lines.
- **A fresh index changes every chunk id**, so links in old audit rows point at passages that no longer exist. The page then shows no highlight and the reader sees the full policy; acceptable for a prototype, stated in the report.
- **Long text on the page.** Twelve passages of 60–300 tokens is about four screens; sections are cards so a reader can skim headings.

## 11. Decisions requested

- **D1 Validator card.** Add the *Passages* line (sections linked, cited ones marked) so the card has something to link; the JSON block stays as it is. *Recommended: yes.*
- **D2 Human review panel.** Rename the heading to *Retrieved policy passages*, link each section, badge the cited ones. *Recommended: yes.*
- **D3 Version.** `0.10.1`, minor. *Recommended: yes.*
- **D4 Navigation.** *Policy* between *Integrations* and *Guide*. *Recommended: yes.*
- **D5 Passage label** includes the token count ("… · 255 tokens"). *Recommended: yes.*
- **D6 Mixed embedding models** abort with `ValueError` rather than picking one. *Recommended: yes.*
- **D7 Anchor and highlight.** Raw chunk id as element id; `aria-current` + amber ring while the hash matches; guarded `scrollIntoView`. *Recommended: yes.*

Optional, not part of the specification:

- **O1** A README line under the API or documentation index naming the Policy page, if the README lists pages or endpoints (to be checked at build; added only if such a list exists). *Recommended: yes if the list exists.*

---

**Approved by Dermot, 10 November 2026 (2026-11-10T14:11Z).** D1 to D4, D6 and D7 as recommended; **D5 no** — the token count stays off the passage label (the endpoint still returns it); O1 as recommended. Verbatim: *"Approved: D1 to D4, D6 and D7 as recommended. D5 no: leave the token count off the passage label; the endpoint may still return it. O1 as recommended. Commit the prompt and plan, then build."*
