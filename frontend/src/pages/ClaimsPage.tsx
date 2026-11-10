import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { replayPipeline, runPipeline } from '../api/client'
import type { ClaimRecord } from '../api/types'
import { ClaimForm } from '../components/ClaimForm'
import { Tooltip } from '../components/Tooltip'
import { formatDateTime, formatUsd } from '../copy/format'
import { claimTypeLabel, statusLabel } from '../copy/labels'
import { Button, Card, Spinner, StatusBadge } from '../components/ui'
import { guideCopy } from '../copy/guide'
import { tooltips } from '../copy/tooltips'
import { useClaims } from '../hooks/queries'

const REPLAYABLE = new Set(['settled', 'awaiting_human', 'aborted'])
// The second action: the same claim again under the strict-Validator variant,
// so the two runs can be compared on the claim's page.
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
      kind === 'process' ? runPipeline(claimId, cid) : replayPipeline(claimId, cid, REPLAY_VARIANT)
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
        {/* The first line a visitor reads: the data is synthetic and the site is
            public, so no real personal details (Prompt 26). */}
        <p className="mb-3 text-sm text-slate-600">{guideCopy.dataNotice}</p>
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
            {/* Cell padding sized so the table fits the card at the 1024 px main (measured on Azure);
                the claimant, type, status badge and the two actions never wrap (Prompt 28). */}
            <thead className="text-slate-500">
              <tr>
                <th className="py-1.5 pr-2">Claimant</th>
                <th className="px-2 py-1.5">Type</th>
                <th className="px-2 py-1.5 text-right">Amount</th>
                <th className="px-2 py-1.5">Status</th>
                <th className="px-2 py-1.5">Submitted</th>
                <th className="py-1.5 pl-2">Actions</th>
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
  const canRerun = REPLAYABLE.has(claim.status)
  return (
    <tr className="border-t border-slate-200">
      <td className="whitespace-nowrap py-1.5 pr-2">
        <Link to={`/claims/${claim.claim_id}`} className="text-blue-700 hover:underline">
          {claim.claimant_name}
        </Link>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5">{claimTypeLabel(claim.claim_type)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{formatUsd(claim.reported_amount)}</td>
      <td className="px-2 py-1.5">
        <StatusBadge status={claim.status} label={statusLabel(claim.status)} />
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-slate-600">
        {formatDateTime(claim.created_at)}
      </td>
      <td className="whitespace-nowrap py-1.5 pl-2" data-testid="claim-actions">
        <Tooltip text={tooltips.processClaim}>
          <Button size="sm" onClick={onProcess}>
            Process
          </Button>
        </Tooltip>{' '}
        {/* The disabled reason leads the tooltip, so a visitor can tell why (Prompt 28). */}
        <Tooltip text={(canRerun ? '' : tooltips.disabledNoFinishedRun) + tooltips.strictRerun}>
          <Button
            variant="secondary"
            size="sm"
            onClick={onReplay}
            disabled={!canRerun}
            aria-disabled={!canRerun}
          >
            Strict re-run
          </Button>
        </Tooltip>
      </td>
    </tr>
  )
}
