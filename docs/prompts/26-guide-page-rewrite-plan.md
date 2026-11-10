> *Plain-language summary of this phase: see [the build story](README.md#entry-26), entry 26.*

# Prompt 26 — Plan: Guide page rewrite

**Prompt:** `26-guide-page-rewrite.md`. **Scope:** frontend text and layout, the two glossaries, a point release. **Written:** 10 November 2026. **Status:** approved 10 November 2026.

## 0. The three fact checks, and four more the wording needed

The prompt asks for three facts to be verified before its text is used. Each was checked against the code or by running it; two further statements in the supplied wording were checked because they make claims about the agents.

| # | Statement in the prompt's text | Finding | Source |
|---|---|---|---|
| F1 | "the policy wording is split into twelve short passages" | **Confirmed.** The chunker run on `backend/data/sample_policy.txt` with the bge-small tokeniser produces 12 chunks, 2,388 tokens, matching the build log's `Indexed 12 chunks (2388 total tokens)`. Two chunks each for General Conditions, Named Perils Covered, Exclusions, Sub-Limits and Duties After Loss; one each for Definitions and Business Interruption. No test pins the count: `test_index_policy.py` requires only at least one chunk for each of the seven sections. | `backend/data/index_policy.py` (`chunk_markdown_sections`, 200–300 tokens), run on 10 November 2026 |
| F2 | "returns the three passages closest in meaning" | **Confirmed.** `RetrievalSettings.top_k` defaults to 3 (bounds 1–20); `settings.yaml.template` says 3; neither `infra/bicep/main.bicepparam` nor `render.yaml` overrides it, so both deployments retrieve three. | `backend/settings.py` line 419 |
| F3 | "A settlement over $250,000, low confidence from the Validator or Adjuster, or a Guardrail failure sends the claim to a person" | **Matches the three threshold rules and one hard rule** in `policy.yaml`: `settlement_over_ceiling` (> 250000), `validator_confidence_floor` (< 0.65), `adjuster_confidence_floor` (< 0.75), `guardrail_failed`. **Three hard rules are left out:** `claim_type_watchlist`, `claimant_watchlist` (both watchlists are empty in this deployment) and `cross_jurisdictional` (markers `/`, `multi-jurisdiction`, `cross-border`). None of the three scenarios triggers them. See D3. | `backend/app/escalation/policy.yaml` |
| F4 | "**Validator** … decides whether the loss is covered, quoting the passages it relied on" | **Not quite right.** The Validator returns `cited_chunks` (chunk id and section name, one to three of them) and a `policy_basis` sentence; it names the passages, it does not quote their text. The passages themselves are recorded in the audit as `retrieved_chunks`, so a reader can see them, but the word *quoting* describes something the agent does not do. See D2. | `backend/app/agents/validator_models.py` (`CitedChunk`, `ValidatorVerdict`) |
| F5 | "**Adjuster** proposes a settlement figure within the market range for that type of loss" | **Confirmed, with one nuance:** the range is looked up by claim type *and severity*. "For that type of loss" is a fair plain-language reading; no change proposed. | `backend/app/prompts/system/adjuster.md` |
| F6 | "**Guardrail** checks … for personal data, biased language and references to policy wording that does not exist" | **Confirmed.** The three flag kinds are `pii`, `bias`, `hallucinated_citation`; a deterministic rule engine runs first and the model's citation claims are verified in code (Phase 9.2.2). | `backend/app/prompts/system/guardrail.md`, `guardrail_llm_flags.py` |
| F7 | "Each row carries a SHA-256 hash, a short code calculated from the row's contents and the hash of the row before it" | **Confirmed as a simplification.** Each row has two hashes: a row hash over its canonical bytes and a chain hash over `row_hash ‖ previous chain_hash`. One sentence covering both is accurate about what a reader needs: alter or remove a row and every later chain hash fails. "The claim's description" in the retrieval paragraph is the claim narrative as submitted, which is what the Validator embeds. | `backend/app/audit/chain.py`, `validator.py` `_embed_narrative` |

Also checked: "One click checks the whole trail" is the Audit page's *Verify chain (whole ledger)* button; "The answer is read from the audit trail, never worked out afresh" is the stated contract of `backend/app/mcp/explain.py`; "deployed on Azure" is true (the system is also deployed on Render / Vercel / Neon; the glossary currently says "two clouds").

## 1. What changes, section by section

### 1.1 "What this is"

Replaced by the prompt's text, with D2 applied if approved. The copy module stops holding one string: `whatIntro` (first sentence pair), `agents` (four `{name, detail}` entries, rendered as a list with the name in bold), `whatRules` (the rules-and-audit sentence pair) and `whatScope` (the prototype's-scope paragraph, the one place the word *prototype* appears).

