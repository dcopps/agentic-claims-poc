# Multi-Agent Insurance Claims Architecture — Stack Reference

## Purpose

A side-by-side reference of the development stack (the working prototype) and the production stack (the target deployment for a regulated specialty insurer operating across Bermuda, the UK, the US, and the EU). Use this as a quick-lookup when building, demonstrating, or discussing the architecture.

The prototype is deliberately deployed on commodity hosting (Render and Vercel) for fast iteration and zero deployment friction. The production target is the Microsoft Azure stack the organisation already operates, with all data confined to the corporate Azure tenant and all model inference reached through private network paths.

## Architectural principles (the five ideas everything reduces to)

1. **Trust boundary.** All components that touch claim data live inside the corporate Azure tenant. External model inference is reached only via Azure PrivateLink.
2. **Decoupling.** Claims are persisted to a system of record before any AI processes them. The pipeline is triggered by events, not by direct user submission.
3. **Durable workflow.** Long human-review waits are handled by Azure Durable Functions, which persists workflow state across restarts and failovers.
4. **Tamper-evident audit.** SQL Server Ledger Tables maintain a cryptographic hash chain natively. A daily database digest is exported to immutable Blob Storage as a Write-Once-Read-Many backstop.
5. **Provider substitutability.** All LLM access is mediated by an LLM Gateway service, providing a tested swap path between model providers — a regulatory artefact under DORA Article 28, not just clean code.

## Stack at a glance

| Layer / Concern | Development (Prototype) | Production (Target) |
|---|---|---|
| Frontend hosting | Vercel | Azure Container Apps |
| Frontend framework | React with Vite, Tailwind CSS | React with Vite, Tailwind CSS |
| Backend hosting | Render | Azure Container Apps |
| Backend framework | Python 3.11+, FastAPI, Uvicorn, Pydantic | Python 3.11+, FastAPI, Uvicorn, Pydantic |
| API edge | Render's built-in router | Azure API Management with Entra ID auth |
| Workflow orchestration | In-process Python async | Azure Durable Functions |
| Event backbone | Button-triggered events in the React UI | Azure Service Bus |
| Claims of record | Neon (managed Postgres) — `eu-central-1` / Frankfurt; pgvector 0.8.0 enabled | Azure SQL Managed Instance |
| Audit vault | Neon (managed Postgres) with hand-rolled SHA-256 hash chain | Azure SQL Managed Instance with Ledger Tables |
| Audit immutability backstop | Not present in prototype | Azure Blob Storage with Immutable Policy (daily digest) |
| Vector index | pgvector extension on the same Neon database | Azure AI Search (vector + hybrid retrieval) |
| Embedding model | bge-small-en-v1.5 (local, sentence-transformers) | text-embedding-3-large via Azure AI Foundry private endpoint |
| Frontier LLM (Orchestrator) | Claude Sonnet via public Anthropic API | Claude Sonnet via Azure AI Foundry private endpoint |
| Small LLM (Doc-Parser, Guardrail) | Claude Haiku via public Anthropic API | Claude Haiku via Azure AI Foundry private endpoint |
| Open-weight LLM (Validator) | Mistral Large via public Mistral API | Mistral Large via Azure AI Foundry private endpoint |
| Open-weight LLM with fine-tune (Adjuster) | Mistral Large via public Mistral API (no fine-tune in prototype) | Mistral Large with LoRA adapter, trained on redacted historical claims |
| Document extraction (known templates) | Not present (Haiku handles all input) | Azure AI Document Intelligence (deterministic OCR) before Haiku |
| LLM Gateway | Thin Python wrapper class (same interface as production) | Tenant-owned Container Apps service: routing, failover, prompt logging, cost attribution, PII redaction |
| LLM observability | Langfuse (self-hosted on Render or free cloud tier) | Langfuse self-hosted on Azure Container Apps |
| Operational observability | Render log viewer, Python logging | Azure Monitor with Application Insights |
| Identity (services) | Environment variables for API keys | Microsoft Entra ID managed identities |
| Identity (humans) | None (single-user demo) | Microsoft Entra ID with SAML single sign-on |
| Secrets management | Render dashboard environment variables | Azure Key Vault |
| Source control | GitHub | The organisation's existing Azure DevOps organisation |
| CI / CD | GitHub Actions | Azure DevOps Pipelines |
| Infrastructure as code | Render and Vercel auto-deploys (no IaC needed) | Bicep templates |
| Change governance | None (prototype) | Azure DevOps Work Items: standard / normal / emergency change taxonomy with CCB workflow |
| Code quality | Black, ruff, mypy (Python); ESLint, Prettier (JS) | Black, ruff, mypy (Python); ESLint, Prettier (JS) |
| Testing | pytest with synthetic claim eval harness | pytest plus golden test set of historical claims with known outcomes; eval pipeline runs on every PR |
| Fine-tuning platform | Not present in prototype | Azure Machine Learning training jobs producing LoRA adapters; adapters versioned in Blob Storage; blue/green deploy |
| Region | Render and Vercel default regions | Azure North Europe (Dublin) primary; West Europe paired secondary for DR |
| Network model | Public internet (synthetic data only) | Private VNet, private endpoints for all Azure services, PrivateLink to Foundry |

