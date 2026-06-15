// One-sentence "what's happening now" copy per agent, shown in the live pipeline
// visualisation while an agent is running. Kept beside tooltips.ts so Phase 7+
// copy revisions live in one place.

export const agentDescriptions: Record<string, string> = {
  doc_parser: 'Extracting structured fields from the claim narrative…',
  validator: 'Retrieving policy clauses and deciding coverage with citations…',
  adjuster: 'Estimating a settlement within the market-data range…',
  guardrail: 'Scanning the output for PII, bias, and hallucinated citations…',
}