### 1.2 "How it works" — new, after "What this is"

Five paragraphs as the prompt gives them, each as `{lead, body}` so the bold lead renders from data (*Preparing the policy*, *Finding the relevant wording*, *Deciding*, *Recording*, *Asking it questions*). The *Deciding* paragraph gains one sentence if D3 is approved.

### 1.3 "Try it" — new, before "The three scenarios"

Button and link labels are taken from the components as they render today: the three demo buttons are labelled *Auto-approve ($85k water damage)*, *Threshold escalation ($850k fire)* and *Guardrail escalation ($1.4M storm)* (`frontend/src/fixtures/demoClaims.ts`); the form's button is *Submit Claim*; the row actions are *Process* and *Re-process with v2*; the run page has *View audit log*; the Audit page has *Verify chain (whole ledger)*; the claim page shows the *Human review* panel with *Approve* and *Reject* when the claim is awaiting a person, and *Compare selected* once two runs are ticked. Note that *Process* both starts the pipeline and opens the run page, so the prompt's "start the pipeline" and "read the run page" are steps 3 and 4 of one action.

Draft, for approval (each step one sentence):

> 1. On the Claims page, press one of the three buttons above the form, *Auto-approve ($85k water damage)*, *Threshold escalation ($850k fire)* or *Guardrail escalation ($1.4M storm)*, and the form fills in with that scenario.
> 2. Press *Submit Claim*, and the claim appears in the list below.
> 3. Press *Process* on its row: the run page opens and the four agent cards fill in as each agent finishes.
> 4. Read the run page: the status badge is the outcome, and each card opens to show what the agent was asked and what it answered.
> 5. Press *View audit log*, then *Verify chain (whole ledger)*, to check every recorded step against its hash.
>
> To decide an escalated claim, open it from the Claims list by the claimant's name and use *Approve* or *Reject* in the Human review panel. To see the same claim handled a second way, press *Re-process with v2* on its row, which runs the Validator under a stricter instruction, then open the claim, tick the two runs and press *Compare selected*.

The labels are rendered in italics on the page (the `<em>` element), not in quotation marks.

### 1.4 "The three scenarios" — Coral Bay

One sentence appended to Coral Bay's detail, draft:

> That citation is planted: for this scenario the Adjuster's answer comes from a fixed file rather than the model, so the run behaves the same every time, and the audit trail records it as demo_fixture: true.

Fact basis: `backend/app/agents/adjuster.py` returns `backend/data/demo_fixtures/guardrail_adjuster.json` for a claim tagged `guardrail_escalation`; the fixture's reasoning cites *Endorsement Coastal Surge Rider*; the audit payload carries top-level `demo_fixture: true` and no `llm_call.prompt`.

### 1.5 "Reading a run page" and the Guardrail card

"refused claims" becomes "refused objections" in the paragraph and in `AgentCard.tsx`'s line (*Refused objections (n):*). The explanatory half of the paragraph ("things the model said were policy citations that the code could not find in the Adjuster's text, each with the reason it did not count") stays. The card's `data-testid` is renamed with it (D7). Audit keys and payloads are untouched: the card still reads `llm_flags_discarded`.

### 1.6 The line about data

Draft:

> The claims here are synthetic and this site is open to anyone with the address, so do not enter real personal details.

Placement (D6): the Claims page, inside the *Submit a claim* card, above the three demo buttons, so it is the first line a visitor reads on the home route. The text lives in `guide.ts` as `guideCopy.dataNotice` so that every visitor-facing sentence is in one reviewed module.

### 1.7 Links

Five links, in this order: *Interactive architecture diagram* ("the production design in four views, the last marking what is built and what stands in"); *How the system was tested* → `…/blob/main/docs/test-evidence.md` (new); *The build story, phase by phase*; *The decision register*; *The repository*. No Policy page link.

## 2. The glossary decision (D1)

**Does any test enforce the match?** No. `guide.test.ts` has a test named *opens with the glossary definition of the system*, but it checks two phrases of the current Guide text, not the glossary; nothing reads the two documents. The regeneration script rebuilds only the at-a-glance table and `README_TLDR.md` from the entries; the glossary is edited by hand, and the TLDR carries no glossary. The only tie is the comment in `guide.ts`.

**Recommended:** change *The system* in both glossaries to the first and last paragraphs of the new text, spliced into one entry because the first paragraph ends in a colon that introduces the agent list:

> **The system.** An agentic insurance claims processor: four AI agents handle a claim in turn, a set of rules decides whether it settles or goes to a person for review, and every step is recorded in an audit trail that shows if anything has been altered. The claims are synthetic and the policy is a short excerpt, so its scope is a prototype's. It is built and run to production standards: deployed on Azure, tested, audited and change-controlled.