## Development stack — detailed

### Frontend tier

**React with Vite.** A single-page application providing the user-facing UI for claim submission, status tracking, and the human-handler review panel. Vite chosen over Create React App for build speed and modern defaults.

**Tailwind CSS.** Utility-first styling. Avoids the CSS bikeshed during prototype iteration and keeps the markup self-documenting.

**Vercel hosting.** Zero-configuration deployments triggered from the GitHub `main` branch. Free tier sufficient for the demo; preview deployments per PR.

### Backend tier

**Python 3.11+ with FastAPI.** The API and orchestration layer. FastAPI's Pydantic integration enforces typed request and response schemas across every agent boundary, which doubles as living documentation.

**Uvicorn.** The ASGI server hosting the FastAPI application.

**Pydantic.** Data validation and schema definition. Every agent's input and output is a Pydantic model, making the contracts explicit and the test surface small.

**Render hosting.** Single-click deploys from GitHub, free tier for the application service. Adequate for a public-facing demo. The data tier is split out to Neon (see Data tier below) rather than using Render's bundled Postgres.

### Workflow and event simulation

**In-process Python async.** No real workflow engine in the prototype; the agents run sequentially within the FastAPI request handler or in a background task.

**Button-triggered events in the React UI.** The "Process Claim", "Approve", and "Re-process with v2 model" buttons stand in for the production event-driven flow. Each button's tooltip describes the production equivalent (Service Bus event, Durable Functions signal, etc.) so the architecture is visible without being implemented.

### Data tier

**Neon (managed Postgres).** Postgres 17 with pgvector 0.8.0 enabled, hosted in Neon's `eu-central-1` (Frankfurt) region on the free tier. Hosts the claims of record, the audit table, and the vector index in a single database — simplest possible deployment. Neon is split out from Render so the data tier is independently managed and so the prototype's Postgres version and `pgvector` extension version are pinned by us, not by Render's image.

**pgvector extension.** Postgres extension that adds a `vector` column type and cosine distance operators. Used for the policy chunk vector index.

**Audit table with hand-rolled SHA-256 hash chain.** Every row's hash is computed as `SHA-256(row_content + previous_chain_hash)`. Tampering with any row breaks every subsequent hash, providing detective tamper-evidence in plain Postgres. The README explains that production replaces this with SQL Server Ledger Tables, which provide the same property natively.

### AI / LLM tier

**Claude Sonnet via the public Anthropic API.** The Orchestrator's reasoning model — used specifically for the human-escalation decision.

**Claude Haiku via the public Anthropic API.** The Doc-Parser (extracts structured fields from claim narratives and document images using Haiku's vision capability) and the Guardrail (checks the Adjuster's output for PII leakage, bias, and hallucinated policy citations).

**Mistral Large via the public Mistral API.** The Validator (RAG-based coverage decision) and the Adjuster (settlement estimation). The Adjuster does not have a fine-tuned LoRA adapter in the prototype; the production architecture document describes how this would be trained and deployed.

