// How the run page decides what each card and the header show (Prompt 29).
//
// The page has two sources: the audit rows, which are the durable record, and
// the live event stream, which is a projection of the same run in time. Before
// this module the cards read the stream alone, so a run opened after the event
// showed every agent as queued. The rule now: the audit trail is consulted
// first, and the stream speaks only where the trail has no row yet. Pure
// functions, no React, so the four card states are testable from hand-built
// rows without a browser or a stream.
import type { AuditEntry, FiredRule, PipelineEvent, PipelineResult } from '../api/types'
import type { CardState } from '../components/AgentCard'
import { readableFallback, statusLabel } from '../copy/labels'
import { failureReason, runCopy } from '../copy/run'

// The four agents in pipeline order, with their SSE name, display label, and the
// audit step their row lands under.
export const AGENTS = [
  { key: 'doc_parser', label: 'Doc-Parser', step: 'doc_extract' },
  { key: 'validator', label: 'Validator', step: 'coverage_check' },
  { key: 'adjuster', label: 'Adjuster', step: 'settlement_estimate' },
  { key: 'guardrail', label: 'Guardrail', step: 'output_check' },
] as const

type Agent = (typeof AGENTS)[number]
type Payload = Record<string, unknown>

export interface AbortInfo {
  failingAgent: string
  errorType: string
  message: string
}

// The audit steps the orchestrator writes at the end of a run, and the run
// status each one means.
const TERMINAL_STEPS: Record<string, string> = {
  pipeline_settled: 'settled',
  pipeline_awaiting_human: 'awaiting_human',
  pipeline_aborted: 'aborted',
}

export function agentLabel(key: string): string {
  return AGENTS.find((agent) => agent.key === key)?.label ?? readableFallback(key)
}

// One state per agent, keyed by the agent's SSE name.
export function deriveCards(
  rows: AuditEntry[],
  events: PipelineEvent[],
): Record<string, CardState> {
  const abort = deriveAbort(rows, events)
  const threw = guardrailThrew(rows, events)
  return Object.fromEntries(
    AGENTS.map((agent, index) => [agent.key, deriveCard(agent, index, rows, events, abort, threw)]),
  )
}

// The abort, from the audit row when it exists and the live event otherwise, so
// an abort watched live and one opened a week later read the same.
export function deriveAbort(rows: AuditEntry[], events: PipelineEvent[]): AbortInfo | null {
  const row = rows.find((r) => r.step === 'pipeline_aborted')?.payload
  if (row) {
    return {
      failingAgent: str(row.failing_agent),
      errorType: str(row.error_type),
      message: str(row.error_message),
    }
  }
  const event = events.find((e) => e.event_type === 'pipeline_aborted')
  if (!event) return null
  return {
    failingAgent: event.failing_agent ?? '',
    errorType: event.error_type ?? '',
    message: event.message ?? '',
  }
}

export function deriveVariant(rows: AuditEntry[], events: PipelineEvent[]): string {
  const started = events.find((e) => e.event_type === 'pipeline_started')
  if (started?.variant) return started.variant
  const row = rows.find((r) => r.step === 'pipeline_started')?.payload
  return typeof row?.variant === 'string' ? row.variant : 'default'
}

// The run's outcome: the live terminal event, else the terminal audit row, else
// the reconstructed run, else "running" once anything at all has been recorded.
export function deriveStatus(
  rows: AuditEntry[],
  events: PipelineEvent[],
  run?: PipelineResult,
): string | undefined {
  const completed = events.find((e) => e.event_type === 'pipeline_completed')
  if (completed?.status) return completed.status
  if (events.some((e) => e.event_type === 'pipeline_aborted')) return 'aborted'
  const terminal = rows.find((r) => r.step in TERMINAL_STEPS)
  if (terminal) return TERMINAL_STEPS[terminal.step]
  if (run?.status) return run.status
  return rows.length > 0 || events.length > 0 ? 'running' : undefined
}

// The fired escalation rules: from the decision's own row first (present while
// the run is still live), else from the reconstructed run, which also carries
// the synthetic fail-closed rule when the Guardrail threw.
export function deriveFiredRules(rows: AuditEntry[], run?: PipelineResult): FiredRule[] {
  const fromRow = rows.find((r) => r.step === 'escalation_decision')?.payload.fired_rules
  if (Array.isArray(fromRow)) return fromRow.flatMap(asFiredRule)
  return run?.escalation_decision?.fired_rules ?? []
}

function asFiredRule(item: unknown): FiredRule[] {
  if (typeof item !== 'object' || item === null) return []
  const { name, rule_type, description, observed_value } = item as Payload
  if (typeof name !== 'string' || typeof description !== 'string') return []
  return [
    {
      name,
      rule_type: str(rule_type),
      description,
      observed_value: typeof observed_value === 'string' ? observed_value : null,
    },
  ]
}

// The abort is applied before the agent's own row is read: when a model call
// fails the agent still writes a row (with an error block), and the orchestrator's
// abort row is the one that says what happened.
function deriveCard(
  agent: Agent,
  index: number,
  rows: AuditEntry[],
  events: PipelineEvent[],
  abort: AbortInfo | null,
  threw: { message: string } | null,
): CardState {
  if (abort) {
    const failingIndex = AGENTS.findIndex((a) => a.key === abort.failingAgent)
    if (index === failingIndex) return failedCard(agent, abort)
    if (failingIndex >= 0 && index > failingIndex) {
      return { status: 'not_run', summary: runCopy.notRun(AGENTS[failingIndex].label) }
    }
  }
  if (agent.key === 'guardrail' && threw) {
    return { status: 'failed', summary: runCopy.guardrailThrew, detail: threw.message || undefined }
  }
  const rowIndex = rows.findIndex((r) => r.step === agent.step)
  if (rowIndex >= 0) return cardFromRow(agent, rows, rowIndex, events)
  return cardFromEvents(agent, events)
}