The agent list stays on the Guide only. The `guide.ts` comment is rewritten to say that `whatIntro` + `whatScope` is the glossary's definition. The regeneration script is run at close-out anyway (entry 26); it will report the glossary change as nothing to do, because it does not read the glossary.

**The alternative** (leave the glossary as it is) costs a comment that is no longer true, or its deletion, and a Guide that defines the system one way while the two documents a reader is sent to define it another ("deployed on two clouds" against "deployed on Azure"). It saves two one-line edits. Not recommended.

## 3. Files touched

| File | Change |
|---|---|
| `frontend/src/copy/guide.ts` | Rewritten as above; new keys `whatIntro`, `agents`, `whatRules`, `whatScope`, `howHeading`, `how[]`, `tryHeading`, `trySteps[]`, `tryMore[]`, `dataNotice`; `guideLinks` gains the test-evidence link and the new diagram detail; comment updated. |
| `frontend/src/copy/guide.test.ts` | Updated and extended (see §4). |
| `frontend/src/pages/GuidePage.tsx` | Six cards: What this is (intro, agent list, rules, scope), How it works, Try it (`<ol>` with `aria-label="Try it steps"`, then the two further sentences), The three scenarios, Reading a run page, Links. Comment no longer claims one screen. |
| `frontend/src/pages/GuidePage.test.tsx` | Updated and extended. |
| `frontend/src/components/AgentCard.tsx` | *Refused objections (n):*; comment; `data-testid="refused-objections"`. |
| `frontend/src/components/AgentCard.test.tsx` | Assertions follow. |
| `frontend/src/pages/ClaimsPage.tsx` | `dataNotice` paragraph above the form inside *Submit a claim*. |
| `frontend/src/pages/ClaimsPage.test.tsx` | One assertion: the notice renders. |
| `docs/decision-register.md`, `docs/prompts/README.md` | Glossary entry *The system* (D1); entry 26 in the build story. |
| `docs/prompts/README_TLDR.md` | Regenerated by the script. |
| `pyproject.toml`, `uv.lock` | Version `0.10.0.2` → `0.10.0.3` (D5). |
| `docs/build-log.md`, `CLAUDE.md`, `docs/prompts/26-*.md` | Close-out: build-log entry *Prompt 26*, status, signposts, report. |

**Confirmation of scope.** Nothing under `backend/app/`, `backend/data/`, `backend/tests/`, `infra/`, `scripts/` or `.github/` changes. No HTTP or SSE shape, audit key, setting or agent prompt changes. The only non-frontend edits are the two glossaries, the build-story entry, the regenerated TLDR, the version in `pyproject.toml` / `uv.lock`, and the close-out documents.

## 4. Tests, in the existing style

`guide.test.ts` (Vitest, data-level, as today):

- *links to the five public documents with absolute https URLs*: five labels in order; the diagram URL unchanged; the test-evidence link ends `/docs/test-evidence.md`; the diagram detail is the new sentence.
- *opens with what the system is and names the four agents in order*: `agents` names are `Doc-Parser, Validator, Adjuster, Guardrail`; `whatScope` contains "its scope is a prototype's" and "built and run to production standards".
- *explains how it works in five parts with the stated numbers*: leads in order; the first body contains "twelve"; the second contains "three passages"; the third contains "$250,000".
- *gives five one-sentence steps that use the interface's own labels*: `trySteps` has length 5; each step contains exactly one sentence terminator; step 1 contains every label from `demoClaims` (imported, so a renamed button fails this test); steps 2, 3 and 5 contain *Submit Claim*, *Process*, *View audit log* and *Verify chain (whole ledger)*; `tryMore` mentions *Approve*, *Reject*, *Re-process with v2* and *Compare selected*.
- *names the three scenarios and their expected outcomes*: as today, plus Coral Bay's detail contains "demo_fixture: true".
- *points readers to the Guardrail card for refused objections*: contains "refused objections" and does not contain "refused claims".
- *warns about real personal details*: `dataNotice` contains "do not enter real personal details".
- The *stays within one screen* budget test is removed (D4).

`GuidePage.test.tsx`: the six card headings render; the ordered list labelled *Try it steps* has five items; the five links render with their exact hrefs; the Integrations link still points at `/integrations`.

`AgentCard.test.tsx`: *Refused objections (1)* on the renamed test id; the empty-list case unchanged.

`ClaimsPage.test.tsx`: the data notice is in the document on the Claims route.

Expected count: frontend 54 → about 58 (one test removed, five added or split). Backend unchanged at 521 passed, 18 skipped; `ruff`, `mypy`, ESLint, `tsc` and `vite build` must stay clean.

## 5. Version (D5)

