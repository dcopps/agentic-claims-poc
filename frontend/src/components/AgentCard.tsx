import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AuditEntry } from '../api/types'
import { agentDescriptions } from '../copy/agent-descriptions'
import { formatSeconds } from '../copy/format'
import { refusalReason } from '../copy/labels'
import { runCopy } from '../copy/run'
import { useAgentPrompt } from '../hooks/queries'
import { Badge, JsonBlock, Spinner } from './ui'

// `escalated` is the Guardrail's own failed verdict (the run went to a person);
// `failed` is an agent that broke; `not_run` is an agent after the one that
// broke (Prompt 29).
export type AgentStatus = 'queued' | 'running' | 'done' | 'escalated' | 'failed' | 'not_run'

// What the run page derives for one card (pages/runDerivation.ts): the state,
// the one-line sentence, an optional line beneath (an exception's message or a
// Guardrail finding's detail), and the duration with where it came from.
export interface CardState {
  status: AgentStatus
  summary: string
  detail?: string
  durationMs?: number
  durationFromAudit?: boolean
}

const STATUS_ICON: Record<AgentStatus, string> = {
  queued: '○',
  running: '◐',
  done: '✓',
  escalated: '⚠',
  failed: '✗',
  not_run: '∅',
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
  state: CardState
  variant: string
  auditEntry?: AuditEntry // this agent's audit-step entry, once written
}

// One agent in the pipeline visualisation. Collapsed: the state's icon, the
// sentence and the duration, with the Validator's passages and the Guardrail's
// refused objections beneath. Expanded (lazy): the prompt the LLM actually
// received and the agent's response, both read from the audit entry (the single
// source of truth). The prompt is the *filled* text captured in
// `llm_call.prompt` (Phase 8.3); for historical runs that pre-date the capture,
// it falls back to the raw template endpoint with a caveat.
export function AgentCard({ agent, label, state, variant, auditEntry }: AgentCardProps) {
  const [expanded, setExpanded] = useState(false)
  const filledPrompt = extractPrompt(auditEntry)
  // Only fetch the raw template when the filled prompt isn't available — i.e. a
  // historical entry, or an entry not yet written. Lazy on expand as before.
  const prompt = useAgentPrompt(agent, variant, expanded && filledPrompt === null)
  const expectedMs = AGENT_EXPECTED_MS[agent] ?? 6000
  const progress = useProgress(state.status === 'running', expectedMs)

  return (
    <div className="rounded border border-slate-200 bg-white">
      <CardLine
        label={label}
        state={state}
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
      />
      {state.detail && (
        <p className="px-3 pb-2 text-xs text-slate-600" data-testid="card-detail">
          {state.detail}
        </p>
      )}
      <PassagesLine passages={extractPassages(auditEntry)} />
      <RefusedObjectionsLine refused={extractRefusedClaims(auditEntry)} />
      {state.status === 'running' && (
        <RunningBar agent={agent} label={label} expectedMs={expectedMs} progress={progress} />
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
            <ResponsePanel auditEntry={auditEntry} status={state.status} />
          </div>
        </div>
      )}
    </div>
  )
}

interface CardLineProps {
  label: string
  state: CardState
  expanded: boolean
  onToggle: () => void
}

// The card's top line: icon, agent, sentence, duration, caret. The duration's
// title says when it was computed from the audit rows rather than the live event.
function CardLine({ label, state, expanded, onToggle }: CardLineProps) {
  return (
    <button
      type="button"
      className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm"
      onClick={onToggle}
      aria-expanded={expanded}
    >
      <span className="font-mono text-base" aria-hidden="true">
        {STATUS_ICON[state.status]}
      </span>
      <span className="w-28 font-medium">{label}</span>
      <span className="flex-1 text-slate-600">{state.summary}</span>
      {state.durationMs !== undefined && (
        <span
          className="font-mono text-xs text-slate-400"
          title={state.durationFromAudit ? runCopy.durationFromAudit : undefined}
        >
          {formatSeconds(state.durationMs)}
        </span>
      )}
      <span className="text-slate-400">{expanded ? '▾' : '▸'}</span>
    </button>
  )
}

