import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { AuditEntry, ClaimRecord, RunSummary } from '../api/types'
import { DecisionCard } from '../components/DecisionCard'
import { HumanReviewPanel } from '../components/HumanReviewPanel'
import { Sentence } from '../components/Sentence'
import { Tooltip } from '../components/Tooltip'
import { Badge, Button, Card, Spinner, StatusBadge } from '../components/ui'
import { WakingNotice } from '../components/WakingNotice'
import { claimCopy, type Segment } from '../copy/claim'
import { formatDate, formatDateTime, formatUsd } from '../copy/format'
import { claimStatusLabel, claimTypeLabel, runStatusLabel, variantLabel } from '../copy/labels'
import { tooltips } from '../copy/tooltips'
import { useAuditEntries, useClaim, useClaimRuns } from '../hooks/queries'
import { deriveDecision, deriveRunOutcome, deriveStoppedAt, latestRun } from './claimDerivation'

// The claim page (Phase 6; rewritten by Prompt 30): the record in plain words,
// the runs by the time they started, and in between either the human review
// panel or the Decision card. The latest run's audit rows are fetched once here
// and passed to everything that reads them (plan D2); a claim never run fetches
// none.
export function ClaimDetailPage() {
  const { claimId = '' } = useParams()
  const claim = useClaim(claimId)
  const runs = useClaimRuns(claimId)
  const latest = latestRun(runs.data ?? [])
  const audit = useAuditEntries(latest?.correlation_id ?? '', latest !== undefined)
  const rows = audit.data ?? []

  if (claim.isLoading) {
    return (
      <div className="space-y-1">
        <Spinner />
        <WakingNotice waiting />
      </div>
    )
  }
  if (claim.error || !claim.data) return <p className="text-red-600">{claimCopy.notFound}</p>

  return (
    <div className="space-y-6">
      <p className="text-sm">
        <Link to="/" className="text-blue-700 hover:underline">
          {claimCopy.backToClaims}
        </Link>
      </p>
      <ClaimCard claim={claim.data} latest={latest} rows={rows} />
      <Outcome claim={claim.data} latest={latest} rows={rows} loading={audit.isLoading} />
      <Card title={claimCopy.runsHeading}>
        {runs.isLoading && <Spinner />}
        <WakingNotice waiting={runs.isLoading} />
        {runs.data?.length === 0 && (
          <p className="text-sm text-slate-600" data-testid="no-runs">
            <Sentence segments={claimCopy.noRuns} />
          </p>
        )}
        {runs.data && runs.data.length > 0 && (
          <RunsList claimId={claimId} runs={runs.data} rows={rows} />
        )}
      </Card>
    </div>
  )
}

function runPath(claimId: string, correlationId: string): string {
  return `/claims/${claimId}/runs/${correlationId}`
}

interface RowsProps {
  claim: ClaimRecord
  latest: RunSummary | undefined
  rows: AuditEntry[]
}

// Identifiers keep the monospace face; words, amounts and dates are ordinary
// text. Labels follow the form's where it has the field.
function ClaimCard({ claim, latest, rows }: RowsProps) {
  const f = claimCopy.fields
  return (
    <Card title={claim.claimant_name}>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <Field label={f.claimNumber} value={claim.claim_number} mono />
        <Field label={f.policyNumber} value={claim.policy_number} mono />
        <Field label={f.claimType} value={claimTypeLabel(claim.claim_type)} />
        <Field label={f.reportedAmount} value={formatUsd(claim.reported_amount)} />
        <Field label={f.jurisdiction} value={claim.jurisdiction} />
        <Field label={f.lossDate} value={formatDate(claim.loss_date)} />
        <Field label={f.reportedDate} value={formatDate(claim.reported_date)} />
        <Field label={f.submitted} value={formatDateTime(claim.created_at)} />
        <StatusField claim={claim} latest={latest} rows={rows} />
        <div className="col-span-2">
          <dt className="text-slate-500">{f.description}</dt>
          <dd className="text-slate-700">{claim.narrative}</dd>
        </div>
      </dl>
    </Card>
  )
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-slate-500">{label}</dt>
      <dd className={mono ? 'font-mono text-xs text-slate-700' : 'text-slate-700'}>{value}</dd>
    </div>
  )
}

function StatusField({ claim, latest, rows }: RowsProps) {
  const line = statusLine(claim, latest, rows)
  return (
    <div className="col-span-2">
      <dt className="text-slate-500">{claimCopy.fields.status}</dt>
      <dd className="flex flex-wrap items-center gap-2">
        <StatusBadge status={claim.status} label={claimStatusLabel(claim.status)} />
        {line && (
          <span className="text-slate-700" data-testid="claim-status-line">
            <Sentence segments={line} />
          </span>
        )}
      </dd>
    </div>
  )
}

