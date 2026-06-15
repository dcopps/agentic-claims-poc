import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { verifyChain } from '../api/client'
import type { AuditEntry, ChainVerification } from '../api/types'
import { Tooltip } from '../components/Tooltip'
import { Badge, Button, Card, JsonBlock, Spinner } from '../components/ui'
import { tooltips } from '../copy/tooltips'
import { useAuditEntries } from '../hooks/queries'

// Audit-log viewer. The correlation_id comes from the URL query (?correlation_id=)
// and is editable inline. The "Verify chain" button verifies the WHOLE audit
// ledger, not just this run — the hash chain spans every row, so a break anywhere
// matters. The copy says so explicitly.
export function AuditPage() {
  const [params, setParams] = useSearchParams()
  const cid = params.get('correlation_id') ?? ''
  const [input, setInput] = useState(cid)

  return (
    <div className="space-y-4">
      <Card title="Audit log">
        <div className="flex items-end gap-2">
          <label className="text-sm">
            <span className="block text-slate-500">Correlation id</span>
            <input
              aria-label="Correlation id"
              className="w-96 rounded border border-slate-300 px-2 py-1 font-mono text-xs"
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
          </label>
          <Button
            variant="secondary"
            onClick={() => setParams(input ? { correlation_id: input } : {})}
          >
            Load
          </Button>
        </div>
      </Card>
      {cid && <AuditContent cid={cid} />}
    </div>
  )
}

function AuditContent({ cid }: { cid: string }) {
  const audit = useAuditEntries(cid)
  const [verification, setVerification] = useState<ChainVerification | null>(null)
  const [verifying, setVerifying] = useState(false)

  const verify = async () => {
    setVerifying(true)
    try {
      setVerification(await verifyChain(cid))
    } finally {
      setVerifying(false)
    }
  }

  return (
    <Card
      title={
        <span className="flex items-center gap-3">
          Entries
          <Tooltip text={tooltips.verifyChain}>
            <Button onClick={verify} disabled={verifying}>
              Verify chain (whole ledger)
            </Button>
          </Tooltip>
          {verification && <VerifyResult result={verification} />}
        </span>
      }
    >
      {audit.isLoading && <Spinner />}
      {audit.error && <p className="text-sm text-red-600">No entries for this id.</p>}
      {audit.data && (
        <table className="w-full text-left text-sm" aria-label="Audit entries">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1">Time</th>
              <th>Agent</th>
              <th>Step</th>
              <th>Chain hash</th>
            </tr>
          </thead>
          <tbody>
            {audit.data.map((entry) => (
              <AuditRow key={entry.audit_id} entry={entry} />
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}

function VerifyResult({ result }: { result: ChainVerification }) {
  if (result.ok)
    return (
      <Badge tone="success">Chain verified · {result.rows_checked} rows (whole ledger)</Badge>
    )
  return (
    <Badge tone="danger">
      Chain break at audit_id {result.first_break?.audit_id} ({result.first_break?.kind})
    </Badge>
  )
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr
        className="cursor-pointer border-t border-slate-200 hover:bg-slate-50"
        onClick={() => setOpen((v) => !v)}
      >
        <td className="py-1 font-mono text-xs">{entry.created_at.slice(11, 19)}</td>
        <td>{entry.agent}</td>
        <td>{entry.step}</td>
        <td className="font-mono text-xs text-slate-400">{entry.chain_hash.slice(0, 12)}…</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={4} className="px-2 pb-2">
            <JsonBlock value={entry.payload} />
          </td>
        </tr>
      )}
    </>
  )
}
