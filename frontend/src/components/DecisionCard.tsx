import { claimCopy } from '../copy/claim'
import { formatDateTime } from '../copy/format'
import type { HumanDecision } from '../pages/claimDerivation'
import { Sentence } from './Sentence'
import { Card } from './ui'

// What a person decided, read from the audit trail's human row (Prompt 30).
// It takes the review panel's place once the claim is no longer awaiting a
// person, so a visitor opening the claim later sees who decided, what, when
// and why, rather than a badge alone. `runPath` is the run the row sits under.
export function DecisionCard({ decision, runPath }: { decision: HumanDecision; runPath: string }) {
  return (
    <Card title={claimCopy.decisionHeading}>
      <div className="space-y-2 text-sm text-slate-700" data-testid="decision-card">
        <p>
          {claimCopy.decided(
            decision.decision,
            decision.decidedBy,
            formatDateTime(decision.decidedAt),
          )}
        </p>
        {decision.comment ? (
          <blockquote className="border-l-2 border-slate-300 pl-3 text-slate-600">
            {decision.comment}
          </blockquote>
        ) : (
          <p className="text-slate-500">{claimCopy.noComment}</p>
        )}
        <p className="text-xs text-slate-500">
          <Sentence segments={claimCopy.decisionInAudit(runPath)} />
        </p>
      </div>
    </Card>
  )
}