// The one line beside the badge, when the badge alone would mislead: a run is
// still going, or the latest run broke and left the status where it got to.
// The terminal statuses and a person's decision speak for themselves.
function statusLine(
  claim: ClaimRecord,
  latest: RunSummary | undefined,
  rows: AuditEntry[],
): Segment[] | null {
  if (!latest) return null
  const to = runPath(claim.claim_id, latest.correlation_id)
  if (latest.status === 'running') return claimCopy.runInProgress(to)
  const stoppedAt = deriveStoppedAt(claim.status, rows)
  return stoppedAt ? claimCopy.stoppedAt(stoppedAt, to) : null
}

// The review panel while a person's decision is awaited; the Decision card once
// the latest run's rows hold one; nothing otherwise.
function Outcome({ claim, latest, rows, loading }: RowsProps & { loading: boolean }) {
  if (!latest) return null
  if (claim.status === 'awaiting_human') {
    return (
      <HumanReviewPanel
        claimId={claim.claim_id}
        correlationId={latest.correlation_id}
        rows={rows}
        loading={loading}
      />
    )
  }
  const decision = deriveDecision(rows)
  if (!decision) return null
  return (
    <DecisionCard decision={decision} runPath={runPath(claim.claim_id, latest.correlation_id)} />
  )
}

interface RunsListProps {
  claimId: string
  runs: RunSummary[]
  rows: AuditEntry[]
}

// Newest first, as the API orders them. Only the first line has rows to draw
// on, so only it can say "Settled at $82,500"; the others carry the outcome
// word (plan D1). Ticking a third run drops the earliest tick, so the compare
// button needs exactly two.
function RunsList({ claimId, runs, rows }: RunsListProps) {
  const [picked, setPicked] = useState<string[]>([])
  const navigate = useNavigate()
  const toggle = (cid: string) =>
    setPicked((prev) =>
      prev.includes(cid) ? prev.filter((x) => x !== cid) : [...prev, cid].slice(-2),
    )
  const ready = picked.length === 2
  return (
    <div className="space-y-2 text-sm">
      {runs.length >= 2 && (
        <CompareControls
          ready={ready}
          onCompare={() => navigate(`/claims/${claimId}/compare/${picked[0]}/${picked[1]}`)}
        />
      )}
      <ul className="space-y-1" aria-label="Runs">
        {runs.map((run, index) => (
          <RunLine
            key={run.correlation_id}
            run={run}
            claimId={claimId}
            isLatest={index === 0}
            outcome={
              index === 0
                ? claimCopy.runOutcome(deriveRunOutcome(run.status, rows))
                : runStatusLabel(run.status)
            }
            picked={picked.includes(run.correlation_id)}
            onToggle={() => toggle(run.correlation_id)}
          />
        ))}
      </ul>
    </div>
  )
}

// The hint and the button share a line; the disabled reason leads the tooltip,
// as on the Claims page.
function CompareControls({ ready, onCompare }: { ready: boolean; onCompare: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-slate-600" data-testid="compare-hint">
        {claimCopy.compareHint}
      </p>
      <Tooltip text={(ready ? '' : tooltips.disabledCompareNeedsTwo) + tooltips.compareSelected}>
        <Button
          variant="secondary"
          size="sm"
          onClick={onCompare}
          disabled={!ready}
          aria-disabled={!ready}
        >
          {claimCopy.compareSelected}
        </Button>
      </Tooltip>
    </div>
  )
}

interface RunLineProps {
  run: RunSummary
  claimId: string
  isLatest: boolean
  outcome: string
  picked: boolean
  onToggle: () => void
}

function RunLine({ run, claimId, isLatest, outcome, picked, onToggle }: RunLineProps) {
  const startedAt = formatDateTime(run.started_at)
  return (
    <li className="flex flex-wrap items-center gap-2" data-testid="run-line">
      <input
        type="checkbox"
        aria-label={claimCopy.selectRun(startedAt)}
        checked={picked}
        onChange={onToggle}
      />
      <Link to={runPath(claimId, run.correlation_id)} className="text-blue-700 hover:underline">
        {startedAt}
      </Link>
      {isLatest && <Badge>{claimCopy.latest}</Badge>}
      <span className="text-slate-700">{variantLabel(run.variant)}</span>
      <Dot />
      <span className="text-slate-700">{outcome}</span>
      <span className="font-mono text-xs text-slate-400">{run.correlation_id.slice(0, 8)}</span>
      <Link
        to={`/audit?correlation_id=${run.correlation_id}`}
        className="text-xs text-blue-600 hover:underline"
      >
        {claimCopy.auditLog}
      </Link>
    </li>
  )
}

function Dot() {
  return <span className="text-slate-400">·</span>
}
