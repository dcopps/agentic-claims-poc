// Plain-words labels for the values the API stores (Prompt 28). The stored value
// is never altered: these functions are for display only, and a value they do
// not know is shown in a readable fallback form rather than hidden or rejected.
// Written for every page; used by the Claims page first, the other pages follow
// in their own prompts.

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

const STATUS_LABELS: Record<string, string> = {
  received: 'Received',
  // Since Phase 8.2 the Doc-Parser produces only the narrative summary.
  extracted: 'Summarised',
  // True whether the verdict was covered or not.
  coverage_verified: 'Coverage checked',
  estimated: 'Settlement estimated',
  guardrail_checked: 'Guardrail checked',
  settled: 'Settled',
  awaiting_human: 'Awaiting human review',
  aborted: 'Aborted',
  // A run status, not a claim status; here for the pages that show runs.
  running: 'Running',
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

export function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? readableFallback(value)
}
