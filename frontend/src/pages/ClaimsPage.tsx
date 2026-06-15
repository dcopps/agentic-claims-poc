import { useQueryClient } from '@tanstack/react-query'
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

  const refetch = () => queryClient.invalidateQueries({ queryKey: ['claims'] })

  // Navigate to the run-detail page FIRST so its SSE subscription is open before
  // the run emits events (the event bus buffers late subscribers, so this is
  // safe), then fire the POST without awaiting — the ~27s run is observed live
  // rather than blocking the navigation. A failed POST writes the error to a
  // run-scoped cache key the run-detail page renders (fix #6); a successful one
  // refreshes the claims list.
  const trigger = (claimId: string, kind: 'process' | 'replay') => {
    const cid = crypto.randomUUID()
    navigate(`/claims/${claimId}/runs/${cid}`)
    const post =
      kind === 'process'
        ? runPipeline(claimId, cid)
        : replayPipeline(claimId, cid, REPLAY_VARIANT)
    post
      .then(() => refetch())
      .catch((err: unknown) => {
        queryClient.setQueryData(
          ['runError', cid],
          err instanceof Error ? err.message : String(err),
        )
      })
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
  onProcess,
  onReplay,
}: {
  claim: ClaimRecord
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
          <Button onClick={onProcess}>Process</Button>
        </Tooltip>
        <Tooltip text={tooltips.reprocessV2}>
          <Button
            variant="secondary"
            onClick={onReplay}
            disabled={!REPLAYABLE.has(claim.status)}
          >
            Re-process with v2
          </Button>
        </Tooltip>
      </td>
    </tr>
  )
}
