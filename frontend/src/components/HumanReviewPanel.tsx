import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { submitHumanDecision } from '../api/client'
import type { AuditEntry, RunSummary } from '../api/types'
import { useAuditEntries } from '../hooks/queries'
import { Button, Card, Spinner } from './ui'

// The human-review panel. Evidence is assembled from the latest run's *audit
// entries* — `ValidatorVerdict.cited_chunks` carries chunk IDs without the clause
// text, so the policy-clause content lives only in the validator's coverage_check
// audit payload. Approve/Reject post a typed decision and optimistically refresh.
export function HumanReviewPanel({
  claimId,
  runs,
}: {
  claimId: string
  runs: RunSummary[]
}) {
  const latest = runs[0]?.correlation_id
  const audit = useAuditEntries(latest ?? '')
  const queryClient = useQueryClient()
  const [decidedBy, setDecidedBy] = useState('')
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const decide = async (decision: 'approved' | 'rejected') => {
    setError(null)
    setBusy(true)
    try {
      await submitHumanDecision(claimId, { decision, decided_by: decidedBy, comment })
      await queryClient.invalidateQueries({ queryKey: ['claim', claimId] })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Human review">
      {audit.isLoading && <Spinner label="Loading evidence…" />}
      {audit.data && <Evidence entries={audit.data} />}
      <div className="mt-4 space-y-2 border-t border-slate-200 pt-3">
        <input
          aria-label="Decided by"
          placeholder="Your name"
          className="rounded border border-slate-300 px-2 py-1 text-sm"
          value={decidedBy}
          onChange={(e) => setDecidedBy(e.target.value)}
        />
        <textarea
          aria-label="Comment"
          placeholder="Comment (optional)"
          className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
          rows={2}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="space-x-2">
          <Button onClick={() => decide('approved')} disabled={busy || !decidedBy.trim()}>
            Approve
          </Button>
          <Button
            variant="danger"
            onClick={() => decide('rejected')}
            disabled={busy || !decidedBy.trim()}
          >
            Reject
          </Button>
        </div>
      </div>
    </Card>
  )
}

type Obj = Record<string, unknown>

function _obj(value: unknown): Obj | undefined {
  return value && typeof value === 'object' ? (value as Obj) : undefined
}

function Evidence({ entries }: { entries: AuditEntry[] }) {
  const payload = (step: string): Obj | undefined =>
    entries.find((e) => e.step === step)?.payload
  const adjusterOut = _obj(payload('settlement_estimate')?.output)
  const chunks = _obj(payload('coverage_check')?.retrieval)?.chunks
  const guardrailOut = _obj(payload('output_check')?.output)
  const chunkList = Array.isArray(chunks) ? (chunks as Obj[]) : []

  return (
    <dl className="space-y-2 text-sm">
      {adjusterOut && (
        <div>
          <dt className="text-slate-500">Recommended settlement</dt>
          <dd className="font-mono">{String(adjusterOut.recommended_settlement)}</dd>
          <dd className="text-slate-600">{String(adjusterOut.reasoning)}</dd>
        </div>
      )}
      {chunkList.length > 0 && (
        <div>
          <dt className="text-slate-500">Cited policy clauses</dt>
          {chunkList.map((chunk, i) => (
            <dd key={i} className="text-slate-600">
              <span className="font-medium">{String(chunk.section)}:</span>{' '}
              {String(chunk.content_excerpt)}
            </dd>
          ))}
        </div>
      )}
      {guardrailOut && (
        <div>
          <dt className="text-slate-500">Guardrail</dt>
          <dd>
            {guardrailOut.passed ? 'passed' : 'flagged'} — {String(guardrailOut.summary)}
          </dd>
        </div>
      )}
    </dl>
  )
}
