# Diagrams

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: true, theme: 'default', securityLevel: 'loose' });
</script>

## Architecture diagram (interactive)

The centrepiece of the design is the interactive **[Architecture Diagram](Architecture_Diagram.html)** — view it via GitHub Pages to render it in the browser. From the GitHub repo view this link shows HTML source only; the Pages-served version is what's meant for reading.

## Headline agent flow

The "what this is" sequence diagram — agents, audit vault, and the four-tier model strategy.

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

## Other diagrams (sources only — not yet embedded inline)

These three are still source-only. Download and render with [mermaid.live](https://mermaid.live), the VS Code Mermaid extension, or any Mermaid-aware tool. They'll be embedded inline using the same pattern once we confirm the rendering above works on Pages.

| File | Purpose |
|---|---|
| `2-rag-zoom.mmd` | A zoom-in showing the RAG mechanics inside the Validator step (embedding, similarity search, augmented prompt, audit). |
| `3-decoupling-event-flow.mmd` | The lifecycle of a claim from submission through processing, human review, and replay. |
| `4-production-architecture.mmd` | The Azure topology view — trust boundary, components, PrivateLink to Foundry. |