// The Validator's retrieved passages (Prompt 27), shown without expanding and
// each linked to its place on the Policy page; the ones the verdict cited are
// marked. Read from the coverage_check row's retrieval block.
function PassagesLine({ passages }: { passages: RetrievedPassage[] }) {
  if (passages.length === 0) return null
  return (
    <p className="px-3 pb-2 text-xs text-slate-600" data-testid="validator-passages">
      Passages:{' '}
      {passages.map((passage, index) => (
        <span key={passage.chunkId}>
          {index > 0 && ' · '}
          <Link
            to={{ pathname: '/policy', hash: passage.chunkId }}
            className="text-blue-700 hover:underline"
          >
            {passage.section}
          </Link>
          {passage.cited && ' (cited)'}
        </span>
      ))}
    </p>
  )
}

// The Guardrail's refused objections (Phase 9.2.2's `llm_flags_discarded`),
// shown without expanding: the model said these were policy citations and the
// code could not find them in the Adjuster's text. Called objections, not
// claims, because on this screen a claim is an insurance claim (Prompt 26). The
// reason is given in words (Prompt 29); its code stays in the audit trail.
function RefusedObjectionsLine({ refused }: { refused: RefusedClaim[] }) {
  if (refused.length === 0) return null
  return (
    <p className="px-3 pb-2 text-xs text-amber-700" data-testid="refused-objections">
      Refused objections ({refused.length}):{' '}
      {refused
        .map((claim) => `“${claim.quote ?? 'no quote'}” — ${refusalReason(claim.reason)}`)
        .join('; ')}
    </p>
  )
}

interface RunningBarProps {
  agent: string
  label: string
  expectedMs: number
  progress: number
}

function RunningBar({ agent, label, expectedMs, progress }: RunningBarProps) {
  return (
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
        Showing the prompt template — this run pre-dates the audit-prompt-capture change.
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
function ResponsePanel({ auditEntry, status }: { auditEntry?: AuditEntry; status: AgentStatus }) {
  if (auditEntry) return <JsonBlock value={extractResponseBlock(auditEntry)} />
  if (status === 'done') {
    return (
      <p className="text-sm text-red-600">
        Audit entry not found for this completed agent — this may indicate a write failure.
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

interface RefusedClaim {
  quote: string | null
  reason: string
}

// The `llm_flags_discarded` list an output_check row carries from 0.9.1.2 on:
// each item is a model claim the code refused, with its quote and the reason.
// Absent or malformed → an empty list; nothing else on the card depends on it.
function extractRefusedClaims(entry?: AuditEntry): RefusedClaim[] {
  const discarded = entry?.payload.llm_flags_discarded
  if (!Array.isArray(discarded)) return []
  return discarded.flatMap((item) => {
    if (typeof item !== 'object' || item === null) return []
    const { quote, reason } = item as Record<string, unknown>
    if (typeof reason !== 'string') return []
    return [{ quote: typeof quote === 'string' ? quote : null, reason }]
  })
}

interface RetrievedPassage {
  chunkId: string
  section: string
  cited: boolean
}

// The coverage_check row's `retrieval.chunks`, each marked if the verdict's
// `cited_chunks` names it. Absent or malformed → an empty list; the card shows
// nothing extra, as with the Guardrail's refused objections.
function extractPassages(entry?: AuditEntry): RetrievedPassage[] {
  const retrieval = entry?.payload.retrieval
  const chunks = (retrieval as Record<string, unknown> | undefined)?.chunks
  if (!Array.isArray(chunks)) return []
  const verdict = entry?.payload.verdict as Record<string, unknown> | undefined
  const citedRaw = Array.isArray(verdict?.cited_chunks) ? verdict.cited_chunks : []
  const cited = new Set(
    citedRaw.flatMap((c) => {
      const id = (c as Record<string, unknown> | null)?.chunk_id
      return typeof id === 'string' ? [id] : []
    }),
  )
  return chunks.flatMap((chunk) => {
    const { chunk_id, section } = (chunk ?? {}) as Record<string, unknown>
    if (typeof chunk_id !== 'string' || typeof section !== 'string') return []
    return [{ chunkId: chunk_id, section, cited: cited.has(chunk_id) }]
  })
}
