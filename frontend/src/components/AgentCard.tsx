import { useEffect, useState } from 'react'
import type { AuditEntry } from '../api/types'
import { agentDescriptions } from '../copy/agent-descriptions'
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

// Expected per-agent runtime (ms), empirical from the Phase 8 rehearsal on Render
// Standard and rounded conservatively upward. Display-only: the SSE
// `agent_completed` event always wins; this only drives the running progress bar.
const AGENT_EXPECTED_MS: Record<string, number> = {
  doc_parser: 6000,
  validator: 9000,
  adjuster: 7000,
  guardrail: 5000,
}

// While `active`, advance a 0–100 percentage from elapsed/expected. JS-driven
// (not a pure CSS transition) so the progress is observable in tests; the only
// setState is inside the interval callback, which the effect rules permit.
function useProgress(active: boolean, expectedMs: number): number {
  const [pct, setPct] = useState(0)
  useEffect(() => {
    if (!active) return
    const start = Date.now()
    const id = setInterval(() => {
      setPct(Math.min(100, ((Date.now() - start) / expectedMs) * 100))
    }, 200)
    return () => clearInterval(id)
  }, [active, expectedMs])
  return active ? pct : 0
}

interface AgentCardProps {
  agent: string // underscore key, e.g. "doc_parser"
  label: string
  status: AgentStatus
  durationMs?: number
  summary?: Record<string, unknown>
  variant: string
  auditEntry?: AuditEntry // this agent's audit-step entry, once written
}

// One agent in the live pipeline visualisation. Collapsed: status + summary +
// duration. Expanded (lazy): the prompt the LLM actually received and the agent's
// response — both read from the audit entry (the single source of truth). The
// prompt is the *filled* text captured in `llm_call.prompt` (Phase 8.3); for
// historical runs that pre-date the capture, it falls back to the raw template
// endpoint with a caveat. The response panel uses the audit entry's existence as
// the completion signal, not the live SSE event.
export function AgentCard({
  agent,
  label,
  status,
  durationMs,
  summary,
  variant,
  auditEntry,
}: AgentCardProps) {
  const [expanded, setExpanded] = useState(false)
  const filledPrompt = extractPrompt(auditEntry)
  // Only fetch the raw template when the filled prompt isn't available — i.e. a
  // historical entry, or an entry not yet written. Lazy on expand as before.
  const prompt = useAgentPrompt(agent, variant, expanded && filledPrompt === null)
  const expectedMs = AGENT_EXPECTED_MS[agent] ?? 6000
  const progress = useProgress(status === 'running', expectedMs)

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

      {status === 'running' && (
        <div className="px-3 pb-2" aria-label={`${label} running`}>
          <p className="text-xs text-slate-500">
            {agentDescriptions[agent] ?? 'Working…'} · ~{Math.round(expectedMs / 1000)}s
          </p>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded bg-slate-100">
            <div
              className="h-1.5 rounded bg-blue-500 transition-[width] duration-200 ease-linear"
              style={{ width: `${progress}%` }}
              role="progressbar"
              aria-valuenow={Math.round(progress)}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
        </div>
      )}

      {expanded && (
        <div className="space-y-3 border-t border-slate-200 px-3 py-3">
          <div>
            <Badge>prompt</Badge>
            {filledPrompt ? (
              <div className="mt-1 space-y-2">
                <PromptText title="System" body={filledPrompt.system} />
                <PromptText title="User" body={filledPrompt.user} />
              </div>
            ) : (
              <TemplateFallback prompt={prompt} />
            )}
          </div>
          <div>
            <Badge>response</Badge>
            <ResponsePanel auditEntry={auditEntry} status={status} />
          </div>
        </div>
      )}
    </div>
  )
}

// The prompt panel's fallback for runs with no captured prompt: the raw template
// (placeholders intact) plus a caveat so the viewer knows they are not seeing the
// substituted text. Used for historical runs that pre-date the audit-prompt
// capture, and transiently for an entry not yet written mid-run.
function TemplateFallback({ prompt }: { prompt: ReturnType<typeof useAgentPrompt> }) {
  if (prompt.isLoading) return <Spinner label="Loading prompt…" />
  if (!prompt.data) return null
  return (
    <div className="mt-1 space-y-2">
      <p className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">
        Showing the prompt template — this run pre-dates the audit-prompt-capture
        change.
      </p>
      <PromptText title="System" body={prompt.data.system} />
      <PromptText title="User" body={prompt.data.user} />
    </div>
  )
}

// The response panel reads the audit entry, not the SSE event. Three explicit
// states: entry present → render its response block; entry absent but the agent
// reports done → an audit-integrity error (a completed agent must have written an
// entry); otherwise → still in flight.
function ResponsePanel({
  auditEntry,
  status,
}: {
  auditEntry?: AuditEntry
  status: AgentStatus
}) {
  if (auditEntry) return <JsonBlock value={extractResponseBlock(auditEntry)} />
  if (status === 'done') {
    return (
      <p className="text-sm text-red-600">
        Audit entry not found for this completed agent — this may indicate a write
        failure.
      </p>
    )
  }
  return <p className="text-sm text-slate-500">Waiting for this agent to complete…</p>
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

// Read the literal prompt (Phase 8.3) from an audit entry's `llm_call.prompt`.
// Returns null when the entry is absent, the call made no prompt (e.g. the
// Adjuster demo fixture), or the run pre-dates the capture — the caller then
// falls back to the raw template.
function extractPrompt(entry?: AuditEntry): { system: string; user: string } | null {
  const llmCall = entry?.payload.llm_call
  if (typeof llmCall !== 'object' || llmCall === null) return null
  const prompt = (llmCall as Record<string, unknown>).prompt
  if (typeof prompt !== 'object' || prompt === null) return null
  const { system, user } = prompt as Record<string, unknown>
  if (typeof system === 'string' && typeof user === 'string') return { system, user }
  return null
}

// The response block to display for an agent: its output (or the validator's
// verdict) where present, else the whole payload. Mirrors the audit-step shapes.
function extractResponseBlock(entry: AuditEntry): unknown {
  const payload = entry.payload
  return payload.output ?? payload.verdict ?? payload
}
