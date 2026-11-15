import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, listRuns, verifyChain } from '../api/client'
import type { AuditEntry, ChainVerification, RunListItem, RunStatus } from '../api/types'
import { ClaimLine } from '../components/ClaimLine'
import { RecordDialog } from '../components/RecordDialog'
import { Tooltip } from '../components/Tooltip'
import { Button, Card, Spinner } from '../components/ui'
import { WakingNotice } from '../components/WakingNotice'
import { auditCopy } from '../copy/audit'
import { claimCopy, decisionWord } from '../copy/claim'
import { formatDateTime } from '../copy/format'
import { runStatusLabel, variantLabel } from '../copy/labels'
import { tooltips } from '../copy/tooltips'
import { useAuditEntries, useRecentRuns } from '../hooks/queries'
import {
  classifyRunId,
  deriveStartedAt,
  recordHeader,
  rowAuthor,
  rowSentence,
} from './auditDerivation'
import { deriveRunOutcome } from './claimDerivation'
import { deriveClaimId, deriveStatus, deriveVariant } from './runDerivation'

// The most a prefix lookup asks for, so "n runs start with…" counts them all.
const PREFIX_LOOKUP_LIMIT = 100
const WITH_SECONDS = { seconds: true }

// The audit log in words (Prompt 32): a run named by its claim, one sentence
// per record, the chain check in sentences, and each record openable in the
// viewer. The run comes from the address (?correlation_id=), so every link in
// still lands; the finder below writes the same parameter.
export function AuditPage() {
  const [params, setParams] = useSearchParams()
  const cid = params.get('correlation_id') ?? ''
  const load = (id: string) => setParams(id ? { correlation_id: id } : {})
  return (
    <div className="space-y-4">
      <Card title={auditCopy.heading}>
        {/* Keyed by the run so choosing one from the list resets the box to it. */}
        <RunFinder key={cid} current={cid} onLoad={load} />
      </Card>
      {cid ? (
        <RunRecords cid={cid} />
      ) : (
        <p className="text-sm text-slate-500" data-testid="choose-run">
          {auditCopy.chooseRun}
        </p>
      )}
    </div>
  )
}

interface RunFinderProps {
  current: string
  onLoad: (id: string) => void
}

// The Run id box and the Recent runs list. A whole id loads at once; eight or
// more characters are resolved through GET /api/runs?prefix=; fewer never
// leave the page (Dermot, at the gate).
function RunFinder({ current, onLoad }: RunFinderProps) {
  const [input, setInput] = useState(current)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const id = classifyRunId(input)
    if (id.kind === 'full') return onLoad(id.value)
    if (id.kind === 'too_short') return setMessage(auditCopy.tooShort)
    if (id.kind === 'invalid') return setMessage(auditCopy.invalidId)
    setBusy(true)
    setMessage(null)
    const found = await resolveShortId(id.value)
    setBusy(false)
    if (found.load) onLoad(found.load)
    else setMessage(found.message ?? null)
  }

  return (
    <div className="space-y-3 text-sm">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <label className="block">
          <span className="block text-slate-500">{auditCopy.runIdLabel}</span>
          <input
            className="w-96 rounded border border-slate-300 px-2 py-1 font-mono text-xs"
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </label>
        <Button type="submit" variant="secondary" disabled={busy}>
          {busy ? auditCopy.resolving : auditCopy.load}
        </Button>
        <span className="text-xs text-slate-500">{auditCopy.runIdHint}</span>
      </form>
      {message && (
        <p className="text-slate-600" role="status" data-testid="finder-message">
          {message}
        </p>
      )}
      <RecentRuns />
    </div>
  )
}

// Eight or more characters of a run id, resolved through the backend: exactly
// one match loads; none or several is said in a sentence.
async function resolveShortId(prefix: string): Promise<{ load?: string; message?: string }> {
  try {
    const runs = await listRuns({ prefix, limit: PREFIX_LOOKUP_LIMIT })
    if (runs.length === 1) return { load: runs[0].correlation_id }
    if (runs.length === 0) return { message: auditCopy.noneStartWith(prefix) }
    return { message: auditCopy.severalStartWith(runs.length, prefix) }
  } catch {
    return { message: auditCopy.loadFailed }
  }
}

