# Diagrams

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({
    startOnLoad: true,
    theme: 'default',
    securityLevel: 'loose',
    sequence: { useMaxWidth: false },
    flowchart: { useMaxWidth: false },
  });
</script>

<style>
  /* Widen the content area on the diagrams page so the diagrams have room. */
  .wrapper { max-width: min(1400px, 95vw); }
  /* Keep each rendered diagram inside the viewport so more is visible before
     scrolling. Aspect ratio is preserved; open in mermaid.live for full size. */
  pre.mermaid svg { max-height: 65vh; max-width: 100%; height: auto; }
</style>

## Architecture diagram (interactive)

The centrepiece of the design is the interactive **[Architecture Diagram](Architecture_Diagram.html)** — view it via GitHub Pages to render it in the browser. From the GitHub repo view this link shows HTML source only; the Pages-served version is what's meant for reading.

## 1 — Headline agent flow

The "what this is" sequence diagram — agents, audit vault, and the four-tier model strategy.

<a href="https://mermaid.live/edit#pako:eNqlVU1v2zgQ_SsDnVRshBTd9UWHFqr8WTiRYXndQ1wUjDiWuKFIlyLduEX_-w4txVYbI11gdRAo8c3jvOHj8HtQaI5BHDT4xaEqcChYaVi9UUAPc1YrV9-jab93zFhRiB1TFlJgDaSSidp_hX83aF49R2UelZmiwsYaZrWBu7HRygo0sY92HCHXSqH99Dx46IOHuogWzBA93OU1k_IUN2XiwV0IW_uwNZOCtwtmO1TRRxRlZWO4ET4RCXNmSrwQnPjghP_jGosvxsIfMNfL5ALFxFNMHDPcMCH_a9ZTHzV1VE2CKC4v1Tw5SkscF6SSOWnhbsqaKkorJhRymCMv0RB5G5pGb99mMeTuvha22ywIZzUrsble4aPtNiwjXLKOSU8JuaX1INXGoGRWaPV5NnziM1hYMOV9-Oav11fw9OpIbrVFML5QoLcwjGE1Gy0hgvwmmc8hHLPGwuiR6ld41t7KBO3-w5BZ1k4Meyl1s6TvQ57dwg1axn8CksYlWmdUQ-kbV9CQwGcyVPy5hDc--z8H9BoMLkpYnyRki9Ft9HE0m0xXEK5Q-a2IYDGbQc622JNCIWs0YnugAu7RUJ0hXCbkh5L2h_QvtBTFAWaK42MXtu4J7abTyqmHxksyAvekJMy1MwXCnDaZOHuRPeWnFVOttsLUyP-P-OSy-DFlEFnnvaZVa6imbyLaysZSRyCqHK2VWKOy7XzSF2rI0aqk3FmjlR8tmK3OuP6GnmjoV6FrGvGjL19Q91t3Tn51Z-bsztnzoe1pImxaYfFwbgodOHwv6DBeH31wTWdWSkeiWM_dk57kcz8gh3BR2DOkp3bBmgaoZ40J-ILAweA3ArOTwPEyuz0Ow1FTsPZI-4RE0dNI8GS3kwfoYTozRrAiVuoqXW9a4l7g13fn2GkMY8lK2FLaRGL0njpkmFf6K4z2gvs7hVplKuyR9skt015pWuKhKAkjIRclFZFO8BnYptcyTwydvgve9qmksS-D2IqilRB1La_1EP-52ZGV6Yr4hl3ThJGy5uC7Y-0su5e-UTcVZRtcBTWamglOt-R3z7EJbEWO3AQxDTlufSPeBBv1g6D-xswPqghiakR4FbgdufXpUm1__vgXbqBeaQ" target="_blank" rel="noopener noreferrer"><strong>→ Open in mermaid.live (full-size, zoomable)</strong></a>

