// How the claim page reads the latest run's audit rows (Prompt 30).
//
// The page has three sources: the claim record, the run summaries, and the
// latest run's audit rows, fetched once and shared by the status line, the
// runs list, the review panel and the Decision card (plan D2). A summary holds
// no settlement figure, no failing agent and no human decision; those are in
// the rows alone, so everything the page says beyond the stored status comes
// through here. Pure functions, no React, in the manner of runDerivation.ts.
import type { AuditEntry, ClaimStatus, FiredRule, RunStatus, RunSummary } from '../api/types'
import type { RunOutcome } from '../copy/claim'
import { FAIL_CLOSED_DESCRIPTION } from '../copy/run'
import { agentLabel, deriveAbort, deriveFiredRules } from './runDerivation'

/** A person's decision, from the `human` audit row api/human.py writes. */
export interface HumanDecision {
  decision: 'approved' | 'rejected'
  decidedBy: string
  comment: string | null
  decidedAt: string
}

// The claim statuses that mean the pipeline left the claim part-way: a run
// broke after reaching this step and wrote no later status.
const PART_WAY: ReadonlySet<string> = new Set<ClaimStatus>([
  'extracted',
  'coverage_verified',
  'estimated',
  'guardrail_checked',
])

const HUMAN_STEPS: Record<string, HumanDecision['decision']> = {
  human_approval: 'approved',
  human_rejection: 'rejected',
}

// The API orders summaries by started_at descending and api/human.py decides
// on the same first run, so the page does not re-sort: both agree on "latest".
export function latestRun(runs: readonly RunSummary[]): RunSummary | undefined {
  return runs[0]
}

// The latest run's outcome with what its rows add: the settled figure from the
// pipeline_settled row, the failing agent from the pipeline_aborted row. The
// other outcomes carry nothing more than the summary's word.
export function deriveRunOutcome(status: RunStatus, rows: AuditEntry[]): RunOutcome {
  switch (status) {
    case 'settled': {
      const settlement = rows.find((r) => r.step === 'pipeline_settled')?.payload.settlement
      return {
        kind: 'settled',
        settlement: typeof settlement === 'string' ? settlement : undefined,
      }
    }
    case 'aborted': {
      const abort = deriveAbort(rows, [])
      return { kind: 'aborted', failingAgent: abort ? agentLabel(abort.failingAgent) : undefined }
    }
    default:
      return { kind: status }
  }
}

// The agent the latest run stopped at, when the claim's status says the run
// never finished and the rows say which agent broke; null otherwise, because
// the terminal statuses speak for themselves.
export function deriveStoppedAt(status: string, rows: AuditEntry[]): string | null {
  if (!PART_WAY.has(status)) return null
  const abort = deriveAbort(rows, [])
  return abort ? agentLabel(abort.failingAgent) : null
}

// The last human row wins: a claim has at most one, but the rule is stated so
// a second never hides the first silently.
export function deriveDecision(rows: AuditEntry[]): HumanDecision | null {
  const row = [...rows].reverse().find((r) => r.agent === 'human' && r.step in HUMAN_STEPS)
  if (!row) return null
  const { decided_by, comment, decided_at } = row.payload
  return {
    decision: HUMAN_STEPS[row.step],
    decidedBy: typeof decided_by === 'string' ? decided_by : '',
    comment: typeof comment === 'string' && comment.trim() !== '' ? comment : null,
    decidedAt: typeof decided_at === 'string' ? decided_at : row.created_at,
  }
}

// The fired rules the reviewer reads first. The fail-closed path writes no
// escalation_decision row (the Guardrail itself threw), so the awaiting row's
// reason stands in as the one synthetic rule the backend's reconstructed run
// also carries; ruleLine then gives it the fail-closed sentence.
export function deriveWhyHere(rows: AuditEntry[]): FiredRule[] {
  const fired = deriveFiredRules(rows)
  if (fired.length > 0) return fired
  const threw = rows.some(
    (r) => r.step === 'pipeline_awaiting_human' && r.payload.reason === 'guardrail_threw',
  )
  return threw
    ? [
        {
          name: 'guardrail_failed',
          rule_type: 'hard',
          description: FAIL_CLOSED_DESCRIPTION,
          observed_value: null,
        },
      ]
    : []
}
