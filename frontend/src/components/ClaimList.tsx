import type { ClaimRecord } from '../api/types'
import { tooltips } from '../copy/tooltips'
import { Tooltip } from './Tooltip'

const REPLAYABLE = new Set(['settled', 'awaiting_human'])

interface ClaimListProps {
  claims: ClaimRecord[]
  busyClaimId: string | null
  onProcess: (claimId: string) => void
  onReplay: (claimId: string) => void
}

// The claims table. Each row shows the headline fields plus two actions: process
// (runs the default pipeline) and re-process with v2 (a replay variant, enabled
// only once the claim has reached a terminal state). Both carry a tooltip naming
// the production trigger.
export function ClaimList({ claims, busyClaimId, onProcess, onReplay }: ClaimListProps) {
  if (claims.length === 0) {
    return <p className="text-sm text-slate-500">No claims yet — submit one above.</p>
  }
  return (
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
          <tr key={claim.claim_id} className="border-t border-slate-200">
            <td className="py-1">{claim.claimant_name}</td>
            <td>{claim.claim_type}</td>
            <td>{claim.reported_amount}</td>
            <td>
              <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs">
                {claim.status}
              </span>
            </td>
            <td className="space-x-2">
              <Tooltip text={tooltips.processClaim}>
                <button
                  type="button"
                  disabled={busyClaimId === claim.claim_id}
                  className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
                  onClick={() => onProcess(claim.claim_id)}
                >
                  Process
                </button>
              </Tooltip>
              <Tooltip text={tooltips.reprocessV2}>
                <button
                  type="button"
                  disabled={
                    busyClaimId === claim.claim_id || !REPLAYABLE.has(claim.status)
                  }
                  className="rounded border border-slate-400 px-2 py-1 text-xs disabled:opacity-50"
                  onClick={() => onReplay(claim.claim_id)}
                >
                  Re-process with v2
                </button>
              </Tooltip>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
