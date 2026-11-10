# Prompt 27 — Policy page

## Why this prompt exists

Every coverage decision in the system rests on the policy wording, and a visitor cannot read it. The Validator names the passages it relied on, the human review panel shows excerpts of them, and the Guide says the policy is split into twelve passages, but the policy itself is only in the repository as a text file. A reviewer who wants to see a named passage in its context has nowhere to look.

This prompt adds a Policy page to the app that shows the policy as it is indexed, and links to it from the places that name a passage. It is one small iteration: one read-only endpoint, one page, a handful of links. The wider UI phase (Phase 8.7 in `docs/BACKLOG.md`) is separate; do not start it here.

## What gets built

### 1. A read endpoint for the indexed policy

`GET /api/policy` returns the passages held in `policy_chunks` for the configured policy source, in document order, grouped by section: for each passage its chunk id, section, position within the section, text and token count; and for the whole, the source name, the embedding model recorded against the passages, and the passage count. No vectors are returned.

The endpoint reads the table, not the text file, so the page shows exactly what retrieval searches. It uses the same policy source the Validator's retrieval is scoped to, so the two cannot disagree. If nothing is indexed it returns an empty list with a count of zero, not an error.

This is a new HTTP surface and so an interface addition. It is additive: no existing endpoint, payload, SSE event or table changes. Acknowledge it in the plan and add it to *Locked interface extensions* in `CLAUDE.md` at close-out.

### 2. The Policy page (`/policy`)

A new page, *Policy*, in the top navigation. Text in a copy module, as with the Guide.

- A short opening: this is the commercial property policy excerpt the system checks claims against; it is a sample written for the demonstration; it is shown split into the passages the Validator searches.
- The sections in order, each with its heading and its passages. Each passage is a block with a stable anchor (by chunk id) so that it can be linked to, and a small label giving its position (for example "Exclusions, passage 2 of 3").
- One line stating the passage count and the embedding model, taken from the endpoint, not hard-coded.
- When a passage is reached by its anchor, it is scrolled into view and highlighted so the reader can see which one was meant.
- When nothing is indexed, the page says so in plain words.

### 3. Links to the page

- **Guide:** add *The policy* to the links, described as "the wording every claim is checked against, split into the passages the Validator searches", and link the words "the policy wording" in *How it works* to the page.
- **Run page:** wherever the Validator's retrieved or cited passages are shown (the Validator card and the human review panel), each passage's section name links to that passage on the Policy page. Survey where passages render today and list the places in the plan.
- **Integrations page:** where the `policy://excerpt` resource is mentioned, if it is, link to the Policy page too. If it is not mentioned, leave the page alone.

### 4. Guide consistency

The Guide says "twelve short passages". The Policy page shows the count from the database. If the two could ever disagree (a re-index with different settings), say in the plan how that is handled; the simplest answer is that the Guide's sentence stays as prose and the Policy page is the source of the true number. Do not make the Guide fetch data.

## Plan first

Produce `docs/prompts/27-policy-page-plan.md` covering:

1. The endpoint: path, response shape in full, the query, how the policy source is resolved, the empty case, and the interface-stability acknowledgement.
2. The page: layout, anchors, the highlight behaviour, the copy drafted for approval.
3. Every place a passage is rendered today, and which of them get a link.
4. Tests: backend tests for the endpoint (populated, empty, order, no vectors in the response) in the existing style with the real test database; frontend tests for the page (sections and passages render, the count line, the empty state, an anchored passage is highlighted) and for each new link. A mutation proof for the "no vectors" assertion.
5. Version: say whether this is a point release or `0.10.1`, and why.
6. Deployed verification with Dermot present: the Policy page read on the Azure frontend; a passage reached from a run page's link; the count line matching the database. Confirm both deployed databases hold an indexed policy before relying on it. Azure may be running or parked; check its state and start it if needed.
7. Anything in the record that contradicts this prompt.

Wait for explicit confirmation before writing code.

## Constraints

- Standing conventions per `CLAUDE.md`: plan first, defensive ordering, function size, settings hierarchy, text in copy modules, tests in the existing style, British English, no client name anywhere.
- No new dependency. No change to the agents, the retrieval query, the audit chain, the indexer, or any existing HTTP or SSE shape.
- Voice: plain and direct; "the policy", never "handbook"; no superlatives, no scare quotes.
- The endpoint is unauthenticated like the rest of the demonstration API; the policy text is synthetic and already public in the repository. Say so in the plan.

## Close-out

Report; build-log entry *Prompt 27*; build-story entry 27 with TL;DR and Technologies; signposts on this file, the plan and the report; the regeneration script; a decision-register entry for any halt or deviation; `CLAUDE.md` status, tree and *Locked interface extensions*; commit and push.

## Archive

Pre-saved at `docs/prompts/27-policy-page.md`; plan and report alongside.
