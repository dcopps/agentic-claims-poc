# DORA Third-Party Register

Every external (ICT third-party) dependency the system relies on, with its role,
its substitution path, whether the substitution has been **exercised in the
prototype**, and the regulatory rationale under **DORA Article 28** (management of
ICT third-party risk — concentration risk, exit strategy, substitutability).

The honest summary up front: the **LLM Gateway substitution has been exercised**
across Anthropic and Mistral (the `v2_haiku_validator` variant swaps the Validator's
provider at run time, and the audit log records the actual provider). Every other
substitution is **design-level** in the prototype — the path is defined and the
production target named, but not exercised against a running alternative.

## Model providers

### Anthropic — Claude Sonnet (Orchestrator), Claude Haiku (Doc-Parser, Guardrail)

| | |
|---|---|
| **Role** | Frontier orchestration reasoning (Sonnet); fast extraction and the output guardrail (Haiku). |
| **Substitution path** | Reached only through the `LLMProvider` Gateway. Swap to a different vendor by changing the provider/model in settings or a variant — no agent code change. Production target: the same Claude models via **Azure AI Foundry** private endpoints. |
| **Exercised in prototype?** | **Yes (partial).** The `v2_haiku_validator` variant routes the Validator to Claude Haiku; the audit `llm_call.provider` records `anthropic` truthfully. Cross-vendor swap of the orchestrator/guardrail is config-level, not exercised. |
| **DORA Art. 28 rationale** | The Gateway is the documented exit/substitution seam. Concentration on one frontier vendor is mitigated by provider diversity (Mistral on the PII-sensitive path) and by the swap being a configuration change. |

### Mistral — Mistral Large (Validator, Adjuster)

| | |
|---|---|
| **Role** | Open-weight reasoning for the PII-sensitive coverage and settlement decisions; the Adjuster is the fine-tune target. |
| **Substitution path** | Via the Gateway. The `v2_haiku_validator` variant demonstrates swapping *off* Mistral for the Validator. Production: Mistral Large via Azure AI Foundry; the Adjuster gains a **LoRA adapter** trained on redacted historical claims, versioned in Blob Storage with blue/green deploy. |
| **Exercised in prototype?** | **Yes (partial).** The provider-swap variant proves the Validator can run off Mistral; the truthful provider audit is the evidence. |
| **DORA Art. 28 rationale** | Open-weight + tenant-hostable is the strongest substitutability posture — the model can be self-hosted if the vendor relationship ends. Fine-tuning keeps the differentiated capability inside the tenant. |

## Infrastructure providers

### Neon — managed Postgres + pgvector (claims of record, audit vault, vector index)

| | |
|---|---|
| **Role** | Single database hosting the system of record, the hash-chained audit log, and the pgvector index (`eu-central-1` / Frankfurt). |
| **Substitution path** | Migrations are plain Alembic SQL; `DATABASE_URL` points anywhere Postgres-compatible. Production: **Azure SQL Managed Instance** (with **Ledger Tables** taking over audit-chain integrity) for claims/audit, and **Azure AI Search** for the vector index. |
| **Exercised in prototype?** | **No** (design-level). The app already runs against either local Postgres or a Neon branch by URL, but not against SQL MI. |
| **DORA Art. 28 rationale** | Standard Postgres dialect and migration tooling keep the data tier portable; the audit-engine swap is the substantive production change and is documented as a transition. |

### Render — backend host · Vercel — frontend host

| | |
|---|---|
| **Role** | Commodity hosting for the FastAPI backend (Render) and the React SPA (Vercel). |
| **Substitution path** | Stateless container + static SPA; no provider lock-in beyond build config. Production: both move to **Azure Container Apps** inside the tenant VNet, behind **API Management + Entra ID**. |
| **Exercised in prototype?** | **No** (design-level). |
| **DORA Art. 28 rationale** | Deliberately commodity for iteration speed; the production move to tenant-owned Azure compute removes the third-party hosting dependency entirely (data never leaves the tenant). |

### Embedding model — `bge-small-en-v1.5` (sentence-transformers, local)

| | |
|---|---|
| **Role** | Embeds policy chunks at index time and claim narratives at query time (384-dim). |
| **Substitution path** | The embedding model is a **one-way door** — changing it requires re-indexing the entire corpus, because index and query vectors must come from the same model. Production: **text-embedding-3-large** via an Azure AI Foundry private endpoint, with a full re-index. |
| **Exercised in prototype?** | **No** (design-level). The model name and dimension are interlocked and pinned in settings precisely because the swap is a re-index event. |
| **DORA Art. 28 rationale** | The substitution cost (re-index) is documented; the one-way-door nature is the key risk to plan for in an exit. |

## Concentration-risk summary

| Provider | Concentration risk | Primary mitigation |
|---|---|---|
| Anthropic | Frontier orchestration | Provider diversity (Mistral) + Gateway swap |
| Mistral | PII-sensitive reasoning | Open-weight, tenant-hostable, fine-tunable |
| Neon | All persistent state | Portable Postgres + Alembic; SQL MI target |
| Render / Vercel | Hosting | Stateless; tenant-Azure target |
| bge-small | Retrieval quality | Documented re-index path to Foundry embeddings |

No single provider, if it failed tomorrow, would leave the system without a named
and (for the model tier) at least partially-exercised substitution path. That is
the DORA Article 28 posture the prototype is built to evidence.