// The twenty latest runs across every claim, each line a link to its audit log.
function RecentRuns() {
  const runs = useRecentRuns()
  return (
    <div>
      <h3 className="text-slate-500">{auditCopy.recentHeading}</h3>
      {runs.isLoading && <Spinner />}
      {runs.isError && <p className="text-red-600">{auditCopy.recentLoadFailed}</p>}
      {runs.data && runs.data.length === 0 && <p className="text-slate-500">{auditCopy.noRuns}</p>}
      {runs.data && runs.data.length > 0 && (
        <ul className="space-y-0.5" aria-label={auditCopy.recentHeading}>
          {runs.data.map((run) => (
            <li key={run.correlation_id}>
              <Link
                to={`/audit?correlation_id=${run.correlation_id}`}
                className="text-blue-700 hover:underline"
              >
                {recentLine(run)}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function recentLine(run: RunListItem): string {
  const outcome = run.human_decision ? decisionWord(run.human_decision) : runStatusLabel(run.status)
  return auditCopy.recentLine(
    run.claimant_name,
    run.claim_number,
    variantLabel(run.variant),
    formatDateTime(run.started_at),
    outcome,
  )
}

// The run's records: the claim and run lines, the table, the chain check.
function RunRecords({ cid }: { cid: string }) {
  const audit = useAuditEntries(cid)
  const rows = audit.data ?? []
  const claimId = deriveClaimId(rows, []) ?? ''
  if (audit.isLoading) {
    return (
      <div className="space-y-1">
        <Spinner label={auditCopy.loading} />
        <WakingNotice waiting />
      </div>
    )
  }
  if (audit.isError) {
    const notFound = audit.error instanceof ApiError && audit.error.status === 404
    return (
      <p className="text-sm text-slate-500" data-testid="records-state">
        {notFound ? auditCopy.unknownId : auditCopy.loadFailed}
      </p>
    )
  }
  return (
    <>
      <RunHeading cid={cid} claimId={claimId} rows={rows} />
      <RecordsTable cid={cid} rows={rows} />
    </>
  )
}

// Which claim and which run: the claimant as the link, the claim in words, then
// the kind of run, when it started, and its outcome in the run page's words.
function RunHeading({ cid, claimId, rows }: { cid: string; claimId: string; rows: AuditEntry[] }) {
  const status = (deriveStatus(rows, []) ?? 'running') as RunStatus
  const outcome = claimCopy.runOutcome(deriveRunOutcome(status, rows))
  const started = deriveStartedAt(rows)
  return (
    <Card>
      <div className="space-y-1 text-sm">
        <ClaimLine claimId={claimId} />
        <p className="text-slate-600" data-testid="audit-run-line">
          {auditCopy.runLine(
            variantLabel(deriveVariant(rows, [])),
            started ? formatDateTime(started, WITH_SECONDS) : '',
            outcome,
          )}
          {claimId && (
            <>
              {' · '}
              <Link to={`/claims/${claimId}/runs/${cid}`} className="text-blue-700 hover:underline">
                {auditCopy.openRun}
              </Link>
            </>
          )}
        </p>
      </div>
    </Card>
  )
}

// One row per record; a row opens its record in the viewer.
function RecordsTable({ cid, rows }: { cid: string; rows: AuditEntry[] }) {
  const [selected, setSelected] = useState<AuditEntry | null>(null)
  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-3">
          {auditCopy.recordsHeading}
          <VerifyChain cid={cid} />
        </span>
      }
    >
      <table className="w-full text-left text-sm" aria-label={auditCopy.recordsHeading}>
        <thead className="text-slate-500">
          <tr>
            <th className="py-1 pr-2">{auditCopy.columns.when}</th>
            <th className="px-2 py-1">{auditCopy.columns.who}</th>
            <th className="px-2 py-1">{auditCopy.columns.what}</th>
            <th className="py-1 pl-2">
              <Tooltip text={tooltips.chainHash} label={auditCopy.aboutRecords}>
                <span>{auditCopy.columns.record}</span>
              </Tooltip>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((entry) => (
            <RecordRow key={entry.audit_id} entry={entry} onOpen={() => setSelected(entry)} />
          ))}
        </tbody>
      </table>
      {selected && (
        <RecordDialog
          entry={selected}
          header={recordHeader(selected)}
          onClose={() => setSelected(null)}
        />
      )}
    </Card>
  )
}

function RecordRow({ entry, onOpen }: { entry: AuditEntry; onOpen: () => void }) {
  return (
    <tr className="cursor-pointer border-t border-slate-200 hover:bg-slate-50" onClick={onOpen}>
      <td className="whitespace-nowrap py-1 pr-2 text-slate-600">
        {formatDateTime(entry.created_at, WITH_SECONDS)}
      </td>
      <td className="whitespace-nowrap px-2 py-1">{rowAuthor(entry)}</td>
      <td className="px-2 py-1">
        <button
          type="button"
          aria-label={auditCopy.openRecord(entry.audit_id)}
          className="text-left text-slate-700 hover:underline"
        >
          {rowSentence(entry)}
        </button>
      </td>
      <td className="whitespace-nowrap py-1 pl-2 font-mono text-xs text-slate-400">
        {auditCopy.recordCell(entry.audit_id, entry.chain_hash)}
      </td>
    </tr>
  )
}

// The chain check over the whole ledger (the hash chain spans every row, so a
// break anywhere matters), with its result in a sentence.
function VerifyChain({ cid }: { cid: string }) {
  const [result, setResult] = useState<ChainVerification | null>(null)
  const [state, setState] = useState<'idle' | 'busy' | 'failed'>('idle')
  const verify = async () => {
    setState('busy')
    try {
      setResult(await verifyChain(cid))
      setState('idle')
    } catch {
      setState('failed')
    }
  }
  return (
    <>
      <Tooltip text={tooltips.verifyChain}>
        <Button size="sm" onClick={verify} disabled={state === 'busy'}>
          {state === 'busy' ? auditCopy.verifying : auditCopy.verify}
        </Button>
      </Tooltip>
      {state === 'failed' && (
        <span
          className="text-sm font-normal text-red-700"
          role="status"
          data-testid="verify-result"
        >
          {auditCopy.verifyFailed}
        </span>
      )}
      {state !== 'failed' && result && (
        <span
          className={`text-sm font-normal ${result.ok ? 'text-green-700' : 'text-red-700'}`}
          role="status"
          data-testid="verify-result"
        >
          {result.ok
            ? auditCopy.verified(result.rows_checked)
            : auditCopy.breakAt(result.first_break?.audit_id ?? 0, result.first_break?.kind ?? '')}
        </span>
      )}
    </>
  )
}