function failedCard(agent: Agent, abort: AbortInfo): CardState {
  const reason = failureReason(agent.label, abort.errorType, abort.message)
  return { status: 'failed', summary: runCopy.failed(reason), detail: abort.message || undefined }
}

// The fail-closed path: the Guardrail itself raised, the run went to a person,
// and the awaiting row (or the live completion's summary) says so.
function guardrailThrew(rows: AuditEntry[], events: PipelineEvent[]): { message: string } | null {
  const row = rows.find(
    (r) => r.step === 'pipeline_awaiting_human' && r.payload.reason === 'guardrail_threw',
  )
  if (row) return { message: str(row.payload.error_message) }
  const live = events.some(
    (e) => e.event_type === 'pipeline_completed' && e.summary?.reason === 'guardrail_threw',
  )
  return live ? { message: '' } : null
}

// A written row means the agent finished. The live event's duration is the
// agent's wall time; after the event the difference between this row and the
// one before it is the same figure to within the status write (plan D2).
function cardFromRow(
  agent: Agent,
  rows: AuditEntry[],
  rowIndex: number,
  events: PipelineEvent[],
): CardState {
  const live = events.find((e) => e.agent === agent.key && e.event_type === 'agent_completed')
  const duration =
    live?.duration_ms !== undefined
      ? { durationMs: live.duration_ms }
      : durationBetweenRows(rows, rowIndex)
  return { ...describeRow(agent.key, rows[rowIndex].payload), ...duration }
}

function durationBetweenRows(rows: AuditEntry[], rowIndex: number): Partial<CardState> {
  if (rowIndex === 0) return {}
  const ms = Date.parse(rows[rowIndex].created_at) - Date.parse(rows[rowIndex - 1].created_at)
  return Number.isNaN(ms) || ms < 0 ? {} : { durationMs: ms, durationFromAudit: true }
}

// The sentence for a finished agent, from the fields its audit row carries. A row
// of an unexpected shape still reads as finished rather than breaking the page.
function describeRow(
  key: string,
  payload: Payload,
): Pick<CardState, 'status' | 'summary' | 'detail'> {
  const output = obj(payload.output)
  switch (key) {
    case 'doc_parser':
      return { status: 'done', summary: runCopy.docParser(str(output.claim_type)) }
    case 'validator': {
      const verdict = obj(payload.verdict)
      return {
        status: 'done',
        summary: runCopy.validator(verdict.covered === true, num(verdict.confidence)),
      }
    }
    case 'adjuster':
      return {
        status: 'done',
        summary: runCopy.adjuster(
          str(output.recommended_settlement),
          num(output.confidence),
          payload.demo_fixture === true,
        ),
      }
    case 'guardrail':
      return describeGuardrailRow(payload, output)
    default:
      return { status: 'done', summary: statusLabel('done') }
  }
}

// A failed verdict is the Guardrail doing its job, so it is marked ⚠ (escalated),
// not ✗ (failed): the run went to a person, the agent did not break (plan D4).
function describeGuardrailRow(
  payload: Payload,
  output: Payload,
): Pick<CardState, 'status' | 'summary' | 'detail'> {
  const flags = Array.isArray(output.flags) ? output.flags.map(obj) : []
  if (output.passed === false) {
    const details = flags.map((flag) => str(flag.detail)).filter((d) => d !== '')
    return {
      status: 'escalated',
      summary: runCopy.guardrailFailed(flags.map((flag) => str(flag.kind))),
      detail: details.length > 0 ? details.join('; ') : undefined,
    }
  }
  const refused = Array.isArray(payload.llm_flags_discarded)
    ? payload.llm_flags_discarded.length
    : 0
  return { status: 'done', summary: runCopy.guardrailPassed(refused) }
}

// No row yet: the stream decides. A completion here is transient (the row
// arrives on the invalidation the stream triggers), so the sentence is built
// from the event's thin summary without a confidence.
function cardFromEvents(agent: Agent, events: PipelineEvent[]): CardState {
  const mine = events.filter((e) => e.agent === agent.key)
  const completed = mine.find((e) => e.event_type === 'agent_completed')
  if (completed) {
    const summary = obj(completed.summary)
    return {
      status: agent.key === 'guardrail' && summary.passed === false ? 'escalated' : 'done',
      summary: summaryFromEvent(agent.key, summary),
      durationMs: completed.duration_ms,
    }
  }
  if (mine.some((e) => e.event_type === 'agent_started')) {
    return { status: 'running', summary: statusLabel('running') }
  }
  return { status: 'queued', summary: runCopy.waiting }
}

function summaryFromEvent(key: string, summary: Payload): string {
  switch (key) {
    case 'doc_parser':
      return runCopy.docParser(str(summary.claim_type))
    case 'validator':
      return runCopy.validator(summary.covered === true)
    case 'adjuster':
      return runCopy.adjuster(str(summary.recommended_settlement))
    case 'guardrail':
      return summary.passed === false ? runCopy.guardrailFailed([]) : runCopy.guardrailPassed(0)
    default:
      return statusLabel('done')
  }
}

// Loose readers for audit payloads, which are untyped JSON: a missing or
// mistyped field reads as empty rather than throwing inside a render.
function obj(value: unknown): Payload {
  return typeof value === 'object' && value !== null ? (value as Payload) : {}
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function num(value: unknown): number | undefined {
  return typeof value === 'number' ? value : undefined
}
