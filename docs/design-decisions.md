# Design Decisions and Trade-offs

The decisions a reviewer is most likely to probe, with the reasoning and the
trade-off each one accepted. The README carries a one-line summary of each; this
is the full treatment.

## 1. A hand-rolled SHA-256 hash chain, not SQL Server Ledger Tables

**Decision.** The audit vault is an append-only table where each row stores its
own `row_hash` (SHA-256 of the canonicalised content) plus a `chain_hash` that
incorporates the previous row's `chain_hash`. A single advisory lock serialises
writers so concurrent appends cannot fork the chain.

**Why.** The prototype runs on Postgres (Neon), which has no Ledger Tables. The
goal is to demonstrate the *property* — tamper-evidence with a locatable break —
not to ship the production engine. The chain logic is ~100 lines and fully
tested, and the verifier walks the whole ledger and reports the first divergence.

**Trade-off.** Hand-rolled integrity is the application's responsibility, not the
database's. In production, **Azure SQL Managed Instance Ledger Tables** take over:
the engine guarantees the chain, and a daily digest is exported to Blob Storage
with an immutable policy. The application code that writes audit rows barely
changes. Chain verification, which is a UI button here, becomes a single
`sys.sp_verify_database_ledger` call.

## 2. An LLM Gateway mediating every model call

**Decision.** No agent calls a vendor SDK directly. Every call goes through a
thin `LLMProvider` interface (`complete(system=, user=, model=, …)`), with concrete
`AnthropicProvider` and `MistralProvider` implementations selected by a factory.

**Why.** The Gateway is the substitutability seam DORA Article 28 asks for: swapping
a provider is a configuration change, not an agent rewrite. It is also the single
place to add prompt logging, cost attribution, and PII redaction in production.

**Evidence it works.** The `v2_haiku_validator` replay variant swaps the Validator
from Mistral to Claude Haiku at run time, and the Validator's audit entry records
the *actual* provider (`self._provider.vendor`) — so the audit log itself proves
the substitution happened. An entry that lied about the provider would undermine
exactly the substitutability story the prototype exists to tell.

**Trade-off.** The interface is the lowest common denominator across vendors;
provider-specific features (Anthropic's native tool use, Mistral's JSON mode
nuances) are normalised away. Acceptable for this workload.

## 3. Mistral *and* Claude — a tiered, diverse model strategy

**Decision.** Sonnet for orchestration reasoning; Haiku for fast extraction and the
output guardrail; Mistral Large for the coverage (Validator) and settlement
(Adjuster) decisions.

**Why.** Three reasons stacked: **cost/capability tiering** (don't pay frontier
prices for field extraction), **provider diversity** (no single-vendor dependency),
and **tenant-hostability + fine-tuning** for the PII-sensitive open-weight path —
the Adjuster gets a LoRA adapter on redacted historical claims in production.

**Trade-off.** Two SDKs, two key sets, two failure modes. The Gateway absorbs most
of that; the operational surface is wider than a single-vendor design.

## 4. An in-process event bus, not a message broker

**Decision.** The decoupling (claim persisted → event → pipeline) is real, but the
event transport is an in-process `asyncio.Queue` fan-out keyed by correlation_id,
not a broker.

**Why.** A single-process prototype doesn't need Redis or Service Bus to
demonstrate decoupling and SSE progress streaming. The orchestrator stays
asyncio-agnostic (it emits via a plain callback); all the async machinery lives at
the API edge.

**Trade-off.** No durability, no cross-process delivery, best-effort late-subscriber
buffering. Production uses **Azure Service Bus + Durable Functions** — which also
unlocks the long human-review wait without holding application state, the real
reason the production design is event-driven end-to-end.

## 5. A demo fixture for the guardrail scenario

**Decision.** The seeded $1.4M guardrail claim returns a deterministic Adjuster
fixture (a planted "Endorsement Coastal Surge Rider" the policy doesn't carry)
instead of calling the model, so the Guardrail's hallucinated-citation **regex**
catches it every time.

**Why.** A demo must reproduce. A hallucinated endorsement is exactly the kind of
non-deterministic model output you cannot rely on to appear on cue. The fixture
removes the luck without faking the *mechanism*: the Guardrail's real
deterministic detector does the catching.

**Trade-off — and how it's mitigated.** A "demo affordance" that silently faked an
LLM call would be precisely the hidden behaviour the audit vault exists to prevent.
So the fixture is **auditable**: the Adjuster's audit payload records
`demo_fixture: true` and the `llm_call` block honestly states no model was called.
The demo is deterministic *and* the trail tells the truth. The branch is fail-closed
— a missing or out-of-range fixture raises, never silently degrading to a live call.

## 6. The audit log is the trusted record

**Decision.** Wherever a UI value and an audit value could disagree (the
denormalised `claims.status` vs. the audit entries; the reconstructed
`PipelineResult` vs. the raw payloads), the **audit log is authoritative**. Runs are
reconstructed *purely by reading* the audit log; the runs repository writes nothing.

**Why.** This is what makes replay non-destructive (a re-run is just a new chain of
entries under a new correlation_id) and what makes the human-review evidence
trustworthy (the cited policy-clause *text* lives in the validator's audit payload,
not in the reconstructed result). Every additive interface extension since Phase 4
was chosen to preserve this property — full Adjuster reasoning so reconstruction is
verbatim; truthful provider/model so substitution is provable; `demo_fixture` so the
demo affordance is visible. The locked list is in `CLAUDE.md`.

**Trade-off.** Denormalised conveniences (the `status` column) can lag the audit
truth on partial failures; status writes are deliberately non-fatal, and the audit
log is the reconciliation source.
