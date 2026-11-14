import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { replayPipeline, runPipeline } from '../api/client'
import type { ClaimRecord } from '../api/types'
import { ClaimForm } from '../components/ClaimForm'
import { Tooltip } from '../components/Tooltip'
import { Button, Card, Spinner, StatusBadge } from '../components/ui'
import { WakingNotice } from '../components/WakingNotice'
import { claimsCopy } from '../copy/claims'
import { formatDateTime, formatUsd } from '../copy/format'
import { guideCopy } from '../copy/guide'
import { claimStatusLabel, claimTypeLabel } from '../copy/labels'
import { disabledClosed, tooltips } from '../copy/tooltips'
import { useClaims } from '../hooks/queries'

// The statuses after which a strict re-run is offered. `aborted` is not among
// them: a claim is stored `aborted` only by a person's rejection, and a decided
// claim is closed to further runs (Prompt 31), so it could never enable the button.
const REPLAYABLE = new Set(['settled', 'awaiting_human'])
// The second action: the same claim again under the strict-Validator variant,
// so the two runs can be compared on the claim's page.
const REPLAY_VARIANT = 'v2_strict_validator'

type RunKind = 'process' | 'replay'
type Trigger = (claimId: string, kind: RunKind) => void

export function ClaimsPage() {
  const { data: claims, isLoading, error } = useClaims()
  const queryClient = useQueryClient()
  const refetch = () => queryClient.invalidateQueries({ queryKey: ['claims'] })
  const trigger = useRunTrigger(refetch)

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
        <WakingNotice waiting={isLoading} />
        {error && <p className="text-sm text-red-600">{claimsCopy.loadFailed}</p>}
        {claims && claims.length === 0 && (
          <p className="text-sm text-slate-500">{claimsCopy.noClaims}</p>
        )}
        {claims && claims.length > 0 && <ClaimsTable claims={claims} onTrigger={trigger} />}
      </Card>
    </div>
  )
}

// Navigate to the run-detail page FIRST so its SSE subscription is open before
// the run emits events (the event bus buffers late subscribers, so this is
// safe), then fire the POST without awaiting — the ~27s run is observed live
// rather than blocking the navigation. A failed POST writes the error to a
// run-scoped cache key the run-detail page renders (fix #6); a successful one
// calls `onStarted` (the claims list refreshes).
function useRunTrigger(onStarted: () => unknown): Trigger {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return (claimId, kind) => {
    const cid = crypto.randomUUID()
    // `started` tells the run page this run began here, so it shows the awaiting
    // hint rather than "Run not found" while the first event is on its way.
    navigate(`/claims/${claimId}/runs/${cid}`, { state: { started: true } })
    const post =
      kind === 'process' ? runPipeline(claimId, cid) : replayPipeline(claimId, cid, REPLAY_VARIANT)
    post
      .then(() => onStarted())
      .catch((err: unknown) => {
        queryClient.setQueryData(
          ['runError', cid],
          err instanceof Error ? err.message : String(err),
        )
      })
  }
}

// One confirmation may be open at a time (Prompt 31): the open row is table
// state, so opening another row's question closes the first.
function ClaimsTable({ claims, onTrigger }: { claims: ClaimRecord[]; onTrigger: Trigger }) {
  const [confirming, setConfirming] = useState<string | null>(null)
  return (
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
            confirming={confirming === claim.claim_id}
            onConfirming={(open) => setConfirming(open ? claim.claim_id : null)}
            onTrigger={(kind) => onTrigger(claim.claim_id, kind)}
          />
        ))}
      </tbody>
    </table>
  )
}

interface RowProps {
  claim: ClaimRecord
  confirming: boolean
  onConfirming: (open: boolean) => void
  onTrigger: (kind: RunKind) => void
}

function ClaimRow({ claim, confirming, onConfirming, onTrigger }: RowProps) {
  return (
    <tr className="border-t border-slate-200">
      <td className="whitespace-nowrap py-1.5 pr-2">
        <Link to={`/claims/${claim.claim_id}`} className="text-blue-700 hover:underline">
          {claim.claimant_name}
        </Link>
        {/* The claim number as a second line in the same cell: no new column, so the
            table keeps the width measured in Prompt 28 (Prompt 30 addition). */}
        <span className="block font-mono text-xs text-slate-500" data-testid="claim-number">
          {claim.claim_number}
        </span>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5">{claimTypeLabel(claim.claim_type)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{formatUsd(claim.reported_amount)}</td>
      <td className="px-2 py-1.5">
        <StatusBadge status={claim.status} label={claimStatusLabel(claim.status)} />
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-slate-600">
        {formatDateTime(claim.created_at)}
      </td>
      <RowActions
        claim={claim}
        confirming={confirming}
        onConfirming={onConfirming}
        onTrigger={onTrigger}
      />
    </tr>
  )
}

// The two actions and their reasons (Prompt 31). The primary reads Process until
// the claim has had a run, then Run again; on a settled claim it asks once
// first. A claim a person has decided is closed: both buttons are disabled with
// the reason leading the tooltip, and the backend would refuse the run anyway.
function RowActions({ claim, confirming, onConfirming, onTrigger }: RowProps) {
  const closed = claim.human_decision !== null
  const closedReason = claim.human_decision ? disabledClosed(claim.human_decision) : ''
  const canRerun = !closed && REPLAYABLE.has(claim.status)
  const primary = () => (claim.status === 'settled' ? onConfirming(true) : onTrigger('process'))
  return (
    <td className="relative whitespace-nowrap py-1.5 pl-2" data-testid="claim-actions">
      <Tooltip text={closedReason + tooltips.processClaim}>
        <Button size="sm" onClick={primary} disabled={closed} aria-disabled={closed}>
          {claim.status === 'received' ? claimsCopy.process : claimsCopy.runAgain}
        </Button>
      </Tooltip>{' '}
      {/* The disabled reason leads the tooltip, so a visitor can tell why (Prompt 28). */}
      <Tooltip
        text={
          (closed ? closedReason : canRerun ? '' : tooltips.disabledNoFinishedRun) +
          tooltips.strictRerun
        }
      >
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onTrigger('replay')}
          disabled={!canRerun}
          aria-disabled={!canRerun}
        >
          {claimsCopy.strictRerun}
        </Button>
      </Tooltip>
      {confirming && (
        <ConfirmRerun
          onConfirm={() => {
            onConfirming(false)
            onTrigger('process')
          }}
          onCancel={() => onConfirming(false)}
        />
      )}
    </td>
  )
}

// The question before a settled claim is run again, anchored below the actions
// so the row keeps its height and the table its width (plan D2). It closes on
// either button, on Escape, and on a click anywhere outside it.
function ConfirmRerun({ onConfirm, onCancel }: { onConfirm: () => void; onCancel: () => void }) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (panel.current && !panel.current.contains(event.target as Node)) onCancel()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [onCancel])
  return (
    <div
      ref={panel}
      role="group"
      aria-label={claimsCopy.confirmRerun}
      data-testid="confirm-rerun"
      className="absolute right-0 top-full z-20 mt-1 flex items-center gap-2 whitespace-nowrap rounded border border-slate-300 bg-white px-3 py-2 text-xs text-slate-700 shadow"
    >
      <span>{claimsCopy.confirmRerun}</span>
      <Button size="sm" onClick={onConfirm}>
        {claimsCopy.confirm}
      </Button>
      <Button variant="secondary" size="sm" onClick={onCancel}>
        {claimsCopy.cancel}
      </Button>
    </div>
  )
}
