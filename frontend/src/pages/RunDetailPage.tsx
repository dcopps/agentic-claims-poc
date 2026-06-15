import { useParams } from 'react-router-dom'
import type { AuditEntry, PipelineEvent } from '../api/types'
import { AgentCard, type AgentStatus } from '../components/AgentCard'
import { Card, Spinner, StatusBadge } from '../components/ui'
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

  const variant = _variant(events, audit.data)
  const completed = events.find((e) => e.event_type === 'pipeline_completed')
  const status = completed?.status ?? run.data?.status

  return (
    <div className="space-y-4">
      <Card title="Pipeline run">
        <p className="text-sm text-slate-500">
          variant: <span className="font-mono">{variant}</span> · run{' '}
          <span className="font-mono">{correlationId.slice(0, 8)}</span>
          {status && (
            <>
              {' · '}
              <StatusBadge status={status} />
            </>
          )}
        </p>
      </Card>

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
            responsePayload={_payload(agent.step, audit.data)}
          />
        ))}
      </div>

      {!completed && run.isLoading && audit.data === undefined && <Spinner />}
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

function _payload(step: string, audit?: AuditEntry[]): unknown {
  const entry = audit?.find((e) => e.step === step)
  if (!entry) return undefined
  const payload = entry.payload as Record<string, unknown>
  // Show the agent's output/verdict block where present, else the whole payload.
  return payload.output ?? payload.verdict ?? payload
}