**bge-small-en-v1.5 embedding model.** Loaded into the FastAPI process via the `sentence-transformers` library. Runs on CPU; produces 384-dimensional vectors. Used both for indexing the policy chunks and for embedding the claim narrative at query time.

**LLM Gateway.** A thin Python class wrapping the Anthropic and Mistral SDK calls. Exposes a single `complete(model, messages, ...)` interface. The same interface as the production version, so the swap from public APIs to Azure AI Foundry is a configuration change rather than a code change.

### Observability

**Langfuse.** LLM observability platform capturing every prompt, response, latency, and token cost, joined to the correlation ID. Either self-hosted on a small Render instance or using Langfuse's free cloud tier for the demo.

**Python logging to stdout.** General-purpose application logging captured by Render's log viewer.

### Identity and secrets

**Environment variables.** API keys for Anthropic and Mistral set in Render's dashboard. Never in source control.

**No real authentication.** Single-user demo; the human-handler review is just a button on the same page as the claimant view.

### CI / CD and code quality

**GitHub Actions.** Lint, format check, and test on every PR. Auto-deploys to Render and Vercel on merge to `main`.

**Code quality tools.** Black for Python formatting, ruff for linting, mypy for type checking, ESLint and Prettier for JavaScript.

**pytest.** Python unit and integration tests, including a small evaluation harness that runs the agents against synthetic claims with known expected outcomes.

## Production stack — detailed

### Frontend tier

**React on Azure Container Apps.** Same application code as the prototype, deployed inside the corporate Azure tenant. In practice, the AI capability may be embedded in the existing claims workbench rather than running as a standalone UI; the standalone React app is the simpler architectural answer for the prototype-to-production migration.

### Backend tier

**Python FastAPI on Azure Container Apps.** Managed container service with autoscaling and scale-to-zero. No Kubernetes operations to manage. The same FastAPI codebase as the prototype, with environment-specific configuration for the production providers.

**Azure API Management.** The system's front door. Terminates HTTPS, enforces authentication via Entra ID, applies rate limiting, and routes to the appropriate backend service.

### Workflow orchestration

**Azure Durable Functions.** A workflow engine that persists its own state, survives container restarts, and waits indefinitely for external signals. Replaces the prototype's in-process async pattern. Critical for handling long human-review delays without holding any HTTP connection or in-memory state open.

**Azure Service Bus.** Enterprise message bus that decouples the claims of record from the AI pipeline. The claims of record emits a `ClaimReceived` event; Durable Functions consumes it and starts a new orchestration. If the AI pipeline is degraded or offline, claims continue to be received and queue safely until processing resumes.

### Data tier

**Azure SQL Managed Instance — Claims of Record.** The system of record for claim data. Operated by the existing DBA team using their existing PowerShell, T-SQL, and IaC tooling. Always-On Availability Groups for high availability, geo-replication to the secondary region for disaster recovery.

**Azure SQL Managed Instance — Audit Vault with Ledger Tables.** Same SQL MI engine, but uses SQL Server 2022 Ledger Tables for the audit log. Ledger Tables maintain a cryptographic hash chain over every row in the database engine itself; tampering breaks the chain detectably without any application code involvement.

**Azure AI Search.** Managed search service supporting both vector retrieval and hybrid (keyword plus vector) retrieval. Replaces the prototype's pgvector. Scales independently of the application database; integrates natively with Entra ID for authentication.

**Azure Blob Storage with Immutable Policy.** Daily database digest from the Audit Vault is exported to a blob container under an immutable retention policy. Once written, the blob cannot be modified or deleted (even by the storage administrator) until the retention period expires. Provides the WORM backstop for the audit chain.

### AI / LLM tier

**Azure AI Foundry.** Microsoft's unified platform for hosting LLMs inside an Azure tenant. Both Anthropic models (Sonnet and Haiku) and Mistral models are available as first-party services, accessed through a single tenant-scoped endpoint.

**Foundry Private Endpoint.** A network endpoint provisioned inside the corporate VNet, with an IP address in the private address space. Connects to Foundry over Azure PrivateLink — a private network path that does not traverse the public internet. The model physically runs in Microsoft's data centres, but the corporate data never leaves the trust boundary to get there.

