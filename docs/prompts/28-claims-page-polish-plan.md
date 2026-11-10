> *Plain-language summary of this phase: see [the build story](README.md#entry-28), entry 28.*

# Prompt 28 — Plan: Claims page polish

**Prompt:** `28-claims-page-polish.md`. **Scope:** the Claims page only, presentation only. **Written:** 10 November 2026. **Status:** approved 10 November 2026.

## 0. What the survey found

- **The list order.** `GET /api/claims` is `ORDER BY created_at DESC LIMIT %s` (`backend/app/claims/repository.py`), default limit 50, and the frontend passes no limit. The list is already newest first and shows the 50 most recent claims. Nothing to change; the *Submitted* column makes the order visible.
- **Claim types.** The backend's `ClaimType` Literal has six values, matching `market_data.yaml` (`water_damage`, `fire`, `wind`, `theft`, `flood`, `storm_complex`); the form offers those six. The seed generator produces nine, five of which (`sprinkler_leakage`, `vandalism`, `smoke_damage`, `hail`, `windstorm`) have no market range and abort at the Adjuster (backlog, *Five of the six seeded background claims abort*). The label table covers all eleven distinct values plus a readable fallback.
- **Statuses.** Eight in `claims.status` (seven from migration 0001 plus `aborted` from 0002). `running` is a run status, not a claim status; the mapping module includes it for the later pages.
- **`StatusBadge` is shared** by the Claims page, the claim page and the run page, and renders the raw value itself. To change the Claims page alone it gains an optional `label` prop (D1); the other pages keep passing nothing and are unchanged.
- **The tooltips (item 6) do not appear on keyboard focus.** `Tooltip.tsx` puts the text in a native `title` attribute on a wrapping `<span>` and marks the ⓘ glyph `aria-hidden`. A `title` shows on mouse hover only, in every browser; nothing is focusable and nothing is announced, so the check fails for keyboard and screen-reader users. D2 replaces the mechanism without changing the callers.
- **Where the old label appears.** *Re-process with v2*: `pages/ClaimsPage.tsx:112` (the button), `copy/guide.ts:174` (a *Try it* segment), `copy/guide.test.ts:86` (asserts that segment's labels), `docs/BACKLOG.md:90` and `:92` (the Phase 8.7 items, to be marked done at close-out). The tooltip key `reprocessV2`: `copy/tooltips.ts`, `copy/tooltips.test.ts`, `pages/ClaimsPage.tsx:110`.
- **Where raw status or type strings appear in the frontend.** As *values*, which stay: `api/types.ts` (the unions), `styles/tokens.ts` (the colour map, keyed by value), `components/ClaimForm.tsx` (`CLAIM_TYPES` and the default), `pages/ClaimsPage.tsx:12` (`REPLAYABLE`), `fixtures/demoClaims.ts`, test fixtures (`ClaimsPage.test.tsx`, `HumanReviewPanel.test.tsx`, `ui.test.tsx`, `AgentTestPanel.test.tsx`). As *displayed text*, which this prompt changes on the Claims page: the type cell, the status badge, the form's `<option>` text. Displayed elsewhere and left alone: `pages/ClaimDetailPage.tsx` (type field, badge), `pages/RunDetailPage.tsx` (badge), `pages/AgentsPage.tsx` (fixtures). The Guide names no status or type value.
- **Form fields** use `aria-label` plus a placeholder; the two date inputs have no placeholder at all, so once filled nothing says which is which — Dermot's 4 November finding. The existing tests find fields with `getByLabelText('Claimant name')`, which a real `<label htmlFor>` satisfies unchanged.
- **Documents.** `README.md`'s scenario table and `docs/walkthrough.md` quote `awaiting_human` as the *API* outcome and the run page's badge, which this prompt does not touch; both stay correct. `tooltips.ts` carries a comment "Locked at end of Phase 5" and `Tooltip.tsx` says "Phase 6 polish can replace this"; both are superseded by this prompt and the comments are rewritten.

## 1. Labels

### Claim types (`copy/labels.ts`, `claimTypeLabel`)

| Stored value | Label | Source of the value |
|---|---|---|
| `water_damage` | Water damage | form, seed |
| `fire` | Fire | form, seed |
| `wind` | Wind | form |
| `theft` | Theft | form, seed |
| `flood` | Flood | form |
| `storm_complex` | Storm (complex) | form, seed |
| `sprinkler_leakage` | Sprinkler leakage | seed only |
| `vandalism` | Vandalism | seed only |
| `smoke_damage` | Smoke damage | seed only |
| `hail` | Hail | seed only |
| `windstorm` | Windstorm | seed only |
| anything else | underscores to spaces, first letter capitalised (`hail_storm` → "Hail storm") | fallback, never hidden, never an error |

### Statuses (`statusLabel`)

| Stored value | Label | Note |
|---|---|---|
| `received` | Received | |
| `extracted` | Summarised | Since Phase 8.2 the Doc-Parser produces only the narrative summary; the structured fields come from the claim record. "Summarised" is what happened. |
| `coverage_verified` | Coverage checked | True whether the verdict was covered or not. |
| `estimated` | Settlement estimated | |
| `guardrail_checked` | Guardrail checked | |
| `settled` | Settled | |
| `awaiting_human` | Awaiting human review | |
| `aborted` | Aborted | |
| `running` | Running | run status; for the later pages |
| anything else | the same readable fallback | |

No wording changes proposed beyond the prompt's list. Badge colours are untouched: `statusBadgeClass` stays keyed by the stored value.

## 2. Drafts for approval

**Tooltips** (`copy/tooltips.ts`; what the button does here first, the production trigger in one clause):

> **Submit Claim:** Saves the claim to the claims-of-record table; nothing is processed until you press Process. In production the form would post to the claims system, which raises a ClaimReceived event on Azure Service Bus.
>
> **Process:** Runs the four agents on this claim now and opens the run page to watch them. In production the ClaimReceived event would start this automatically through Azure Durable Functions.
>
> **Re-run with strict Validator:** Runs the claim again with the Validator under a stricter instruction, so the two runs can be compared on the claim's page. In production a model-promotion event from the deployment pipeline would trigger it.

The Audit page's `verifyChain` text is not on this page and is left alone.

**Disabled state** (D4): while the button is disabled, its tooltip opens with "Not yet available: this claim has no finished run. " followed by the text above, and the button carries `aria-disabled`. Nothing extra is added beside the button, so the row stays one line.

**Field labels**: Claimant name, Policy number, Loss date, Reported date, Jurisdiction, Reported amount (USD), Claim type, Description. The `<textarea>`'s label changes from the aria-only "Narrative" to the visible "Description"; the stored field is still `narrative`.

## 3. Files touched

| File | Change |
|---|---|
| `frontend/src/copy/labels.ts` (new) | `claimTypeLabel`, `statusLabel`, the readable fallback; written for every page, used by the Claims page now. |
| `frontend/src/copy/format.ts` (new) | `formatUsd(value)` — `$850,000`, cents only when non-zero, the raw string back if it does not parse; `formatDateTime(iso, locale?)` — short date and time in the reader's locale ("4 Nov 2026, 11:08" in en-GB), the raw string back if it does not parse. |
| `frontend/src/copy/tooltips.ts` | The three texts rewritten; key `reprocessV2` → `rerunStrictValidator` (D6); `disabledNoFinishedRun`; comments updated. |
| `frontend/src/components/Tooltip.tsx` | D2: a state-driven popover — the wrapper is a `group`, the ⓘ becomes a real `<button type="button" aria-label="About this action">`, and a `role="tooltip"` element renders while the pointer is over the group or focus is inside it; the child receives `aria-describedby` when it is a single element. Callers unchanged. |
| `frontend/src/components/ui.tsx` | `StatusBadge` gains optional `label`; colour lookup still by `status`. |
| `frontend/src/components/ClaimForm.tsx` | Visible `<label htmlFor>` for the eight fields in a two-column grid; `<option>` text from `claimTypeLabel`, values unchanged; `aria-label`s removed. |
| `frontend/src/pages/ClaimsPage.tsx` | Amount via `formatUsd`; type via `claimTypeLabel`; `StatusBadge label={statusLabel(...)}`; new *Submitted* column via `formatDateTime(created_at)`; the second button renamed *Re-run with strict Validator* with the disabled-state tooltip. |
| `frontend/src/copy/guide.ts`, `guide.test.ts` | The *Try it* segment label → *Re-run with strict Validator*; the test's expected labels follow. |
| Tests (§5) | `labels.test.ts`, `format.test.ts`, `Tooltip.test.tsx` (new); `tooltips.test.ts`, `ClaimForm.test.tsx`, `ClaimsPage.test.tsx`, `ui.test.tsx` updated. |
| `pyproject.toml`, `uv.lock` | `0.10.1 → 0.10.1.1` (D5). |
| `docs/BACKLOG.md` | Committed now with the prompt and plan (the 10 November addition, unchanged); at close-out the Claims-page items under *Phase 8.7* are marked done. |
| Close-out | report, build-log entry *Prompt 28*, build-story entry 28, regenerated table and TLDR, signposts, `CLAUDE.md`. |

**Confirmation of scope.** Nothing under `backend/`, `infra/`, `scripts/` or `.github/` changes; no stored value, HTTP shape or SSE shape changes; the form still posts the same `ClaimSubmission` with the same `claim_type` values and a plain-number `reported_amount`. The only non-frontend edits are the version, the backlog and the close-out documents.

## 4. List order

Newest first already, from the API (`ORDER BY created_at DESC`, limit 50 by default). No change. The plan records the 50-row cap: a deployment with more than 50 claims shows the newest 50, which is the Azure state today (25 claims) with room to spare.

## 5. Tests, in the existing style

- `copy/labels.test.ts` (new): every value in both tables maps to its label; **an unmapped claim type falls back readably** (`hail_storm` → "Hail storm", `""` → `""`); an unmapped status likewise; the stored value is never returned altered for a mapped one.
- `copy/format.test.ts` (new): `"850000.00"` → `$850,000`; `"85000.50"` → `$85,000.50`; `"1400000.00"` → `$1,400,000`; `"abc"` → `"abc"`; `formatDateTime('2026-11-04T11:08:00Z', 'en-GB')` contains `4 Nov 2026` and `11:08` (the hour asserted in UTC by passing `timeZone: 'UTC'` through the helper's options, so the test does not depend on the machine's zone); a bad string comes back unchanged.
- `components/Tooltip.test.tsx` (new): no tooltip in the document at rest; **hover** over the group shows `role="tooltip"` with the text; **keyboard focus** (`user.tab()` to the ⓘ button) shows it and blur hides it; the wrapped button carries `aria-describedby` pointing at the tooltip's id.
- `copy/tooltips.test.ts`: each text names what the button does here first (asserted by the leading words) and still names its production trigger (Service Bus, Durable Functions, the deployment pipeline); the disabled sentence exists.
- `components/ClaimForm.test.tsx`: the eight visible labels are real `<label>` elements for their inputs (`getByLabelText` on each, plus the label element's text); the claim-type options show labels and carry stored values; **the form still submits stored values, not labels** — load the storm scenario, submit, and assert the POST body has `claim_type: 'storm_complex'` and `reported_amount: '1400000.00'`.
- `pages/ClaimsPage.test.tsx`: the row shows `$85,000`, "Water damage", "Received"; the *Submitted* column header and a formatted date for the fixture's `created_at` (set to a real ISO string); the button reads *Re-run with strict Validator* and is disabled for a `received` claim with the disabled sentence in its tooltip; existing Process tests unchanged.
- `components/ui.test.tsx`: `StatusBadge` with `label` shows the label and keeps the colour of the status; without `label` it shows the raw value as before.
- `copy/guide.test.ts`: the *Try it* labels list ends `['Re-run with strict Validator', 'Compare selected']`.

Expected: frontend 68 → about 84; backend 527 passed, 18 skipped unchanged.

## 6. Version (D5)

`0.10.1.1`, a point release: presentation only, no new surface. Recorded in `pyproject.toml` and `uv.lock` as the earlier point releases were; the bump makes `deploy-backend.yml` roll a new image whose `/health` reports it (as `0.10.0.3` did). The alternative is no bump, which leaves the deployed version unable to say the page changed. Recommended: bump.

## 7. Deployed verification, Dermot present

Push → CI green → both deploy workflows → Azure `/health` `0.10.1.1`; the Claims page read on the Azure frontend: amounts, labels, the *Submitted* column newest first, the form's visible labels, the three tooltips on hover and on Tab; one scenario (Harborline) loaded, submitted and processed to confirm the form posts the stored values and the run settles; the stored row inspected on the claim page (type and amount as before). Azure stays running throughout; `azure-stop.sh` is not run.

## 8. Contradictions and loose ends in the record

- `docs/BACKLOG.md` (Phase 8.7, Claims page) says *Re-process with v2* "reads like a text input"; it has been a secondary `Button` since Phase 6's `ui.tsx`. The item's remaining half (the name says nothing about what it does) is what this prompt fixes; the whole item is marked done at close-out.
- The same section asks to "verify tooltips are actually wired to a hover handler": they are wired to a native `title`, which is hover only. The keyboard and screen-reader gap found here is new; fixed by D2 and recorded.
- `tooltips.ts` says "Locked at end of Phase 5" and `Tooltip.tsx` says "Phase 6 polish can replace this". Both are superseded; the comments are rewritten.
- The backlog's survey lists the information icons beside *Submit Claim*, *Process* and *Re-process with v2*; that is still where they are.

## 9. Risks

- **Locale-dependent dates.** The *Submitted* column follows the reader's locale by design; the tests fix the locale and time zone so they do not depend on the machine. A visitor in the US sees "Nov 4, 2026, 11:08 AM"; that is the intent.
- **Tooltip as a focusable control.** Adding a focusable ⓘ adds a tab stop per action. Acceptable: it is the only way the text reaches keyboard users; the stop is labelled.
- **Function size.** `ClaimForm` splits into the form, a `Field` helper and the option list; `ClaimRow` stays under 30 lines with the formatting moved to the helpers.

## 10. Decisions requested

- **D1 `StatusBadge` label prop.** Optional `label`; the Claims page passes the plain-words label, the other pages are untouched. *Recommended: yes.*
- **D2 Tooltip mechanism.** A state-driven `role="tooltip"` popover shown on hover and on focus, with a labelled ⓘ button and `aria-describedby` on the action; callers unchanged. *Recommended: yes.*
- **D3 Status words** as the prompt lists them, no changes. *Recommended: yes.*
- **D4 Disabled-state wording** in the tooltip ("Not yet available: this claim has no finished run."), not beside the button. *Recommended: yes.*
- **D5 Version** `0.10.1.1`. *Recommended: yes.*
- **D6 Tooltip key** `reprocessV2` → `rerunStrictValidator`. *Recommended: yes.*
- **D7 Date format** via `Intl.DateTimeFormat` in the reader's locale, short month, 24-hour where the locale uses it; the helper takes an optional locale and time zone for tests. *Recommended: yes.*

No optional items.

---

**Approved by Dermot, 10 November 2026 (2026-11-10T15:59Z).** D1 to D7 as recommended. One wording change: the *Submit Claim* tooltip begins "Saves the claim; nothing is processed until you press Process." and the rest stays. Verbatim: *"Approved: D1 to D7 as recommended. One wording change: the Submit Claim tooltip begins \"Saves the claim; nothing is processed until you press Process.\" and the rest of it stays. Commit the prompt, the plan and the backlog edit, then build."*
