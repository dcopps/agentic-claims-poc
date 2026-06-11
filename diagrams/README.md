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

## Architecture diagram (interactive)

The centrepiece of the design is the interactive **[Architecture Diagram](Architecture_Diagram.html)** — view it via GitHub Pages to render it in the browser. From the GitHub repo view this link shows HTML source only; the Pages-served version is what's meant for reading.

## Headline agent flow

The "what this is" sequence diagram — agents, audit vault, and the four-tier model strategy.

The diagram below renders at natural width — scroll horizontally to see it all, or open it full-screen in mermaid.live for zoom and pan:
**[→ Open headline diagram in mermaid.live](https://mermaid.live/edit#pako:eNqlVU1v2zgQ_SsDnVRshBTd9UWHFqr8WTiRYXndQ1wUjDiWuKFIlyLduEX_-w4txVYbI11gdRAo8c3jvOHj8HtQaI5BHDT4xaEqcChYaVi9UUAPc1YrV9-jab93zFhRiB1TFlJgDaSSidp_hX83aF49R2UelZmiwsYaZrWBu7HRygo0sY92HCHXSqH99Dx46IOHuogWzBA93OU1k_IUN2XiwV0IW_uwNZOCtwtmO1TRRxRlZWO4ET4RCXNmSrwQnPjghP_jGosvxsIfMNfL5ALFxFNMHDPcMCH_a9ZTHzV1VE2CKC4v1Tw5SkscF6SSOWnhbsqaKkorJhRymCMv0RB5G5pGb99mMeTuvha22ywIZzUrsble4aPtNiwjXLKOSU8JuaX1INXGoGRWaPV5NnziM1hYMOV9-Oav11fw9OpIbrVFML5QoLcwjGE1Gy0hgvwmmc8hHLPGwuiR6ld41t7KBO3-w5BZ1k4Meyl1s6TvQ57dwg1axn8CksYlWmdUQ-kbV9CQwGcyVPy5hDc--z8H9BoMLkpYnyRki9Ft9HE0m0xXEK5Q-a2IYDGbQc622JNCIWs0YnugAu7RUJ0hXCbkh5L2h_QvtBTFAWaK42MXtu4J7abTyqmHxksyAvekJMy1MwXCnDaZOHuRPeWnFVOttsLUyP-P-OSy-DFlEFnnvaZVa6imbyLaysZSRyCqHK2VWKOy7XzSF2rI0aqk3FmjlR8tmK3OuP6GnmjoV6FrGvGjL19Q91t3Tn51Z-bsztnzoe1pImxaYfFwbgodOHwv6DBeH31wTWdWSkeiWM_dk57kcz8gh3BR2DOkp3bBmgaoZ40J-ILAweA3ArOTwPEyuz0Ow1FTsPZI-4RE0dNI8GS3kwfoYTozRrAiVuoqXW9a4l7g13fn2GkMY8lK2FLaRGL0njpkmFf6K4z2gvs7hVplKuyR9skt015pWuKhKAkjIRclFZFO8BnYptcyTwydvgve9qmksS-D2IqilRB1La_1EP-52ZGV6Yr4hl3ThJGy5uC7Y-0su5e-UTcVZRtcBTWamglOt-R3z7EJbEWO3AQxDTlufSPeBBv1g6D-xswPqghiakR4FbgdufXpUm1__vgXbqBeaQ)**

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

## Other diagrams (sources only — not yet embedded inline)

These three are still source-only. Download and render with [mermaid.live](https://mermaid.live), the VS Code Mermaid extension, or any Mermaid-aware tool. They'll be embedded inline using the same pattern once we confirm the rendering above works on Pages.

| File | Purpose |
|---|---|
| `2-rag-zoom.mmd` | A zoom-in showing the RAG mechanics inside the Validator step (embedding, similarity search, augmented prompt, audit). |
| `3-decoupling-event-flow.mmd` | The lifecycle of a claim from submission through processing, human review, and replay. |
| `4-production-architecture.mmd` | The Azure topology view — trust boundary, components, PrivateLink to Foundry. |