<div style="overflow-x: auto;">
<pre class="mermaid">
sequenceDiagram
    autonumber
    participant C as Claimant (User)
    participant O as Orchestrator [Frontier: Claude Sonnet]
    participant D as Doc-Parser [Small: Claude Haiku]
    participant V as Validator [Open-Weight: Mistral Large]
    participant A as Adjuster [Open-Weight: Mistral Large + LoRA]
    participant G as Guardrail [Small: Claude Haiku]
    participant H as Human Handler
    participant AV as Audit Vault [Hash-Chained Ledger]

    C->>O: Submits Claim (Images/Text)
    O->>AV: Log Start Correlation_ID

    rect rgb(240, 240, 240)
    Note right of D: TIER - SMALL (Fast Extraction)
    O->>D: Extract Data
    D->>AV: Log Extracted JSON Metadata
    D->>O: Returns Structured Data
    end

    rect rgb(220, 235, 255)
    Note right of V: TIER - OPEN-WEIGHT (Tenant - PII Safe)
    O->>V: Verify Coverage (RAG against Policy Index)
    V->>AV: Log Policy Chunks Retrieved (Source Lineage)
    V->>O: Returns Coverage Confirmed
    end

    rect rgb(220, 235, 255)
    Note right of A: TIER - OPEN-WEIGHT (Fine-tuned on Claims)
    O->>A: Estimate Settlement
    A->>AV: Log Pricing Reasoning Path
    A->>O: Returns Settlement Recommendation
    end

    rect rgb(240, 240, 240)
    Note right of G: TIER - SMALL (Output Guardrail)
    O->>G: Check Adjuster Output (Bias / PII / Hallucination)
    G->>AV: Log Guardrail Verdict
    G->>O: Returns Pass or Fail
    end

    rect rgb(255, 240, 240)
    Note right of O: TIER - FRONTIER (Escalation Logic)
    O->>O: Apply Escalation Policy - Trigger Human Review?
    O->>H: Flag for Approval (Show Evidence + Citations)
    H->>AV: Log Human Digital Signature
    H->>O: Approval Granted
    end

    O->>C: Notification - Claim Settled
    O->>AV: Finalize Ledger Entry (Immutable Hash)
</pre>
</div>

## 2 — RAG zoom

A zoom-in showing the RAG mechanics inside the Validator step — embedding, similarity search, augmented prompt, audit.

<a href="https://mermaid.live/edit#pako:eNqNVF1v2jAU_StXeQIVUAvlJQ-V-sGmTlA62NgDTJOxL4m1xM5shzaq-t93HQdBB6vKQyD4nHvPuR9-ibgWGMWRxT8lKo53kiWG5SsF9GGl06rM12jCe8GMk1wWTDmYArMwNTxF6wxz-gRk4SELlknhz2E5LVB1f6BMUhfDRHpeBmNmEvx5TB5NPHtEyYWQKoEJ6cxguU6wa3OWZScoi7ubOiNyn-5eCXyGZZFs6_cT-PG4zuG_5mi2kqOF5SddKmGqE_Dr2s91KSSlYmXmViqAHrRD0Fs0JLrjVcTwOBt1b77fj--gpRV29WbThi486kzyCoTmZY4Ukael-o0CpHLap_KlL1LbgxHjaTgFrCtAoHXla1JDGVyc9y-7oTUQ_PUa3xYsPeugoSCZVomVApt4Dp9dD2a4MWhTgmmVVfCUooIiqOMpUwna3s7dtHt1tYgpupGbCm69T5YgtHjGZA6KGeq-3GJ7hzckA0yybvWHww70h-f0GJy3D0pl_ASA3gCFnX8bPcIF1eYzKgpMpzSHpmpMBdKCFIwmcRgG-CdvgIwmQeXXAzK0fJUgVMk2AlCJY6EDr_GyVjt8V2ifhM7QGYlbOsUMt2zXRrvXWk_ArbZSIViZy4wZ6SqwyGhdoOV0AYMmDUGD8MG-_D4YnL1hcuqofcdArX3wAQOD2gCzWoWBDcU8O7YQw00pM0FXQOJHlepeGJ0Xbtf3HaW959AekW1azbe7DU_SpUdxAo0oIdmX-fQBuJeEokPGvELa-g5wSZxfh_L-38GPjNolFWCsE2BKEN2VRu0NXBPInzUtME2jSVBoQKfR7gXaQiuLe-409oNB4ex-RW612kiTozgQHnWiHE3OpKBL98UfrCKXYo6rKKafAjf1zRKt1CtB_QU8rxSPYmdK7ERlQVfp7o4Of77-BSp64Fg" target="_blank" rel="noopener noreferrer"><strong>→ Open in mermaid.live (full-size, zoomable)</strong></a>

