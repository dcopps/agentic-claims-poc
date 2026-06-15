# Phase 7 — Live Scenario Verification

Evidence that the three scripted demo scenarios reproduce end-to-end against the
deployed backend. Regenerate with:

```bash
uv run python scripts/verify-demo-scenarios.py --backend "$BACKEND_URL"
```

The script submits each claim, runs the pipeline synchronously, and asserts the
outcome below. For the audit trail, paste the script's output and (optionally) a
`curl` of the reconstructed run, or a screenshot of the live UI's final state, into
each section's **Evidence** block.

> **Status:** the architect runs the script against the deployed backend after the
> Render redeploy and fills the Evidence blocks. The expected outcomes are below;
> the placeholders are filled with the live run's `correlation_id` and key fields.

---

## Scenario 1 — Auto-approve ($85k water damage)

**Input** (`POST /api/claims`):

```json
{ "claim_type": "water_damage", "reported_amount": "85000.00",
  "jurisdiction": "United Kingdom", "scenario_tag": "auto_approve", "…": "…" }
```

**Expected `PipelineResult`:** `status = "settled"`, `escalation_decision.escalate = false`,
`fired_rules = []`. Guardrail passed; settlement within the water_damage/moderate
range and under the $250,000 ceiling.

**Evidence:**

```
<paste verify-demo-scenarios.py output for auto_approve here>
<optional: curl "$BACKEND_URL/api/runs/<correlation_id>" | jq '.status, .escalation_decision'>
```

---

## Scenario 2 — Threshold escalation ($850k fire)

**Input:**

```json
{ "claim_type": "fire", "reported_amount": "850000.00",
  "jurisdiction": "United States — New York", "scenario_tag": "threshold_escalation", "…": "…" }
```

**Expected `PipelineResult`:** `status = "awaiting_human"`, `escalate = true`,
`fired_rules` includes `settlement_over_ceiling` (settlement > $250,000). Guardrail
passed — the escalation is the threshold, not a safety failure. Reproduces live
because any in-range Adjuster value for fire/severe (`[500000, 1500000]`) exceeds
the ceiling.

**Evidence:**

```
<paste verify-demo-scenarios.py output for threshold_escalation here>
```

---

## Scenario 3 — Guardrail escalation ($1.4M storm)

**Input:**

```json
{ "claim_type": "storm_complex", "reported_amount": "1400000.00",
  "jurisdiction": "Bermuda", "scenario_tag": "guardrail_escalation", "…": "…" }
```

**Expected `PipelineResult`:** `status = "awaiting_human"`, `fired_rules` includes
`guardrail_failed`. **Deterministic:** the `guardrail_escalation` tag drives the
Adjuster demo fixture (`backend/data/demo_fixtures/guardrail_adjuster.json`), whose
reasoning cites "Endorsement Coastal Surge Rider" — an endorsement absent from the
policy — which the Guardrail's hallucinated-citation regex catches every time. The
Adjuster's `settlement_estimate` audit entry records `demo_fixture: true` and
`llm_call.provider = "demo_fixture"`, so the trail is truthful about the source.

**Evidence:**

```
<paste verify-demo-scenarios.py output for guardrail_escalation here>
<optional: curl "$BACKEND_URL/api/audit?correlation_id=<cid>" | jq '.[] | select(.step=="settlement_estimate") | .payload.demo_fixture'>
```

---

## Result

| Scenario | Expected | Reproduced live? |
|---|---|---|
| Auto-approve | `settled`, no rules | _fill from script_ |
| Threshold escalation | `awaiting_human`, `settlement_over_ceiling` | _fill from script_ |
| Guardrail escalation | `awaiting_human`, `guardrail_failed` (deterministic) | _fill from script_ |
