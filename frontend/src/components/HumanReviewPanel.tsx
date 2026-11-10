import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { submitHumanDecision } from '../api/client'
import type { AuditEntry, RunSummary } from '../api/types'
import { useAuditEntries } from '../hooks/queries'
import { Badge, Button, Card, Spinner } from './ui'

// The human-review panel. Evidence is assembled from the latest run's *audit
// entries* — `ValidatorVerdict.cited_chunks` carries chunk IDs without the clause
// text, so the passages shown are the coverage_check payload's *retrieved* chunks,
// each linked to its place on the Policy page and badged when the verdict cited
// it (Prompt 27). Approve/Reject post a typed decision and optimistically refresh.
export function HumanReviewPanel({ claimId, runs }: { claimId: string; runs: RunSummary[] }) {
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
  const payload = (step: string): Obj | undefined => entries.find((e) => e.step === step)?.payload
  const adjusterOut = _obj(payload('settlement_estimate')?.output)
  const coverage = payload('coverage_check')
  const chunks = _obj(coverage?.retrieval)?.chunks
  const guardrailOut = _obj(payload('output_check')?.output)
  const chunkList = Array.isArray(chunks) ? (chunks as Obj[]) : []
  const cited = _citedIds(coverage)

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
          <dt className="text-slate-500">Retrieved policy passages</dt>
          {chunkList.map((chunk, i) => (
            <dd key={i} className="text-slate-600">
              <Link
                to={{ pathname: '/policy', hash: String(chunk.chunk_id) }}
                className="font-medium text-blue-700 hover:underline"
              >
                {String(chunk.section)}
              </Link>
              {cited.has(String(chunk.chunk_id)) && (
                <>
                  {' '}
                  <Badge tone="success">cited</Badge>
                </>
              )}
              : {String(chunk.content_excerpt)}
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

// The chunk ids the Validator's verdict cited, so the retrieved list can mark
// which of the three passages the decision actually rested on.
function _citedIds(coverage: Obj | undefined): Set<string> {
  const cited = _obj(coverage?.verdict)?.cited_chunks
  if (!Array.isArray(cited)) return new Set()
  return new Set(
    cited.flatMap((c) => {
      const id = _obj(c)?.chunk_id
      return typeof id === 'string' ? [id] : []
    }),
  )
}