<div style="overflow-x: auto;">
<pre class="mermaid">
sequenceDiagram
    autonumber
    participant O as Orchestrator
    participant V as Validator [Open-Weight: Mistral Large]
    participant EM as Embedding Model [bge-small]
    participant VDB as Vector Index [pgvector]
    participant LLM as LLM Services [Foundry]
    participant AV as Audit Vault

    Note over EM, VDB: PRE-BUILD (one-off) - Policy document chunked into paragraphs. Each chunk embedded by EM into a 1024-number vector. Vectors stored in VDB alongside chunk text. Refreshed only when policy changes.

    O->>V: Verify Coverage (claim narrative)

    rect rgb(255, 250, 230)
    Note right of V: STEP 1 - Generate query vector
    V->>EM: Embed claim narrative
    EM->>V: Query vector (1024 numbers)
    end

    rect rgb(230, 245, 255)
    Note right of V: STEP 2 - Retrieve relevant chunks
    V->>VDB: Cosine similarity search (top 3)
    VDB->>V: 3 policy chunks + similarity scores
    end

    rect rgb(245, 235, 255)
    Note right of V: STEP 3 - Reason over claim + chunks
    V->>V: Build augmented prompt (claim + chunks)
    V->>LLM: Call Mistral Large with augmented prompt
    LLM->>V: JSON covered, reasoning, cited_chunks
    end

    rect rgb(230, 250, 230)
    Note right of V: STEP 4 - Log and return
    V->>AV: Log chunks retrieved, scores, prompt, response
    V->>O: Returns Coverage Confirmed
    end
</pre>
</div>

## 3 — Decoupling event flow

The lifecycle of a claim from submission through processing, human review, and replay.

<a href="https://mermaid.live/edit#pako:eNqNVl1v2koQ_SsjP4FqooSE-4DUSkBIqRTFlFy1uhIv690BtrG9vvsBpVX_-53dNSkY2l4ejO2d8c45c-bY3xOuBCbDxOC_DiuO95KtNSuXFdCPOasqV-ao43XNtJVc1qyyMAFmYFIwWdLVheVs8RpgQK1ggVxpAZ2Hp-yxex4_Hfvw6RbpfOzMeUDm1zPNN2isZlZp6IzWPnouayxkhRceOvM5M0cVwoxVoriEY_TJB42ckBY-MVcQlhikkVvQ67zTv71OoT_wh9vrZpcnZRHUFjVMUo91CPPZ6HkKN9CDZ5eX0hipKuiYfcU3WlXKmRRWzNgmf9J79y6khWAL3PMEHSJzjQbegMWvr6HZ4hD8Hisk7BhphQ_3cNO_vRucxA1hoqqV1CWzvoIeLJMYHUI9KpRbFMskZmElzgEPBoT1bvALwNkihewAuE87xK5ZLddr1MTlB6ibnlzBXCvheFPKM-qt5OgbDBiSVlqVYDd4LhSzNxbL8ACr7L7GAIWuOJpGV8sEcmdJolfHDEzHQ5h6TkPMosHb7Nc54qJBNh1TEuH5O9b_WntczeLiT-aV1lhEbon_4-elsHAVXF_fdH9DbdDSXRDU4IzaLCU5Hpi9JcBR4YeKQLvKXBGLCDNkItwScV5hRQOxckUBLKQItEwWVycY7hXvzZk2qFNSeiGFnyLaUXxxRDWdvXdMC015gF-RO3tEgS_rUa09i3oPFF6Dq4RXwykfDQN_1FZk4RIBswP-O8IfZ1fjVuIOOrsNVoCGM9oPRbclrtE3pxHunWZ5gfDgqrBgoCZNSmPNTxqNpfy2skZ1ramGtqY8eCrpo0OHYJl5abWcShPeN1Pg0gYazBkqyp8pR5NBPRJsT5UwQ32cn9QDxtFwbGn6c-TMGQxjsVP6ZVWoHXG59qHSgIgIm_pmsbexelaAkeuK_t6QMNZUUHPDEjW_6Ukc9cEvRTk59GRAVGXOclVSaVpaSw3JGX8Bq84nmBz31FcPfEbjQ2sLLKNYufR2mQYmyBveggmr4lSAD5KgyW8ItOInlXJJjGSapbOh6RtmNt2WGxIQuZI8KvTUCw-bJH-a10E8nFEzHR8P7F9EzmI6fxz9Q0PIZGVsaKFhRFbw95ZgS3rzFkB9K1W4Ex2KNJIzyzd0Sd37ovK2UBfYqxsX3Em7gW0_Pqmt3LavaawLtm_JN9aw7Xcvu93T9PP_cbzj9INTRHto1qHTGAPBRTIgMuQzMn3iWBEg73JAXyN6H5pqaMB6-b7n_18blaRJifSOk4K-Xb7728uEyC5pfod0KnAVJEed_UGh_jvmmd7EydBqh2niavK-w6dOvPnjP7It4EE" target="_blank" rel="noopener noreferrer"><strong>→ Open in mermaid.live (full-size, zoomable)</strong></a>

