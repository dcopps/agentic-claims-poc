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

## Observed in the prototype — a third-party model changed behaviour without a version change

**26 October 2026.** The Guardrail, pinned to `claude-haiku-4-5-20251001` at
temperature 0, failed the $85k Harborline scenario that it passed on 1 October.
Replaying pass one's recorded prompt, byte for byte, failed today too. No commit,
prompt, setting or model id had changed. The change came from outside the repository.
None of the three classes above would have caught it, because there was no change
request to classify.

**What detected it:** the audit trail. Every `llm_call` records the literal prompt
sent, `requested_model` and the responding `model`, so the verdict could be
replayed and the deployment ruled out in one session (Phase 9.2 build-log entry,
*Recorded exception*).

**What production adds:** the eval gate runs **on a schedule against the live
model**, not only when a change is raised. A moved result with no change on our side
opens a vendor-change incident against the provider entry in the
[DORA register](dora-third-party-register.md). The fix that follows, here a
Guardrail prompt change, is classified as usual (at least *Normal*).

**The control response (Phase 9.2.1, 28 October 2026).** Classified *Normal*: the
placeholders did not change, which alone would make it Standard, but the change
moves an eval result (the auto-approve scenario from `awaiting_human` back to
`settled`), which is the taxonomy's boundary. The Guardrail's definition of a
citation was narrowed to a provision named by title or number, with coverage
explicitly left to the Validator; the change was proven by replaying the recorded
prompts through the new system prompt against the live model, before and after;
and the recorded runs were kept as a gated regression fixture that is run before
each demo — the prototype's stand-in for the scheduled live-model eval. Record in
the Phase 9.2.1 entry of the [build log](build-log.md).

**Outcome (29 October 2026).** Partially effective. The change shipped to both
stacks as `0.9.1.1`; the scenario settled through the Azure frontend but escalated
again through the verification script against Render, on an Adjuster text outside
the fixture corpus. The eval did its job — it recorded the miss — and the lesson is
that a prompt is not a control one can rely on against vendor drift: the verdict
stayed sensitive to wording. Phase 9.2.2 moves the control into code (an LLM
citation flag counts only when the phrase it quotes is present in the reasoning
and has the shape of a named provision), which is a *Normal* change with the same
record. The closed phase is *partially verified*, not *verified*.

**The control response completed (Phase 9.2.2, 30 October 2026).** Classified
*Normal* again (it moves the same eval result). The model keeps its job of
*finding* a suspicious reference and loses the authority to *decide* that it
counts: a `hallucinated_citation` flag from the LLM check must quote the words it
objects to, and code counts it only when the quote is present in the Adjuster's
reasoning and the reasoning's own span has the shape of a named provision by the
rule engine's test. Refused claims are recorded in the audit (`llm_flags_discarded`,
with the reason) and logged, so the model's claim and the code's refusal sit side
by side on every run. Proven by the seven-fixture replay before and after (all
green after; the Coral Bay invented endorsement still counts), a mutation proof,
and the deployed runs recorded in the Phase 9.2.2 entry of the
[build log](build-log.md). A deterministic check in code is the first control in
this sequence that vendor drift cannot move.

## What the prototype has vs. what production adds

The prototype ships the *mechanisms* this taxonomy governs — `variants.yaml`,
`policy.yaml`, the externalised prompts, the guardrail rules, the migrations — but
none of the *control*: no CAB, no eval gate, no Work Item linkage. Adding that
governance overlay is one of the six dev→prod transitions (see
[`architecture-stack-reference.md`](architecture-stack-reference.md)) and is
referenced from the Azure pipeline in [`../infra/azure-devops-pipeline.yml`](../infra/azure-devops-pipeline.yml).
