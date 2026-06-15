# Change Governance for AI Changes

How changes to the AI system are classified, approved, tested, and verified. The
prototype has no change-control machinery; this document describes the production
target — the taxonomy a regulated specialty insurer applies to *AI* changes
specifically, where "the model's behaviour is part of the contract" makes the
usual standard/normal/emergency distinctions sharper.

The Change Advisory Board (CAB) — here, the AI Change Control Board — owns the
classification. Every production change links to an Azure DevOps Work Item with a
risk rating, a rollback plan, and the approval evidence.

## Why AI changes need their own taxonomy

For conventional software, "what changed" is the diff. For an AI system, a
one-character prompt edit can change model *behaviour* across every claim, and a
provider swap can change it without any code diff at all. So the classification
keys off **whether model output behaviour changes at a contract level**, not off
lines of code.

## The taxonomy

| Class | Test (any one → at least this class) | Approval | Gate |
|---|---|---|---|
| **Standard** | No model swap; no structural prompt change (placeholders unchanged); no schema migration; no new API surface; no rule-name change. Pre-authorised. | Peer review | CI green (incl. eval set) → auto-deploy |
| **Normal** | Changes output behaviour at a contract level: a new variant, a new agent, a new prompt placeholder, a new escalation rule, an additive schema migration. | CAB review | Eval gate + CAB sign-off → staged deploy |
| **Emergency** | A live incident needs a fix faster than CAB cadence — typically a guardrail or escalation-policy change to mitigate harm in flight. | On-call lead (retroactive CAB) | Expedited deploy → post-deployment review within 24h |

The **eval gate** — a golden test set of historical claims with known outcomes —
is the boundary of a standard change: if the change moves an eval result, it is at
least Normal.

## Worked example — Standard: reword a prompt template

**Change.** Replace literal copy in `backend/app/prompts/user/validator_template.md`
with clearer phrasing. Placeholders (`{claim_narrative}`, `{retrieved_chunks}`)
unchanged; no model, schema, or rule change.

```diff
- Decide whether the policy covers the loss described in the narrative, citing only the retrieved chunks.
+ Using only the retrieved chunks as authority, decide whether the policy covers the loss described in the narrative.
```

- **Who approves:** one peer reviewer.
- **Tests:** prompt-loader golden-shape test; the full pytest suite; the eval set
  must not regress (no outcome flips on the golden claims).
- **Gate:** CI green → auto-deploy. Pre-authorised under the standard-change policy.
- **Post-deploy:** none beyond the standard `/health` + smoke check.

## Worked example — Normal: add a fine-tuned-model variant

**Change.** Register a `v3_long_form_validator` variant in
`backend/app/orchestrator/variants.yaml` that points the Validator at a
fine-tuned model. New contract-level behaviour → Normal.

```yaml
  v3_long_form_validator:
    description: "Validator on a fine-tuned long-form model."
    validator:
      model: "mistral-large-ft-claims-v3"
      provider: "mistral"
```

- **Who approves:** CAB (model owner + risk).
- **Tests:** variant-registry tests; an eval run of the new variant against the
  golden claim set with a documented acceptance threshold; a side-by-side
  comparison (the runs/compare API) of the new variant vs. the incumbent on a
  sample.
- **Gate:** eval acceptance + CAB sign-off → staged deploy (blue/green), then
  production.
- **Post-deploy:** monitor escalation-rate and confidence-distribution drift for
  the first N runs; the DORA register row for the model is updated.

## Worked example — Emergency: hotfix a guardrail regex after a live PII miss

**Change.** A specific phone-number format observed in a live claim slips past the
PII regex in `backend/app/agents/guardrail_rules.py`. Harm in flight (PII could
reach an auto-approval) → Emergency.

```diff
- ("phone_us", re.compile(r"\b\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
+ ("phone_us", re.compile(r"\b\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?:\s?x\d{1,5})?\b")),
```

- **Who approves:** the on-call AI lead authorises the expedited deploy; CAB review
  is retroactive.
- **Tests:** a *triggering* unit test that the new format is now flagged (asserting
  on the flag, per the project's guard-test standard); the guardrail suite; the
  eval set (must not regress on existing claims).
- **Gate:** expedited pipeline (build → test → deploy), CCB approval gate bypassed
  under the emergency policy with the bypass recorded.
- **Post-deploy:** post-deployment review within 24 hours — confirm the fix, scan
  recent runs for the missed format, and either ratify or roll back. The incident
  and the change link to the same Work Item.

## What the prototype has vs. what production adds

The prototype ships the *mechanisms* this taxonomy governs — `variants.yaml`,
`policy.yaml`, the externalised prompts, the guardrail rules, the migrations — but
none of the *control*: no CAB, no eval gate, no Work Item linkage. Adding that
governance overlay is one of the six dev→prod transitions (see
[`architecture-stack-reference.md`](architecture-stack-reference.md)) and is
referenced from the Azure pipeline in [`../infra/azure-devops-pipeline.yml`](../infra/azure-devops-pipeline.yml).
