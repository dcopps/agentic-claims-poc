import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { compareRuns } from '../api/client'
import type { DiffSummary } from '../api/types'
import { Card, Spinner } from '../components/ui'

// Deep-linkable comparison view: the two correlation ids come from the URL, so a
// specific comparison is shareable. The diff fields are highlighted.
export function ComparePage() {
  const { a = '', b = '' } = useParams()
  const compare = useQuery({
    queryKey: ['compare', a, b],
    queryFn: () => compareRuns(a, b),
    retry: false,
  })

  if (compare.isLoading) return <Spinner />
  if (compare.error || !compare.data)
    return <p className="text-red-600">Could not compare these runs.</p>

  return (
    <Card title="Run comparison">
      <DiffTable diff={compare.data.diff} />
    </Card>
  )
}

function DiffTable({ diff }: { diff: DiffSummary }) {
  const hl = (changed: boolean) => (changed ? 'bg-amber-100' : '')
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
        <tr className={hl(diff.settlement_changed)}>
          <td className="py-1">Settlement</td>
          <td>{diff.settlement_a ?? '—'}</td>
          <td>{diff.settlement_b ?? '—'}</td>
        </tr>
        <tr className={hl(diff.escalation_changed)}>
          <td className="py-1">Escalate</td>
          <td>{String(diff.escalate_a)}</td>
          <td>{String(diff.escalate_b)}</td>
        </tr>
        <tr className={hl(diff.guardrail_changed)}>
          <td className="py-1">Guardrail passed</td>
          <td>{String(diff.guardrail_passed_a)}</td>
          <td>{String(diff.guardrail_passed_b)}</td>
        </tr>
        <tr>
          <td className="py-1">Fired rules Δ</td>
          <td colSpan={2}>
            <span className="text-green-700">
              +{diff.fired_rules_added.join(', ') || '∅'}
            </span>{' '}
            <span className="text-red-700">
              −{diff.fired_rules_removed.join(', ') || '∅'}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  )
}