<div style="overflow-x: auto;">
<pre class="mermaid">
sequenceDiagram
    autonumber
    participant C as Claimant
    participant COR as Claims of Record (FNOL)
    participant EB as Event Bus
    participant O as Orchestrator (Agent Pipeline)
    participant H as Human Handler
    participant AV as Audit Vault

    rect rgb(230, 250, 230)
    Note over C, COR: PHASE 1 - Submission (synchronous, fast)
    C->>COR: Submit claim (images + text)
    COR->>COR: Generate Claim ID 12345
    COR->>C: Confirmation - "Claim 12345 received"
    end

    rect rgb(255, 245, 230)
    Note over COR, O: PHASE 2 - Event triggers AI pipeline. Production - Service Bus event from the Claims of Record system. Prototype - "Process Claim" button.
    COR->>EB: Emit ClaimReceived event (Claim 12345)
    EB->>O: Trigger pipeline
    O->>O: Generate Correlation ID (Claim 12345, Run 001)
    end

    rect rgb(230, 240, 255)
    Note over O, AV: PHASE 3 - Agent pipeline runs. See Headline diagram for full agent detail.
    O->>O: Doc-Parser, Validator, Adjuster, Guardrail execute
    O->>AV: Log every step under Correlation ID Run 001
    end

    rect rgb(255, 240, 240)
    Note over O, H: PHASE 4 - Human review (when escalated). Production - Azure Durable Functions persists pipeline state. Prototype - "Approve" button.
    O->>H: Queue task (Claim 12345, evidence, citations)
    Note over H: Hours or days pass. Pipeline state survives because the workflow engine is durable.
    H->>O: Approval signal + digital signature
    end

    rect rgb(245, 235, 255)
    Note over O, C: PHASE 5 - Outcome written back to Claims of Record and Audit Vault
    O->>COR: Settlement decision, status = settled
    O->>AV: Finalize ledger entry (immutable hash)
    COR->>C: Notification "Claim 12345 settled"
    end

    rect rgb(230, 250, 250)
    Note over EB, AV: PHASE 6 - REPLAY against the same claim. Production - model promotion event or batch eval job. Prototype - "Re-process with v2 model" button.
    EB->>O: Trigger replay (Claim 12345, model v2)
    O->>O: Generate NEW Correlation ID (Claim 12345, Run 002)
    O->>AV: Log under Run 002 (Run 001 preserved)
    Note over AV: Both runs queryable side-by-side
    end
</pre>
</div>

## 4 — Production architecture

The Azure topology view — trust boundary, components, PrivateLink to Foundry.

<a href="https://mermaid.live/edit#pako:eNqNVktv20YQ_isDnhog8qU3HwrQklwLkSxVYhygVA5LckQuTO6y-5CtxvnvnX1QsSkHKQ_ScN47M98svyWlrDC5Tg6tfCobpgxkN3sB9ExbxjsmTD4QMIEvWIBUsJIFb_Fr0JuLmgtElQ8EFzVkyLoov2Oiakl8Z8nJ8EayINW2qBXrGzAoXIx8ut5u1ts0m0P69-ftHLL5fXqfUez79Ta7g_nn7Xozj67dk24Wqzz91yp0JKyYYDV2SK6euGkoO6MYLGaQWtOco76JzPpeQ572fctLZrgUkHGfIbx6tshKk_tfuFVSULoVkOqUSEbHVkAO9MjolmlDSeXxH25Y-fh_7GZWsaLFeKz4BrdWlC49DV-kenQNi7UfWf_JDD6xU75crgaayrdR8sgrF6_QVBLv6ZUhpfVucSpmGOQz9_tOVaZym_8Wstz9tYTVggL5cdEgD1SzUqrqw8gmtRU3F1aeCw_MtgaWWNWUaOZOrcfmD1gaqfTgIF3ADpkqG3dESR08RQ1YiAqfx9aLrrMU_KaVBexIi2aFDD3X1zikMeM1avPh5-W5sTo2Z4fqyEt0HJgf3di5JhfSd-W9YeNpWaJ2A7eASLrm8CN1ivpZ9ZILo2Et2tMo9xUhtd3M81tpRaVOF0ZwoFPvpBBoCGb80cKKu1a3Iz_zrsCK_Pj_yqH1XU8Gn80EB53J75OWqRp_XhM3lAWKssnnzxTX-Y2jcJa8X5K-ZYYCdpBvBoqWBKx7VB6OY3R4SOcDsEfCTw_5JzyFQbqon-DU8ti4-OZDEQRpXDSvGzMOtmSiPliN-UD42jhorQtNvWe0CbkZt2qGx3U_jEh4gQ3vsSW0ah9y2pA_jBDR46qOynsuVaenrbQV5CteKqnlwUBgTGBtjSZ8Q6aspiF0M8LU67zi2CzE4TxBfqLo5AdU1B6HhFSYRsmel8PswHlKvl6k9eNimPzxcpdlm92LX8dB6ignCasz8ML-dMy4EgN72I9OQCslepdb7xg7bkIoKhbyI1aADmgvDnNB1YHPqRrFa7c5-ljql2F3BrVhkbowcTFeCuJ-uRT41XDJPud7XrXEjFC9FETsBUHUgslVBOCSi8crV5xzq-IVG6x-rRjW1-SqYrw9QeXXmNPzC26U-9U_Fi2CYdq7OoP0za3tkx6Jzq_kg-5OuldoTAg8grXO0ZuSD98E3k8AQkwjgIJSxb6VJ-0sw-wkH5MOVcd4RZ8l35z2PjENXen75JrICg8O2_tkL76TKrNG7k6iTK6NsvgxsT3dWDjjjADTBeb3_wAhgdKN" target="_blank" rel="noopener noreferrer"><strong>→ Open in mermaid.live (full-size, zoomable)</strong></a>

