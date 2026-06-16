import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import type { AuditEntry, PipelineEvent } from '../api/types'
import { AgentCard, type AgentStatus } from '../components/AgentCard'
import { Card, CopyButton, ErrorBanner, StatusBadge } from '../components/ui'
import { useAuditEntries, useRun } from '../hooks/queries'
import { useRunStream } from '../hooks/useRunStream'

// The four agents in pipeline order, with their SSE name, display label, and the
// audit step their response lands under.
const AGENTS = [
  { key: 'doc_parser', label: 'Doc-Parser', step: 'doc_extract' },
  { key: 'validator', label: 'Validator', step: 'coverage_check' },
  { key: 'adjuster', label: 'Adjuster', step: 'settlement_estimate' },
  { key: 'guardrail', label: 'Guardrail', step: 'output_check' },
]

export function RunDetailPage() {
  const { claimId = '', correlationId = '' } = useParams()
  const events = useRunStream(correlationId, claimId)
  const run = useRun(correlationId)
  const audit = useAuditEntries(correlationId)
  // Subscribe to the run-scoped error the ClaimsPage trigger writes on a POST
  // failure (fix #6). enabled:false — nothing fetches; this only re-renders when
  // setQueryData(['runError', cid], …) fires.
  const runError = useQuery<string | null>({
    queryKey: ['runError', correlationId],
    queryFn: async () => null,
    enabled: false,
  }).data

  const variant = _variant(events, audit.data)
  const completed = events.find((e) => e.event_type === 'pipeline_completed')
  const aborted = events.find((e) => e.event_type === 'pipeline_aborted')
  const status = completed?.status ?? (aborted ? 'aborted' : run.data?.status)
  // Before the first SSE event, the runs/audit queries 404 (the run hasn't
  // written anything yet) — that is expected in-flight state, not an error.
  const awaiting = events.length === 0 && !completed && !aborted && !runError

  return (
    <div className="space-y-4">
      <Card title="Pipeline run">
        <div className="space-y-2 text-sm text-slate-500">
          <p>
            variant: <span className="font-mono">{variant}</span>
            {status && (
              <>
                {' · '}
                <StatusBadge status={status} />
              </>
            )}
          </p>
          {/* Full correlation id, copyable, with a one-click jump to the audit
              view of this same run (filter pre-populated via the query param). */}
          <div className="flex flex-wrap items-center gap-2">
            <span>run</span>
            <span className="break-all font-mono text-xs text-slate-700">
              {correlationId}
            </span>
            <CopyButton value={correlationId} />
            <Link
              to={`/audit?correlation_id=${correlationId}`}
              className="text-xs text-blue-600 hover:underline"
            >
              View audit log
            </Link>
          </div>
        </div>
      </Card>

      {runError && <ErrorBanner message={`Could not start the run: ${runError}`} />}
      {aborted && (
        <ErrorBanner
          message={`Pipeline aborted at ${aborted.failing_agent}: ${aborted.error_type}${aborted.message ? ` — ${aborted.message}` : ''}`}
        />
      )}
      {awaiting && (
        <p className="text-sm text-slate-500" data-testid="awaiting-hint">
          Awaiting pipeline_started…
        </p>
      )}

      <div className="space-y-2" aria-label="Pipeline agents">
        {AGENTS.map((agent) => (
          <AgentCard
            key={agent.key}
            agent={agent.key}
            label={agent.label}
            variant={variant}
            status={_status(agent.key, events)}
            durationMs={_duration(agent.key, events)}
            summary={_summary(agent.key, events)}
            auditEntry={_entry(agent.step, audit.data)}
          />
        ))}
      </div>
    </div>
  )
}

function _variant(events: PipelineEvent[], audit?: AuditEntry[]): string {
  const started = events.find((e) => e.event_type === 'pipeline_started')
  if (started?.variant) return started.variant
  const auditStart = audit?.find((e) => e.step === 'pipeline_started')?.payload
  return (auditStart?.variant as string) ?? 'default'
}

function _agentEvents(key: string, events: PipelineEvent[]): PipelineEvent[] {
  return events.filter((e) => e.agent === key)
}

function _status(key: string, events: PipelineEvent[]): AgentStatus {
  const mine = _agentEvents(key, events)
  if (mine.some((e) => e.event_type === 'agent_completed')) return 'done'
  if (mine.some((e) => e.event_type === 'agent_started')) return 'running'
  return 'queued'
}

function _duration(key: string, events: PipelineEvent[]): number | undefined {
  return _agentEvents(key, events).find((e) => e.event_type === 'agent_completed')
    ?.duration_ms
}

function _summary(key: string, events: PipelineEvent[]): Record<string, unknown> | undefined {
  return _agentEvents(key, events).find((e) => e.event_type === 'agent_completed')?.summary
}

// The audit entry for an agent's step, or undefined before it is written. The
// card derives both its filled prompt and its response from this single entry, so
// the audit log stays the one source of truth for what each agent did.
function _entry(step: string, audit?: AuditEntry[]): AuditEntry | undefined {
  return audit?.find((e) => e.step === step)
}
