# Diagrams

## Architecture diagram

The centrepiece of the design is the interactive **[Architecture Diagram](Architecture_Diagram.html)** — view it via GitHub Pages to render it in the browser. From the GitHub repo view this link shows HTML source only; the Pages-served version is what's meant for reading.

## Mermaid sources

Four Mermaid source files (`.mmd`). Render with [mermaid.live](https://mermaid.live), the VS Code Mermaid extension, or any Mermaid-aware tool.

| File | Purpose |
|---|---|
| `1-headline-agent-flow.mmd` | The headline sequence diagram — agents and the audit vault. The "what this is" diagram. |
| `2-rag-zoom.mmd` | A zoom-in showing the RAG mechanics inside the Validator step (embedding, similarity search, augmented prompt, audit). |
| `3-decoupling-event-flow.mmd` | The lifecycle of a claim from submission through processing, human review, and replay. |
| `4-production-architecture.mmd` | The Azure topology view — trust boundary, components, PrivateLink to Foundry. |
