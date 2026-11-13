// Every sentence the run page's cards and header can show (Prompt 29). The
// cards used to print the agents' raw data; these functions turn the recorded
// values into one line each. The raw request and response stay in the expanded
// panel, and the stored values are never altered.
import type { FiredRule } from '../api/types'
import { formatPercent, formatUsd } from './format'
import { claimTypeLabel, guardrailFinding } from './labels'

// The thresholds the rule lines quote, as policy.yaml stores them. Typed here
// rather than read at runtime because the page has no endpoint for the policy
// file; `run.test.ts` reads the file and asserts these match, so the two cannot
// drift silently (plan D3).
export const RULE_THRESHOLDS: Record<string, string> = {
  settlement_over_ceiling: '250000',
  validator_confidence_floor: '0.65',
  adjuster_confidence_floor: '0.75',
}

// The description the orchestrator writes on the synthetic guardrail_failed
// rule when the Guardrail itself threw (fail-closed), as distinct from the
// policy file's "Guardrail output check did not pass".
const FAIL_CLOSED_DESCRIPTION = 'Guardrail check raised an exception; failing closed'

// The message shape of the Adjuster's market-range failure, the one abort the
// background claims produce today. Captures the claim type between the quotes.
const MARKET_LOOKUP = /^MarketDataTable\.lookup: unknown claim_type '([^']+)'/

export const runCopy = {
  waiting: 'Waiting',
  notRun: (stoppedAt: string) => `Not run: the run stopped at the ${stoppedAt}`,
  failed: (reason: string) => `Failed: ${reason}`,
  guardrailThrew: 'Failed: the check itself raised an error, so the claim went to a person',
  notFound: 'Run not found.',
  // Under the header while a run started from the Claims page has not yet
  // sent its first event.
  awaiting: 'Waiting for the run to begin…',
  // Shown in place of the cards while the run and audit queries are in flight.
  // Azure wakes from zero replicas in about half a minute; four cards reading
  // "Waiting" for that long would look like the fault Prompt 29 fixed.
  loading: 'Loading this run…',
  // The claim the run belongs to, after the claimant's name (which is the link
  // back to the claim page): "Water damage · $85,000 · claim CLM-2026-9BB57A86".
  claimDetails: (claimType: string, amount: string, claimNumber: string) =>
    `${claimTypeLabel(claimType)} · ${formatUsd(amount)} · claim ${claimNumber}`,
  claimUnavailable: 'The claim this run belongs to could not be loaded.',
  rulesHeading: 'Why it went to a person',
  // The run's wall time for an agent, from the difference between its audit
  // row and the row before it (plan D2); shown as the duration's title.
  durationFromAudit: 'from the audit trail',
  aborted: (reason: string) => `Run aborted: ${reason}`,

  docParser: (claimType: string) => `Summarised the claim (${claimTypeLabel(claimType)})`,
  // The confidence is optional because a live `agent_completed` event carries
  // none; the bracket appears when the audit row arrives a moment later.
  validator: (covered: boolean, confidence?: number) =>
    `${covered ? 'Covered' : 'Not covered'}${confident(confidence)}`,
  adjuster: (settlement: string, confidence?: number, demoFixture = false) =>
    demoFixture
      ? `Recommends ${formatUsd(settlement)} from the fixed demonstration file, no model call` +
        confident(confidence)
      : `Recommends ${formatUsd(settlement)}${confident(confidence)}`,
  guardrailPassed: (refusedCount: number) =>
    refusedCount === 0
      ? 'Passed'
      : `Passed; ${refusedCount} objection${refusedCount === 1 ? '' : 's'} refused`,
  guardrailFailed: (kinds: string[]) =>
    kinds.length === 0 ? 'Failed' : `Failed: ${kinds.map(guardrailFinding).join('; ')}`,
} as const

// " (92% confident)", or nothing when the confidence is not yet known.
function confident(confidence?: number): string {
  return confidence === undefined ? '' : ` (${formatPercent(confidence)} confident)`
}

// The plain-words reason an agent failed, from the exception's class and the
// shape of its message. The message itself is shown beneath the sentence, so
// the fallback need only say who raised what.
export function failureReason(agentLabel: string, errorType: string, message: string): string {
  const lookup = MARKET_LOOKUP.exec(message)
  if (errorType === 'ValueError' && lookup) {
    return `the ${agentLabel} has no market range for the claim type ${claimTypeLabel(lookup[1])}`
  }
  if (errorType === 'LLMProviderError') return 'the model provider refused or failed the call'
  return `the ${agentLabel} raised ${errorType}`
}

// One fired escalation rule as a line under the header, with the observed value
// where the rule has one. An unknown rule falls back to its own description so a
// rule added to policy.yaml is still shown.
export function ruleLine(rule: FiredRule): string {
  const observed = rule.observed_value ?? null
  switch (rule.name) {
    case 'settlement_over_ceiling':
      return `Settlement over the ${formatUsd(RULE_THRESHOLDS[rule.name])} ceiling: ${formatUsd(observed ?? '')}`
    case 'validator_confidence_floor':
      return confidenceLine('Validator', rule.name, observed)
    case 'adjuster_confidence_floor':
      return confidenceLine('Adjuster', rule.name, observed)
    case 'guardrail_failed':
      return rule.description === FAIL_CLOSED_DESCRIPTION
        ? 'Guardrail check itself failed, so the claim went to a person'
        : 'Guardrail check did not pass'
    case 'claim_type_watchlist':
      return 'Claim type is on the watchlist'
    case 'claimant_watchlist':
      return 'Claimant is on the watchlist'
    case 'cross_jurisdictional':
      return 'Claim spans more than one jurisdiction'
    default:
      return observed === null ? rule.description : `${rule.description}: ${observed}`
  }
}

// "Validator confidence below the 65% floor (58% confident)": the same bracketed
// form as the cards, so a confidence reads one way everywhere on the page.
function confidenceLine(agentLabel: string, ruleName: string, observed: string | null): string {
  const floor = formatPercent(Number(RULE_THRESHOLDS[ruleName]))
  const line = `${agentLabel} confidence below the ${floor} floor`
  return observed === null ? line : `${line} (${formatPercent(Number(observed))} confident)`
}
