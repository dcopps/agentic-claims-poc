// How the Audit page reads one record (Prompt 32): who wrote it, what happened
// in a sentence, its name in the viewer's header, and the instructions it holds.
// Wherever the run page or the claim page already has the sentence for a row,
// it is reused from runDerivation.ts and the copy modules, so a wording change
// there changes this page too. Pure functions, no React.
import type { AuditEntry, FiredRule } from '../api/types'
import { auditCopy } from '../copy/audit'
import { claimCopy, decisionWord } from '../copy/claim'
import { formatDateTime } from '../copy/format'
import { readableFallback, runStatusLabel } from '../copy/labels'
import { FAIL_CLOSED_DESCRIPTION, failureReason, ruleLine, runCopy } from '../copy/run'
import { deriveDecision } from './claimDerivation'
import { AGENTS, agentLabel, deriveAbort, deriveFiredRules, describeRow } from './runDerivation'

// The short run id the pages show, and a whole UUID.
export const SHORT_ID_LENGTH = 8
const UUID_LENGTH = 36
const UUID_CHARS = /^[0-9a-f-]+$/

export type RunIdInput =
  | { kind: 'full'; value: string }
  | { kind: 'short'; value: string }
  | { kind: 'too_short' }
  | { kind: 'invalid' }

// What a visitor typed into the Run id box: a whole id to load directly, a
// prefix of eight or more characters to resolve through the backend, too few
// characters (never sent — Dermot, at the gate), or characters a run id never has.
export function classifyRunId(raw: string): RunIdInput {
  const value = raw.trim().toLowerCase()
  if (value === '' || !UUID_CHARS.test(value)) return { kind: 'invalid' }
  if (value.length === UUID_LENGTH) return { kind: 'full', value }
  if (value.length < SHORT_ID_LENGTH) return { kind: 'too_short' }
  return { kind: 'short', value }
}

// The synthetic rule the orchestrator records when the Guardrail itself threw.
const FAIL_CLOSED_RULE: FiredRule = {
  name: 'guardrail_failed',
  rule_type: 'hard',
  description: FAIL_CLOSED_DESCRIPTION,
  observed_value: null,
}

type Payload = Record<string, unknown>

// Who wrote the record, in words: an agent by its label, the orchestrator, a person.
export function rowAuthor(entry: AuditEntry): string {
  const agent = AGENTS.find((a) => a.key === entry.agent)
  if (agent) return agent.label
  return auditCopy.who[entry.agent] ?? readableFallback(entry.agent)
}

// What happened, as one sentence. The agents' rows read the run page's card
// sentence; a row whose model call failed reads the card's failure sentence;
// the orchestrator's and the person's rows have their own.
export function rowSentence(entry: AuditEntry): string {
  const payload = entry.payload
  const agent = AGENTS.find((a) => a.step === entry.step)
  if (agent) return agentSentence(agent.key, agent.label, payload)
  switch (entry.step) {
    case 'pipeline_started':
      return auditCopy.started(str(payload.variant) || 'default')
    case 'escalation_decision': {
      const rules = deriveFiredRules([entry], [])
      return rules.length > 0 ? auditCopy.sentToPerson(rules.map(ruleLine)) : auditCopy.noRuleFired
    }
    case 'pipeline_settled':
      return claimCopy.runOutcome({
        kind: 'settled',
        settlement: str(payload.settlement) || undefined,
      })
    case 'pipeline_awaiting_human':
      return payload.reason === 'guardrail_threw'
        ? `${runStatusLabel('awaiting_human')}: ${ruleLine(FAIL_CLOSED_RULE)}`
        : runStatusLabel('awaiting_human')
    case 'pipeline_aborted':
      return abortSentence(entry)
    case 'human_approval':
    case 'human_rejection':
      return decisionSentence(entry)
    default:
      return readableFallback(entry.step)
  }
}

// An agent's row: its error block means the model call failed (the abort row
// that follows names the agent); otherwise the card's own sentence.
function agentSentence(key: string, label: string, payload: Payload): string {
  const error = obj(payload.error)
  if (typeof error.type === 'string') {
    return runCopy.failed(failureReason(label, error.type, str(error.message)))
  }
  return describeRow(key, payload).summary
}

function abortSentence(entry: AuditEntry): string {
  const abort = deriveAbort([entry], [])
  if (!abort) return readableFallback(entry.step)
  return runCopy.aborted(
    failureReason(agentLabel(abort.failingAgent), abort.errorType, abort.message),
  )
}

function decisionSentence(entry: AuditEntry): string {
  const decision = deriveDecision([entry])
  if (!decision) return readableFallback(entry.step)
  return auditCopy.decided(decisionWord(decision.decision), decision.decidedBy)
}

// The step in plain words, for the viewer's header line.
export function stepName(entry: AuditEntry): string {
  return auditCopy.stepNames[entry.step] ?? readableFallback(entry.step)
}

// "Validator · coverage check · 15 Nov 2026, 15:09:08 · record 210 in the ledger"
export function recordHeader(entry: AuditEntry): string {
  return auditCopy.recordHeader(
    rowAuthor(entry),
    stepName(entry),
    formatDateTime(entry.created_at, { seconds: true }),
    entry.audit_id,
  )
}

// The literal prompt (Phase 8.3) from a record's `llm_call.prompt`: null when
// the record is absent, the call made no prompt (the Adjuster demo fixture), or
// the run pre-dates the capture. Moved here from AgentCard (Prompt 32, D8).
export function extractPrompt(entry?: AuditEntry): { system: string; user: string } | null {
  const prompt = obj(obj(entry?.payload.llm_call).prompt)
  const { system, user } = prompt
  if (typeof system === 'string' && typeof user === 'string') return { system, user }
  return null
}

// The Adjuster's demo-fixture record: the figure came from the fixed file and
// no model was called, which the viewer says in a sentence.
export function isDemoFixture(entry: AuditEntry): boolean {
  return (
    entry.payload.demo_fixture === true || obj(entry.payload.llm_call).provider === 'demo_fixture'
  )
}

// When the run started: the pipeline_started payload's own time, else the first row's.
export function deriveStartedAt(rows: AuditEntry[]): string | undefined {
  const started = rows.find((r) => r.step === 'pipeline_started')
  const recorded = started?.payload.started_at
  if (typeof recorded === 'string') return recorded
  return (started ?? rows[0])?.created_at
}

function obj(value: unknown): Payload {
  return typeof value === 'object' && value !== null ? (value as Payload) : {}
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}