`0.10.0.3`. The project's version lives in `pyproject.toml` only (`frontend/package.json` has said `0.0.1` since Phase 0 and is not the release number), so the point release is recorded there and in `uv.lock`, exactly as `0.10.0.1` and `0.10.0.2` were. One consequence to know: `deploy-backend.yml` treats `pyproject.toml` and `uv.lock` as backend paths, so the push will rebuild the Azure image and roll a new Container App revision whose `/health` reports `0.10.0.3`. That is how the version reaches a deployed surface, and it is what happened for the two earlier point releases; it costs one ACR build. The alternative is no bump, which leaves the deployed version unable to say the Guide changed. Recommended: bump.

## 6. Deployed verification, Dermot present

Azure's state on 10 November 2026, read-only: Container App `minReplicas` 0, no replicas, latest revision `--0000026` (one later than `CLAUDE.md` records; to be explained at verification, most likely the scale change made by `azure-stop.sh` on 4 November); **Postgres `Ready`, not `Stopped`**, so either the 4 November stop did not hold or Azure restarted it after seven days. Postgres does not need starting; a first request will cold-start a replica in about half a minute.

Sequence: push → CI green → `deploy-frontend.yml` publishes the Static Web App and `deploy-backend.yml` rolls the image (D5) → `/health` says `0.10.0.3` → the Guide is read on `https://delightful-beach-009db650f.5.azurestaticapps.net/guide` with Dermot: six sections, five links open, the Claims page shows the data line above the form, and a run with refused objections (the Render Harborline run of 30 October has them; on Azure, Coral Bay's card shows the line only if its Guardrail recorded discarded claims) shows *Refused objections*. Vercel deploys the same commit automatically and is checked in passing. Then `scripts/azure-stop.sh` as the last act, and its result recorded.

## 7. Close-out

Signposts on the prompt, this plan and the report (`README.md#entry-26`); build-log entry *Prompt 26* (what changed, the fact checks, counts, the deployed read); build-story entry 26, TL;DR ending with the weekday and date from the report's *Completed at*, Technologies "React and TypeScript for the page; Vitest for its tests; the two glossaries"; `uv run python scripts/regenerate-build-story.py` (expect exit 1, commit the rewrite); `CLAUDE.md` status; decision-register entry only if a halt or deviation occurs; commit and push. Anonymisation scan over the changed files.

## 8. Risks

- **The one-screen promise is gone.** The Guide was one screen by design in Phase 10; three new sections roughly double it. The prompt asks for them, so the page becomes a short read rather than a glance. Mitigation: the data line stays on the Claims page where the visitor starts, and the Links card stays last.
- **Labels drift.** A later UI phase may rename a button and leave "Try it" wrong. The `demoClaims` import guards the three demo labels; the others are string assertions that fail only if someone edits the Guide, not the button. Recorded as a known limit in the report; Phase 8.7 should re-read "Try it".
- **"twelve" and "three" are facts about today's configuration.** A different policy file or `top_k` would silently date the text. Recorded in the report; see O1.

## 9. Decisions requested

- **D1 Glossary.** Change *The system* in both documents to the spliced first-and-last-paragraph text in §2 and rewrite the `guide.ts` comment. *Recommended: yes.*
- **D2 Validator wording.** Use "naming the passages it relied on" in place of "quoting the passages it relied on" (F4). *Recommended: yes.*
- **D3 Hard rules.** Add one sentence to *Deciding*: "Three further rules in the same file, for a claimant or claim type on a watchlist and for a claim that spans more than one jurisdiction, also send a claim to a person; the watchlists are empty here." *Recommended: yes.*
- **D4 One-screen budget test.** Remove it and the "one screen" comments; the structural tests in §4 replace it. *Recommended: yes.*
- **D5 Version.** `0.10.0.3` in `pyproject.toml` and `uv.lock`, accepting the backend redeploy it triggers. *Recommended: yes.*
- **D6 Data line placement.** Claims page, inside *Submit a claim*, above the demo buttons; text in `guide.ts`. *Recommended: yes.*
- **D7 Test id.** Rename `refused-claims` to `refused-objections` so the test vocabulary matches the label. *Recommended: yes.*

Optional, not part of the specification:

- **O1** A backend test pinning the sample policy to 12 chunks, so the Guide's "twelve" has a guard. Outside this prompt's frontend-only scope; *recommended: no here, one line in the backlog.*
- **O2** A test that reads `guide.ts` and the two glossaries and asserts the glossary sentence is present in both and in the copy module. Would make D1's match enforced rather than commented. *Recommended: no;* it crosses the frontend/docs boundary and the comment has sufficed since Phase 10.

---

**Approved by Dermot, 10 November 2026 (2026-11-10T12:29Z).** D1 to D7 as recommended; O1 and O2 no. Verbatim: *"Approved: D1 to D7 as recommended, O1 and O2 no. Commit the prompt and plan, then build."*
