import type { PipelineEvent } from '../api/types'

interface ProgressStripProps {
  events: PipelineEvent[]
}

const AGENT_LABELS: Record<string, string> = {
  doc_parser: 'Doc-Parser',
  validator: 'Validator',
  adjuster: 'Adjuster',
  guardrail: 'Guardrail',
}

// Renders the agent-by-agent progress of an in-flight run from the SSE event
// stream. Each completed agent shows its headline summary and duration; the
// terminal event shows the outcome (and the variant, surfaced from the start
// event). Functional, not polished — Phase 6 styles this.
export function ProgressStrip({ events }: ProgressStripProps) {
  if (events.length === 0) return null

  const started = events.find((e) => e.event_type === 'pipeline_started')
  const completed = events.find((e) => e.event_type === 'pipeline_completed')
  const aborted = events.find((e) => e.event_type === 'pipeline_aborted')
  const completedAgents = events.filter((e) => e.event_type === 'agent_completed')

  return (
    <div className="rounded border border-slate-200 p-3" aria-label="Run progress">
      <p className="text-sm font-medium">
        Run progress{started?.variant ? ` — variant: ${started.variant}` : ''}
      </p>
      <ol className="mt-2 space-y-1 text-sm">
        {completedAgents.map((event, index) => (
          <li key={`${event.agent}-${index}`} className="flex gap-2">
            <span className="font-mono text-xs text-green-700">✓</span>
            <span className="w-24">{AGENT_LABELS[event.agent ?? ''] ?? event.agent}</span>
            <span className="text-slate-500">
              {JSON.stringify(event.summary ?? {})} · {event.duration_ms}ms
            </span>
          </li>
        ))}
      </ol>
      {completed && (
        <p className="mt-2 text-sm font-semibold" data-testid="run-outcome">
          Outcome: {completed.status}
        </p>
      )}
      {aborted && (
        <p className="mt-2 text-sm font-semibold text-red-700" data-testid="run-outcome">
          Aborted at {aborted.failing_agent}: {aborted.error_type}
        </p>
      )}
    </div>
  )
}
