> *Plain-language summary of this phase: see [the build story](README.md#entry-28), entry 28.*

# Prompt 28 — Report: Claims page polish

**Prompt:** `28-claims-page-polish.md`. **Plan:** `28-claims-page-polish-plan.md` (approved 10 November 2026: D1–D7 as recommended; one wording change to the *Submit Claim* tooltip). **Version:** `0.10.1 → 0.10.1.1`, live on both stacks. **Completed at:** 2026-11-10T19:05Z. **Status:** complete; the Claims page read and used on the Azure frontend by Dermot and confirmed as intended.

## What was built

**Labels and formatting** (`frontend/src/copy/labels.ts`, `copy/format.ts`, both new). `claimTypeLabel` maps the form's six claim types and the seed generator's five extra to plain words ("Water damage", "Storm (complex)", "Sprinkler leakage"); `statusLabel` maps the eight claim statuses and `running` ("Summarised" for `extracted`, "Coverage checked", "Awaiting human review"); anything unmapped falls back to a readable form (underscores to spaces, first letter capitalised), never hidden and never an error. `formatUsd` renders `850000.00` as `$850,000` and shows cents only when they are non-zero; `formatDateTime` renders an ISO timestamp as a short date and time in the reader's locale, with the locale and time zone overridable so tests do not depend on the machine. Both return the raw string when the input does not parse. Stored values are never altered: the colour of a status badge is still chosen by the stored value, and the form still posts the stored claim type and a plain-number amount.

**The Claims page** (`pages/ClaimsPage.tsx`). Columns Claimant | Type | Amount | Status | Submitted | Actions: the amount as currency, right-aligned in tabular figures; type and status in plain words (`StatusBadge` gained an optional `label`; the other pages pass nothing and are unchanged); a new *Submitted* column from `created_at` (the API already orders `created_at DESC`, limit 50, so nothing changed there); the two actions side by side in one non-wrapping cell. The second action is **Strict re-run** everywhere it appears (the page, the Guide's *Try it*, the tests, the tooltip key `strictRerun`); while a claim has no finished run the button is disabled with `aria-disabled` and its tooltip opens with the reason. Cells are `px-2 py-1.5` with flush outer edges so the row fits the card: measured on Azure, the `main` is capped at 1024 px, the card's content is 942 px, and with `px-3` the row needed 979 px and spilled past the card.

**The form** (`components/ClaimForm.tsx`). Eight visible `<label htmlFor>` fields (Claimant name, Policy number, Loss date, Reported date, Jurisdiction, Reported amount (USD), Claim type, Description) in a two-column grid; options show labels and carry stored values; *Submit Claim* is a `Button`.

**Buttons** (`components/ui.tsx`). `primary` is solid blue (`bg-blue-700`, the link colour); `secondary` is a blue outline on white; `danger` red; disabled greyed; a `size="sm"` for table rows.

**Tooltips** (`components/Tooltip.tsx`, `copy/tooltips.ts`). The earlier tooltip was a native `title` on a wrapping span with an `aria-hidden` ⓘ: it showed on mouse hover only and was never announced. Now the ⓘ is a labelled button, a `role="tooltip"` element renders while the pointer is over the group or focus is inside it, and the wrapped control is `aria-describedby` it; callers are unchanged. The box sets its own wrapping (`whitespace-normal`; it inherited `nowrap` from the actions cell and ran off the page as one line), a 320 px maximum width, a dark background with white text, padding, shadow and `z-30` so it sits above the rows and the card. After it opens it measures itself in a layout effect and writes its placement to the element: `right: 0` when it would pass the right edge of the viewport, above its control when it would pass the bottom. The three texts say what the button does here first and name the production trigger second; *Submit Claim* opens with Dermot's wording, "Saves the claim; nothing is processed until you press Process."

**The application's title** (Dermot, at close-out). *Agentic Insurance Claims Processor* in the navigation bar (`App.tsx`) and the browser tab (`index.html`); `App.test.tsx` asserts the new name. The old title *Agentic Claims POC* also appeared as the first heading of `README.md` and `CLAUDE.md`, where it is the repository's name; those are unchanged, as the repository name does not change. It appeared nowhere else.

**Documents.** `CLAUDE.md`: status, the Azure image and revision, and a new standing instruction under *Commit protocol* (below). `docs/BACKLOG.md`: the Claims-page items under *Phase 8.7* marked done; Dermot's walkthrough notes for the run page and the claim page committed as they stand.

## Decisions as applied

D1 `StatusBadge` `label` prop; D2 the state-driven tooltip; D3 the status words as listed; D4 the disabled reason inside the tooltip; D5 version `0.10.1.1`; D6 the tooltip key renamed (to `strictRerun`, following the button's final name rather than the plan's `rerunStrictValidator`); D7 dates through `Intl.DateTimeFormat` in the reader's locale. The *Submit Claim* wording change applied verbatim. Three changes and one fix were made at Dermot's request before close-out, each with tests and no version change: the *Strict re-run* name; the blue primary and outline secondary buttons with the small size; the table's room (one-line badges, right-aligned amounts, side-by-side actions); the tooltip box and placement.

## Tests

Backend **527 passed, 0 failed, 18 skipped** (unchanged; nothing under `backend/` changed). `ruff` and `mypy` clean. Frontend **92 passed** (68 before): `labels.test.ts` (4), `format.test.ts` (5), `Tooltip.test.tsx` (6: absent at rest, hover, keyboard focus, the box's classes and default placement, the right flip, the above flip), `tooltips.test.ts` (3), `ClaimForm.test.tsx` (5, including that the form shows labels but posts `claim_type: 'storm_complex'` and `reported_amount: '1400000.00'`), `ClaimsPage.test.tsx` (5), `ui.test.tsx` (7), `guide.test.ts` and `App.test.tsx` updated. ESLint, `tsc -b` and `vite build` clean; Prettier clean on every file this prompt touched.

**Mutation proof (applied, observed, reverted).** `claimTypeLabel` made to return the stored value unchanged: five tests fail across three files (`labels.test.ts` the mapping and the fallback; `ClaimForm.test.tsx` labels shown but values posted; `ClaimsPage.test.tsx` the plain-words row and the disabled second action), 87 pass. Restored, 92 pass.

## Deployed verification, 10 November 2026, Dermot present

- `0bda446` (the build): CI green; *Deploy backend (Azure)* built `claims-backend:0bda446` and the Container App moved to revision `--0000029`; *Deploy frontend (Azure Static Web Apps)* green; Vercel and Render deployed automatically. Azure `/health` `0.10.1.1`.
- The six later commits changed only the frontend; CI and the frontend deploy were green on each that reached `main` green (`03d0748`, `94df9ce`, `b92286f`, `19332c3`, `6291f43`); the backend workflow found no backend difference and left revision 29 in place.
- Measured in the Azure page: the table is 942 px wide, the card's content width, with no overflow and no wrapped cell over 27 rows; the *Strict re-run* label present and *Re-process with v2* absent in both deployed bundles; the five tooltips (*Submit Claim*; *Process* and *Strict re-run* on the first and last visible rows) each 320 px wide, wrapped to three or four lines, wholly inside the viewport, the last row's two opened above their control and shown over the rows in a screenshot. The browser driven here has a 2560 px viewport that would not narrow, so the right-edge flip is covered by its test only.
- Dermot read and used the Claims page on the Azure frontend: *"The Claims page reads and works as intended."*

**Azure is deliberately left running** at the close: the repository's About link points at the Azure frontend. Postgres `Ready`, `minReplicas` 0.

## Findings and deviations from the plan

- **Two red commits on `main`, both from the same habit.** `b694554` carried one failing frontend test (`getByText('Water damage')` matched the form's option as well as the table cell) because the commit chain piped vitest's output through `grep | head`, which discarded its exit code; CI failed and deployed nothing; fixed in `94df9ce` eleven minutes later by scoping the assertion to the row. `0b3d830` failed CI's Lint step on a React hooks rule (a state update inside a layout effect) that a local `npm run lint | tail -1` had hidden; the deploy workflows were skipped; fixed in `6291f43` by writing the measured placement to the element instead of state, with ESLint run in full before the commit. Both are in the decision register (R-21, R-22) and produced the new standing instruction in `CLAUDE.md`: a test, lint or type-check run that gates a commit is never piped through `head`, `tail` or `grep`, and the commit is made only when the command itself exits with success.
- The tooltip key is `strictRerun`, not the plan's `rerunStrictValidator`: the button's name changed at Dermot's request before the close-out and the key followed it.
- `formatUsd` first printed `$85,000.5`; the tests caught it during the build and it now uses two formatters, one for whole dollars and one with two-digit cents.
- The plan predicted about 84 frontend tests; the build reached 89 and the tooltip box added three, 92.
- `Record<keyof ClaimSubmission, string>` for the field labels demanded a label for `scenario_tag`, which is not a field; a `FieldName` type excludes it.
- Nine frontend files this prompt did not touch fail `prettier --check` on `main`; CI does not run Prettier, so nothing is red, and they were left alone as out of scope. Worth a tidy-up commit, and a Prettier step in CI if the project wants the check enforced.
- The browser used for live checks reports a 2560 px viewport and ignores resize requests, so hover and narrow-width behaviour were checked by focusing the controls from script and measuring, not by pointer.

## Interface-stability events

None. No HTTP or SSE shape, stored value, database column or setting changed; the form posts the same `ClaimSubmission`. No new dependency.

## Suggestions (not in scope)

- The run-page and claim-page items Dermot recorded in `docs/BACKLOG.md` on 10 November are the next two iterations of Phase 8.7; the run page first, since a finished run opened later shows every card as *queued*.
- A Playwright run of the three scenarios against a deployed frontend (backlog, *Browser-driven end-to-end test*) would have caught the unwrapped tooltip and the table overflow before a person did.
- A Prettier check in CI, after the nine files above are formatted.
