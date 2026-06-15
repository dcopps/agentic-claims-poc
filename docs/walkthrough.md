# Demo Walkthrough Script (≈3 minutes)

The script the architect reads while screen-recording the live demo. Each scene
gives the URL/screen target, the actions to perform, and the lines to say. Times
are approximate; the whole path is ~3 minutes. The recorded video is kept outside
the repo (link shared for the interview).

**Before recording:** the deployed backend has been seeded and indexed; `/health`
reports `version=0.7.0`. Open the live Vercel URL.

---

## Opening (0:00–0:15)

**Screen:** the claims list at the live URL.

> "This is a multi-agent insurance claims processing prototype for a regulated
> specialty insurer. Everything you're seeing is live — a React front end on
> Vercel, a FastAPI backend on Render, Postgres on Neon. Let me walk a claim
> through it."

---

## Auto-approve scenario (0:15–0:30)

**Screen:** the submission form. **Action:** click **"Load demo claim →
Auto-approve ($85k water damage)"**, then **Submit Claim**. On the list, click
**Process** on the new claim.

> "I'll submit an $85,000 water-damage claim and process it. Four agents run —
> extract, validate coverage against the policy, estimate settlement, guardrail
> check — and the escalation policy auto-approves it. No rule fired."

**Screen:** the run lands on `settled`.

---

## Threshold escalation + live agent cards (0:30–1:15)

**Action:** load and submit **"Threshold escalation ($850k fire)"**; click
**Process**. You're navigated to the run-detail page with the live agent cards.

> "Now an $850,000 fire loss. Watch the agents complete in real time — this is
> Server-Sent Events streaming from the orchestrator. Doc-Parser, Validator,
> Adjuster, Guardrail."

**Action:** when the cards finish, **expand the Validator card**.

> "Each card expands to show exactly what ran — the system and user prompt the
> agent used, and its raw response, pulled straight from the audit log. This is
> the explainability story: nothing the model did is hidden."

**Screen:** the outcome is `awaiting_human` — settlement over the $250,000 ceiling.

---

## Guardrail escalation — the deterministic affordance (1:15–1:45)

**Action:** load and submit **"Guardrail escalation ($1.4M storm)"**; **Process**.

> "This $1.4M storm claim references an endorsement the policy doesn't contain.
> The Guardrail catches the hallucinated citation and escalates. For the demo
> this is deterministic — the Adjuster returns a fixture, and the audit log
> records `demo_fixture: true`, so the trail is honest about it. The guardrail's
> *detector* is the real thing; only the input is pinned."

**Screen:** `awaiting_human`, `guardrail_failed`.

---

## Audit viewer + chain verification (1:45–2:05)

**Action:** open the **Audit** nav link, paste/select the run's correlation_id,
click **"Verify chain (whole ledger)"**.

> "Every step is a row in a SHA-256 hash chain. One click verifies the *entire*
> ledger — not just this run — and locates the first break if anything were
> tampered. In production this is SQL Server Ledger Tables; here it's hand-rolled
> and does the same job."

**Screen:** green "Chain verified" badge.

---

## Human review (2:05–2:35)

**Action:** open the escalated claim's detail page; the **Human review** panel is
shown. Read the evidence, type a reviewer name, click **Approve**.

> "For an escalated claim, the reviewer sees the evidence — the cited policy
> clauses, the settlement reasoning, the guardrail flags — assembled from the
> audit log. I approve it, and that decision is written back as a `human` audit
> entry. The claim moves to settled."

**Screen:** status flips to `settled`.

---

## Agent test bench (2:35–2:50)

**Action:** open the **Agents** nav link; run the **Doc-Parser** panel on the
sample.

> "And a test bench — invoke any single agent on arbitrary input, out of band, to
> inspect its behaviour. These calls write no audit entry by design."

---

## Closing (2:50–3:05)

> "The architecture diagram, the Azure production target, the change-governance
> taxonomy, and the DORA third-party register are all in the repo, and every
> prompt that built this is archived in build order. Thanks for watching."
