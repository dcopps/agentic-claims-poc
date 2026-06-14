import { useState } from 'react'
import { compareRuns, listClaimRuns } from '../api/client'
import type { ClaimRecord, RunComparison, RunSummary } from '../api/types'

interface CompareViewProps {
  claims: ClaimRecord[]
}

// Side-by-side run comparison. Pick a claim, pick two of its runs, and the diff
// fields are highlighted. Reconstruction is server-side; this view just renders
// the typed RunComparison.
export function CompareView({ claims }: CompareViewProps) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [runA, setRunA] = useState('')
  const [runB, setRunB] = useState('')
  const [comparison, setComparison] = useState<RunComparison | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadRuns = async (claimId: string) => {
    setComparison(null)
    setRunA('')
    setRunB('')
    setError(null)
    if (!claimId) {
      setRuns([])
      return
    }
    try {
      setRuns(await listClaimRuns(claimId))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const doCompare = async () => {
    setError(null)
    try {
      setComparison(await compareRuns(runA, runB))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <section className="space-y-3" aria-label="Compare runs">
      <select
        aria-label="Select a claim"
        className="rounded border border-slate-300 px-2 py-1"
        onChange={(e) => loadRuns(e.target.value)}
        defaultValue=""
      >
        <option value="">Select a claim…</option>
        {claims.map((claim) => (
          <option key={claim.claim_id} value={claim.claim_id}>
            {claim.claimant_name} — {claim.claim_type}
          </option>
        ))}
      </select>

      {runs.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <RunSelect label="Run A" runs={runs} value={runA} onChange={setRunA} />
          <RunSelect label="Run B" runs={runs} value={runB} onChange={setRunB} />
          <button
            type="button"
            disabled={!runA || !runB || runA === runB}
            className="rounded bg-slate-800 px-3 py-1 text-sm text-white disabled:opacity-50"
            onClick={doCompare}
          >
            Compare
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
      {comparison && <DiffTable comparison={comparison} />}
    </section>
  )
}

function RunSelect({
  label,
  runs,
  value,
  onChange,
}: {
  label: string
  runs: RunSummary[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <select
      aria-label={label}
      className="rounded border border-slate-300 px-2 py-1 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{label}…</option>
      {runs.map((run) => (
        <option key={run.correlation_id} value={run.correlation_id}>
          {run.variant} · {run.status} · {run.correlation_id.slice(0, 8)}
        </option>
      ))}
    </select>
  )
}

function DiffTable({ comparison }: { comparison: RunComparison }) {
  const { diff } = comparison
  const highlight = (changed: boolean) => (changed ? 'bg-amber-100' : '')
  return (
    <table className="w-full text-left text-sm" aria-label="Comparison diff">
      <thead className="text-slate-500">
        <tr>
          <th className="py-1">Field</th>
          <th>Run A</th>
          <th>Run B</th>
        </tr>
      </thead>
      <tbody>
        <tr className={highlight(diff.settlement_changed)}>
          <td className="py-1">Settlement</td>
          <td>{diff.settlement_a ?? '—'}</td>
          <td>{diff.settlement_b ?? '—'}</td>
        </tr>
        <tr className={highlight(diff.escalation_changed)}>
          <td className="py-1">Escalate</td>
          <td>{String(diff.escalate_a)}</td>
          <td>{String(diff.escalate_b)}</td>
        </tr>
        <tr className={highlight(diff.guardrail_changed)}>
          <td className="py-1">Guardrail passed</td>
          <td>{String(diff.guardrail_passed_a)}</td>
          <td>{String(diff.guardrail_passed_b)}</td>
        </tr>
        <tr>
          <td className="py-1">Fired rules Δ</td>
          <td colSpan={2}>
            <span className="text-green-700">+{diff.fired_rules_added.join(', ') || '∅'}</span>
            {'  '}
            <span className="text-red-700">−{diff.fired_rules_removed.join(', ') || '∅'}</span>
          </td>
        </tr>
      </tbody>
    </table>
  )
}
