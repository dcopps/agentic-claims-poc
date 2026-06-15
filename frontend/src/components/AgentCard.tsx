import { useState } from 'react'
import { useAgentPrompt } from '../hooks/queries'
import { Badge, JsonBlock, Spinner } from './ui'

export type AgentStatus = 'queued' | 'running' | 'done' | 'escalated' | 'failed'

const STATUS_ICON: Record<AgentStatus, string> = {
  queued: '○',
  running: '◐',
  done: '✓',
  escalated: '⚠',
  failed: '✗',
}

interface AgentCardProps {
  agent: string // underscore key, e.g. "doc_parser"
  label: string
  status: AgentStatus
  durationMs?: number
  summary?: Record<string, unknown>
  variant: string
  responsePayload?: unknown // the agent's audit-step payload, if written
}

// One agent in the live pipeline visualisation. Collapsed: status + summary +
// duration. Expanded (lazy): the prompt source (system + user, fetched on demand)
// and the agent's full LLM response from the audit payload.
export function AgentCard({
  agent,
  label,
  status,
  durationMs,
  summary,
  variant,
  responsePayload,
}: AgentCardProps) {
  const [expanded, setExpanded] = useState(false)
  const prompt = useAgentPrompt(agent, variant, expanded)

  return (
    <div className="rounded border border-slate-200 bg-white">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className="font-mono text-base" aria-hidden="true">
          {STATUS_ICON[status]}
        </span>
        <span className="w-28 font-medium">{label}</span>
        <span className="flex-1 text-slate-500">
          {summary ? JSON.stringify(summary) : status}
        </span>
        {durationMs !== undefined && (
          <span className="font-mono text-xs text-slate-400">{durationMs}ms</span>
        )}
        <span className="text-slate-400">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-slate-200 px-3 py-3">
          <div>
            <Badge>prompt</Badge>
            {prompt.isLoading && <Spinner label="Loading prompt…" />}
            {prompt.data && (
              <div className="mt-1 space-y-2">
                <PromptText title="System" body={prompt.data.system} />
                <PromptText title="User" body={prompt.data.user} />
              </div>
            )}
          </div>
          <div>
            <Badge>response</Badge>
            {responsePayload ? (
              <JsonBlock value={responsePayload} />
            ) : (
              <p className="text-sm text-slate-500">Waiting for this agent to complete…</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function PromptText({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs text-slate-700">
        {body}
      </pre>
    </div>
  )
}
