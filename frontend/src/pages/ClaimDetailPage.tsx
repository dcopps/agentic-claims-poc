import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { RunSummary } from '../api/types'
import { HumanReviewPanel } from '../components/HumanReviewPanel'
import { Button, Card, Spinner, StatusBadge } from '../components/ui'
import { useClaim, useClaimRuns } from '../hooks/queries'

export function ClaimDetailPage() {
  const { claimId = '' } = useParams()
  const claim = useClaim(claimId)
  const runs = useClaimRuns(claimId)

  if (claim.isLoading) return <Spinner />
  if (claim.error || !claim.data) return <p className="text-red-600">Claim not found.</p>

  return (
    <div className="space-y-6">
      <Card title={claim.data.claimant_name}>
        <dl className="grid grid-cols-2 gap-1 text-sm">
          <Field label="Claim number" value={claim.data.claim_number} />
          <Field label="Type" value={claim.data.claim_type} />
          <Field label="Amount" value={claim.data.reported_amount} />
          <Field label="Jurisdiction" value={claim.data.jurisdiction} />
          <div>
            <dt className="text-slate-500">Status</dt>
            <dd>
              <StatusBadge status={claim.data.status} />
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-sm text-slate-600">{claim.data.narrative}</p>
      </Card>

      {claim.data.status === 'awaiting_human' && (
        <HumanReviewPanel claimId={claimId} runs={runs.data ?? []} />
      )}

      <Card title="Runs">
        {runs.isLoading && <Spinner />}
        {runs.data && runs.data.length === 0 && (
          <p className="text-sm text-slate-500">No runs yet — process this claim.</p>
        )}
        {runs.data && runs.data.length > 0 && (
          <RunsList claimId={claimId} runs={runs.data} />
        )}
      </Card>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-mono text-xs">{value}</dd>
    </div>
  )
}

function RunsList({ claimId, runs }: { claimId: string; runs: RunSummary[] }) {
  const [picked, setPicked] = useState<string[]>([])

  const toggle = (cid: string) =>
    setPicked((prev) =>
      prev.includes(cid) ? prev.filter((x) => x !== cid) : [...prev, cid].slice(-2),
    )

  return (
    <div className="space-y-2">
      <ul className="space-y-1 text-sm" aria-label="Runs">
        {runs.map((run) => (
          <li key={run.correlation_id} className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={`pick ${run.correlation_id}`}
              checked={picked.includes(run.correlation_id)}
              onChange={() => toggle(run.correlation_id)}
            />
            <Link
              to={`/claims/${claimId}/runs/${run.correlation_id}`}
              className="text-blue-700 hover:underline"
            >
              {run.variant}
            </Link>
            <StatusBadge status={run.status} />
            <span className="font-mono text-xs text-slate-400">
              {run.correlation_id.slice(0, 8)}
            </span>
          </li>
        ))}
      </ul>
      {picked.length === 2 && (
        <Link to={`/claims/${claimId}/compare/${picked[0]}/${picked[1]}`}>
          <Button variant="secondary">Compare selected</Button>
        </Link>
      )}
    </div>
  )
}