<div style="overflow-x: auto;">
<pre class="mermaid">
flowchart TB
    Claimant[Claimant - Web or Mobile]
    Engineer[Engineering Team]
    Handler[Human Handler]

    subgraph tenant [CORPORATE AZURE TENANT - NORTH EUROPE]
        APIM[Azure API Management with Entra ID Auth]

        subgraph apps [Application Tier]
            React[React Frontend on Container Apps]
            FastAPI[FastAPI Backend on Container Apps]
            Durable[Azure Durable Functions Workflow Engine]
            Gateway[LLM Gateway - Provider Abstraction]
        end

        subgraph data [Data Tier]
            CoR[(Azure SQL MI - Claims of Record)]
            Audit[(Azure SQL MI - Audit Vault Ledger Tables)]
            Vectors[(Azure AI Search - Policy Vector Index)]
            Immut[(Blob Storage - Immutable Audit Digest)]
        end

        Bus[Azure Service Bus Event Backbone]

        subgraph aiAccess [AI Access - Private Endpoints Only]
            ModelPE[Foundry Private Endpoint for Sonnet Haiku Mistral]
            EmbedPE[Embedding Private Endpoint for text-embedding-3-large]
        end

        Workbench[Existing Claims Workbench]

        subgraph platform [Platform and Operations]
            Entra[Entra ID]
            KV[Key Vault]
            Monitor[Azure Monitor and App Insights]
            Langfuse[Langfuse for LLM Observability]
            DevOps[Azure DevOps Pipelines and Change Records]
        end
    end

    subgraph msCloud [Microsoft Cloud - Outside Trust Boundary]
        FoundryInf[Foundry Model Inference - Anthropic Mistral Embedding]
    end

    Claimant -->|HTTPS| APIM
    APIM --> React
    React --> FastAPI
    FastAPI --> CoR
    CoR -->|emit ClaimReceived event| Bus
    Bus -->|trigger pipeline| Durable
    Durable --> Gateway
    Durable --> Vectors
    Durable --> Audit
    Durable --> CoR
    Gateway --> ModelPE
    Gateway --> EmbedPE
    ModelPE -.PrivateLink.-> FoundryInf
    EmbedPE -.PrivateLink.-> FoundryInf
    Audit -.daily digest.-> Immut
    Durable -.queue task.-> Workbench
    Handler --> Workbench
    Workbench -.approval signal.-> Durable
    Engineer --> DevOps
    DevOps -.deploys.-> APIM
</pre>
</div>

## Mermaid sources

All four diagrams are also available as raw Mermaid source files in this directory: `1-headline-agent-flow.mmd`, `2-rag-zoom.mmd`, `3-decoupling-event-flow.mmd`, `4-production-architecture.mmd`. Render locally with [mermaid.live](https://mermaid.live), the VS Code Mermaid extension, or any Mermaid-aware tool.
