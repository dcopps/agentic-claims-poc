import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { replayPipeline, runPipeline } from '../api/client'
import type { ClaimRecord } from '../api/types'
import { ClaimForm } from '../components/ClaimForm'
import { Tooltip } from '../components/Tooltip'
import { Button, Card, Spinner, StatusBadge } from '../components/ui'
import { tooltips } from '../copy/tooltips'
import { useClaims } from '../hooks/queries'

const REPLAYABLE = new Set(['settled', 'awaiting_human', 'aborted'])
const REPLAY_VARIANT = 'v2_strict_validator'

export function ClaimsPage() {
  const { data: claims, isLoading, error } = useClaims()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [busy, setBusy] = useState<string | null>(null)

  const refetch = () => queryClient.invalidateQueries({ queryKey: ['claims'] })

  const trigger = async (claimId: string, kind: 'process' | 'replay') => {
    const cid = crypto.randomUUID()
    setBusy(claimId)
    try {
      if (kind === 'process') await runPipeline(claimId, cid)
      else await replayPipeline(claimId, cid, REPLAY_VARIANT)
      await refetch()
      navigate(`/claims/${claimId}/runs/${cid}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Submit a claim">
        <ClaimForm onSubmitted={refetch} />
      </Card>
      <Card title="Claims">
        {isLoading && <Spinner />}
        {error && <p className="text-sm text-red-600">Failed to load claims.</p>}
        {claims && claims.length === 0 && (
          <p className="text-sm text-slate-500">No claims yet — submit one above.</p>
        )}
        {claims && claims.length > 0 && (
          <table className="w-full text-left text-sm" aria-label="Claims">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Claimant</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {claims.map((claim) => (
                <ClaimRow
                  key={claim.claim_id}
                  claim={claim}
                  busy={busy === claim.claim_id}
                  onProcess={() => trigger(claim.claim_id, 'process')}
                  onReplay={() => trigger(claim.claim_id, 'replay')}
                />
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

function ClaimRow({
  claim,
  busy,
  onProcess,
  onReplay,
}: {
  claim: ClaimRecord
  busy: boolean
  onProcess: () => void
  onReplay: () => void
}) {
  return (
    <tr className="border-t border-slate-200">
      <td className="py-1">
        <Link to={`/claims/${claim.claim_id}`} className="text-blue-700 hover:underline">
          {claim.claimant_name}
        </Link>
      </td>
      <td>{claim.claim_type}</td>
      <td>{claim.reported_amount}</td>
      <td>
        <StatusBadge status={claim.status} />
      </td>
      <td className="space-x-2 py-1">
        <Tooltip text={tooltips.processClaim}>
          <Button onClick={onProcess} disabled={busy}>
            Process
          </Button>
        </Tooltip>
        <Tooltip text={tooltips.reprocessV2}>
          <Button
            variant="secondary"
            onClick={onReplay}
            disabled={busy || !REPLAYABLE.has(claim.status)}
          >
            Re-process with v2
          </Button>
        </Tooltip>
      </td>
    </tr>
  )
}