**Embedding Private Endpoint.** Same pattern, for the embedding model. Either text-embedding-3-large via Foundry, or a self-hosted bge-large model running on Container Apps if full control over the embedding pipeline is desired.

**Mistral Large with LoRA adapter.** The Adjuster's specialised version, fine-tuned on the organisation's PII-redacted historical claims data. The base Mistral model is unchanged; a small LoRA (Low-Rank Adaptation) adapter sits alongside it at inference time, capturing the organisation-specific patterns. Adapters are versioned artefacts in Blob Storage, deployed blue/green to a Foundry custom model endpoint.

**Azure AI Document Intelligence.** Deterministic OCR and structured extraction for known document templates (the organisation's FNOL form, internal claim forms, standard third-party formats). Sits in front of Haiku in the Doc-Parser pipeline; Haiku handles the freeform text and unknown documents. Document Intelligence is preferred for known formats because it is deterministic — same input always produces same output, which makes it auditable and SOX-friendly.

**LLM Gateway.** A tenant-owned service running on Container Apps. Sits between the agents and Foundry. Responsibilities: model selection (route to Sonnet, Haiku, or Mistral as appropriate), provider failover (cut over to a backup if the primary degrades), prompt logging (every prompt and response captured to Langfuse), cost attribution (per-business-unit billing tags), and PII redaction (logs are scrubbed before they leave for observability). The Gateway is the substitutability layer that makes a provider swap a matter of configuration rather than redeployment — the architectural artefact required by DORA Article 28.

### Observability

**Azure Monitor with Application Insights.** Operational telemetry for all services: request rates, latencies, error rates, infrastructure metrics, dependency calls. The "is the system healthy" view that operations teams live in.

**Langfuse self-hosted on Azure Container Apps.** LLM-specific observability layer. Captures every prompt, every completion, every retrieval, every token cost, every trace, joined to the correlation ID. Self-hosted so that prompt data — which contains PII — stays inside the tenant. Critical for debugging model behaviour, detecting drift, and producing the audit reconstruction a regulator may request.

### Identity and secrets

**Microsoft Entra ID.** Identity service for everything. Service-to-service calls authenticated via managed identities — no service account passwords floating around. Human users authenticated via SAML single sign-on against the existing Entra ID tenant.

**Azure Key Vault.** All secrets — API keys for any non-Foundry providers, certificates, connection strings, signing keys. Services have Entra ID identities; identities are granted permission to read specific secrets. Compromise of a service is mitigated by rotating the secret, not by shipping a new build.

### Fine-tuning lifecycle

**Azure Machine Learning.** Training platform for the Adjuster's LoRA adapters. Training jobs run in a dedicated subscription against a curated, PII-redacted dataset of historical claims with known settlement outcomes.

**Adapter versioning in Blob Storage.** Every produced adapter is a versioned artefact. Adapters are immutable once produced; rollback is loading the previous version, not rewriting the current one.

**Blue/green deploy to Foundry custom endpoints.** New adapter deployed alongside the current production adapter. Traffic shadowed at low percentage. Metrics compared against the golden set. Promotion to full production only after metrics hold and CCB approval is granted.

### Evaluation

**Golden test set.** A curated collection of historical claims with known outcomes — coverage decisions, settlement amounts, human-handler verdicts. The non-negotiable artefact for AI quality control.

**Eval pipeline.** Runs on every PR that touches a prompt, an agent, a model, or an adapter. Posts metrics delta to the Azure DevOps work item. The pipeline is the boundary between standard and normal changes — deltas within tolerance ride the standard-change path; deltas outside tolerance require CCB review.

### CI / CD and change governance

**Azure DevOps Pipelines.** The system of record for changes. Builds, tests, scans, and deploys via Bicep templates. Every production deployment links back to a Work Item with risk rating, rollback plan, and CCB approval evidence.

**Azure DevOps Work Items.** Change records. The standard / normal / emergency taxonomy is enforced through Work Item templates. Standard changes (prompt iterations within the eval gate) are pre-approved by CCB once and execute many times via CI/CD. Normal changes (new model versions, new adapters, new agents) require per-change CCB approval. Emergency changes (model rollback, prompt hotfix, guardrail tightening) are pre-approved as a category and reviewed post-hoc at the next CCB.

**Bicep.** Microsoft's IaC language. Every Azure resource — networks, identities, services, secrets, observability — defined in Bicep modules with environment-specific parameter files. Deployments are reproducible, reviewable, and auditable.

### Existing systems integrated with

**Claims Workbench.** Wherever the organisation's human handlers actually work — Salesforce Financial Services Cloud, an in-house tool, or a commercial system such as Guidewire ClaimCenter or Duck Creek Claims. The AI pipeline pushes review tasks into this workbench. It does not replace it.

**Existing Entra ID tenant.** The AI system uses the organisation's existing identity tenant. No new identity provider, no separate user directories.

**Existing Azure DevOps organisation.** The AI codebase lives alongside the organisation's other application repositories, under the same governance.

### Compliance overlay

**SOX IT General Controls.** Auditable change control via Azure DevOps Work Items. Standard / normal / emergency change taxonomy maps directly onto SOX ITGC expectations for change authorisation, testing, and segregation of duties.

**DORA (Digital Operational Resilience Act).** Third-party register of all LLM providers (Anthropic, Mistral, Microsoft Foundry, embedding model provider). Substitutability demonstrated and tested via the LLM Gateway. Concentration risk addressed by the multi-provider architecture. Resilience testing through scheduled chaos exercises against each provider failure scenario.

**GDPR.** Data residency in North Europe (Dublin region) for any EU policyholder data. PII redaction in observability logs. Right-to-erasure procedures defined for the claims of record and the audit vault (the audit vault retains the existence of records but redacts identifying content, preserving the chain integrity).

**ISO 27001 (Information Security).** Inherited largely from Azure's own certifications, with organisation-specific overlays for application-layer controls.

**ISO 22301 (Business Continuity).** Multi-region deployment with the paired secondary region. Documented runbooks for the major failure scenarios. Regular failover exercises with evidence captured in Azure DevOps.

**CBI (Central Bank of Ireland) supervision.** Where applicable to an Irish-regulated entity, AI governance frameworks aligned to CBI's published AI guidance. Reporting and incident notification procedures in place.

## Key dev → prod transitions

Six transitions matter most when moving from the prototype to the production target:

**LLM provider swap.** From public Anthropic and Mistral APIs to Azure AI Foundry private endpoints. The LLM Gateway abstraction makes this a configuration change. No agent code changes.

**Audit vault swap.** From hand-rolled SHA-256 hash chains in Postgres to SQL Server Ledger Tables. The application code that writes audit rows is largely unchanged; the database engine takes over the chain integrity. The daily digest export to immutable Blob Storage is added.

**Vector store swap.** From pgvector to Azure AI Search. Hybrid retrieval (keyword plus vector) becomes available; pure cosine similarity is no longer the only option. Re-indexing is required because the embedding model also moves from bge-small to text-embedding-3-large — the embedding swap is the harder of the two changes because it is a one-way door.

**Workflow swap.** From in-process async to Azure Durable Functions. The agent code is unchanged; the orchestration layer is rewritten as a Durable Functions orchestrator with each agent as an activity function. This is what unlocks the long human-review wait without holding application state.

**Event swap.** From button-triggered events in the UI to real Azure Service Bus messages. The triggers in the UI are removed (or hidden behind an operations console); the production system is event-driven from the moment a claim is persisted.

**Governance overlay.** Adding the change governance machinery — the standard / normal / emergency taxonomy, the CCB approval workflow, the Work Item templates, the eval gate as the standard-change boundary. None of this exists in the prototype. All of it is essential in production.

## Notes on the prototype's role in interviews and demonstrations

The prototype is not the production system in miniature. It is a working artefact that demonstrates the agent architecture, the RAG pipeline, the audit pattern, and the tiered model strategy on commodity infrastructure. Its credibility comes from being live, runnable, and open to inspection.

The production architecture is the strategic answer. Its credibility comes from being internally consistent, regulatorily defensible, and operationally realistic — designed to land in the organisation's existing technology landscape rather than to require greenfield infrastructure.

Both are needed. The prototype demonstrates that the architect can build the thing; the production architecture demonstrates that the architect understands what it would take to run the thing.
