// Plain-words labels for the values the API stores (Prompt 28). The stored value
// is never altered: these functions are for display only, and a value they do
// not know is shown in a readable fallback form rather than hidden or rejected.
// Written for every page; used by the Claims page first, the other pages follow
// in their own prompts. Prompt 30 split the status label in two: a claim's and
// a run's statuses share values but not, for `aborted`, their meaning.

const CLAIM_TYPE_LABELS: Record<string, string> = {
  // The six the form offers (and the market-data table prices).
  water_damage: 'Water damage',
  fire: 'Fire',
  wind: 'Wind',
  theft: 'Theft',
  flood: 'Flood',
  storm_complex: 'Storm (complex)',
  // The five the seed generator also produces (no market range; see the backlog).
  sprinkler_leakage: 'Sprinkler leakage',
  vandalism: 'Vandalism',
  smoke_damage: 'Smoke damage',
  hail: 'Hail',
  windstorm: 'Windstorm',
}

// The statuses a claim and a run share the words for. `aborted` is deliberately
// absent: it means something different for each (below), so each map adds its own.
const SHARED_STATUS_LABELS: Record<string, string> = {
  settled: 'Settled',
  awaiting_human: 'Awaiting human review',
}

// A claim's stored status. The four mid-pipeline values are where the latest
// run got to. A claim is stored `aborted` by one path only, a person's
// rejection in api/human.py (a run that broke leaves the claim's status where
// it was), so the word a reader sees is Rejected (Dermot, 14 November 2026,
// Prompt 30 D4). The stored value is unchanged; the colour still keys on it.
const CLAIM_STATUS_LABELS: Record<string, string> = {
  ...SHARED_STATUS_LABELS,
  received: 'Received',
  // Since Phase 8.2 the Doc-Parser produces only the narrative summary.
  extracted: 'Summarised',
  // True whether the verdict was covered or not.
  coverage_verified: 'Coverage checked',
  estimated: 'Settlement estimated',
  guardrail_checked: 'Guardrail checked',
  aborted: 'Rejected',
}

// A run's status, as the run summaries and the run page's badge report it. A
// run is `aborted` when an agent broke, so the word stays Aborted.
const RUN_STATUS_LABELS: Record<string, string> = {
  ...SHARED_STATUS_LABELS,
  running: 'Running',
  aborted: 'Aborted',
}

// Underscores to spaces, first letter capitalised: "hail_storm" → "Hail storm".
// An empty string stays empty rather than becoming a stray capital.
export function readableFallback(value: string): string {
  const spaced = value.trim().replace(/_+/g, ' ')
  return spaced.length === 0 ? '' : spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function claimTypeLabel(value: string): string {
  return CLAIM_TYPE_LABELS[value] ?? readableFallback(value)
}

export function claimStatusLabel(value: string): string {
  return CLAIM_STATUS_LABELS[value] ?? readableFallback(value)
}

export function runStatusLabel(value: string): string {
  return RUN_STATUS_LABELS[value] ?? readableFallback(value)
}

// --- Prompt 29: the run page -------------------------------------------------

// The replay variants in variants.yaml, as a sentence a visitor can read. The
// stored name is shown beside the sentence in small type, so the fallback need
// only be readable, not exact.
const VARIANT_LABELS: Record<string, string> = {
  default: 'Standard run',
  v2_strict_validator: 'Strict Validator run',
  v1_mistral: 'Mistral run',
}

export function variantLabel(variant: string): string {
  return VARIANT_LABELS[variant] ?? `${readableFallback(variant)} run`
}

// Why the code refused one of the Guardrail model's citation objections (Phase
// 9.2.2's `llm_flags_discarded[].reason`). The codes stay in the audit trail.
const REFUSAL_REASONS: Record<string, string> = {
  no_quote: 'the model gave no quotation',
  quote_not_in_reasoning: 'those words are not in the Adjuster’s reasoning',
  quote_not_a_provision: 'those words do not name a policy provision',
}

export function refusalReason(code: string): string {
  return REFUSAL_REASONS[code] ?? readableFallback(code)
}

// What a Guardrail flag of each kind means, as the object of "Failed: …".
const GUARDRAIL_FINDINGS: Record<string, string> = {
  hallucinated_citation: 'cited policy wording the policy does not contain',
  pii: 'personal data in the reasoning',
  bias: 'biased language in the reasoning',
}

export function guardrailFinding(kind: string): string {
  return GUARDRAIL_FINDINGS[kind] ?? readableFallback(kind)
}
