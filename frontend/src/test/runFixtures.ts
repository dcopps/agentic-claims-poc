// Audit rows for the five run outcomes the run page must read after the event
// (Prompt 29), shaped as the real Azure rows of 10 November 2026 were: the
// Harborline settlement f368c2c5, the Northwood ceiling escalation 67bdf225, the
// Coral Bay Guardrail failure e9566e92, the smoke_damage abort 0aca331d, and the
// fail-closed path from the orchestrator's `_finalise_guardrail_throw`. Payloads
// carry only the keys the page reads plus what identifies the row.
import type { AuditEntry, ClaimRecord, RunStatus, RunSummary } from '../api/types'

const START = Date.parse('2026-11-10T16:20:00.000Z')

/** The claim the fixture rows name (`claim_id: 'c1'`), shaped as GET /api/claims/{id} returns it. */
export const CLAIM: ClaimRecord = {
  claim_id: 'c1',
  claim_number: 'CLM-2026-9BB57A86',
  line_of_business: 'commercial_property',
  claimant_name: 'Harborline Logistics Ltd',
  policy_number: 'CP-2026-9001',
  loss_date: '2026-04-18',
  reported_date: '2026-04-19',
  jurisdiction: 'United Kingdom',
  narrative: 'Burst supply line flooded the warehouse mezzanine.',
  claim_type: 'water_damage',
  reported_amount: '85000.00',
  status: 'settled',
  scenario_tag: 'auto_approve',
  created_at: '2026-11-10T16:19:40.000Z',
  updated_at: '2026-11-10T16:20:09.000Z',
  human_decision: null,
}

// Wall time per step in milliseconds, so a derived duration is checkable.
const STEP_MS = {
  doc_extract: 1310,
  coverage_check: 3400,
  settlement_estimate: 2600,
  output_check: 1600,
  escalation_decision: 20,
  terminal: 15,
}

interface RowSpec {
  agent: string
  step: string
  payload: Record<string, unknown>
  afterMs: number
}

function build(specs: RowSpec[]): AuditEntry[] {
  let at = START
  return specs.map((spec, index) => {
    at += spec.afterMs
    return {
      audit_id: index + 1,
      agent: spec.agent,
      step: spec.step,
      created_at: new Date(at).toISOString(),
      payload: spec.payload,
      chain_hash: `hash-${index + 1}`,
    }
  })
}

const started: RowSpec = {
  agent: 'orchestrator',
  step: 'pipeline_started',
  payload: { variant: 'default', claim_id: 'c1' },
  afterMs: 0,
}

const docExtract: RowSpec = {
  agent: 'doc_parser',
  step: 'doc_extract',
  payload: {
    output: { claim_type: 'water_damage', narrative_summary: 'A pipe burst.' },
    fields_source: 'claim_record',
    llm_call: { provider: 'anthropic', latency_ms: 1147 },
  },
  afterMs: STEP_MS.doc_extract,
}

function coverageCheck(covered: boolean, confidence: number): RowSpec {
  return {
    agent: 'validator',
    step: 'coverage_check',
    payload: {
      verdict: { covered, confidence, policy_basis: 'Named Perils', cited_chunks: [] },
      retrieval: { chunks: [] },
      llm_call: { provider: 'anthropic', latency_ms: 3206 },
    },
    afterMs: STEP_MS.coverage_check,
  }
}

function settlementEstimate(settlement: string, confidence: number, demoFixture = false): RowSpec {
  return {
    agent: 'adjuster',
    step: 'settlement_estimate',
    payload: {
      output: { recommended_settlement: settlement, confidence, reasoning: 'Within range.' },
      demo_fixture: demoFixture,
      llm_call: demoFixture
        ? {
            note: 'no model call; deterministic demo fixture',
            provider: 'demo_fixture',
            latency_ms: 0,
          }
        : { provider: 'anthropic', latency_ms: 2452 },
    },
    afterMs: STEP_MS.settlement_estimate,
  }
}

function outputCheck(passed: boolean, flags: unknown[], discarded: unknown[] = []): RowSpec {
  return {
    agent: 'guardrail',
    step: 'output_check',
    payload: {
      output: {
        passed,
        flags,
        summary: passed ? 'No additional issues found.' : 'Guardrail flagged 1 issue(s).',
      },
      llm_flags_counted: [],
      llm_flags_discarded: discarded,
      llm_call: { provider: 'anthropic', latency_ms: 1499 },
    },
    afterMs: STEP_MS.output_check,
  }
}

function escalationDecision(firedRules: unknown[]): RowSpec {
  return {
    agent: 'orchestrator',
    step: 'escalation_decision',
    payload: { escalate: firedRules.length > 0, fired_rules: firedRules, reasoning: 'rules' },
    afterMs: STEP_MS.escalation_decision,
  }
}

export const CEILING_RULE = {
  name: 'settlement_over_ceiling',
  rule_type: 'threshold',
  description: 'settlement > $250,000',
  observed_value: '820000.00',
}

export const GUARDRAIL_RULE = {
  name: 'guardrail_failed',
  rule_type: 'hard',
  description: 'Guardrail output check did not pass',
  observed_value: null,
}

export const CORAL_BAY_FLAG = {
  kind: 'hallucinated_citation',
  detail: "endorsement 'Coastal Surge Rider' not in retrieved chunks",
  source: 'rule',
}

export const ABORT_MESSAGE =
  "MarketDataTable.lookup: unknown claim_type 'smoke_damage' (normalised='smoke_damage'); " +
  "supported types=['fire', 'flood', 'storm_complex', 'theft', 'water_damage', 'wind']"

/** Harborline: four agents done, no rules, settled. */
export function settledRows(): AuditEntry[] {
  return build([
    started,
    docExtract,
    coverageCheck(true, 0.92),
    settlementEstimate('82500.00', 0.85),
    outputCheck(true, []),
    escalationDecision([]),
    {
      agent: 'orchestrator',
      step: 'pipeline_settled',
      payload: { status: 'settled', settlement: '82500.00', fired_rule_names: [] },
      afterMs: STEP_MS.terminal,
    },
  ])
}

/** Northwood: four agents done, the ceiling rule fired, awaiting a person. */
export function ceilingRows(): AuditEntry[] {
  return build([
    started,
    docExtract,
    coverageCheck(true, 0.92),
    settlementEstimate('820000.00', 0.85),
    outputCheck(true, []),
    escalationDecision([CEILING_RULE]),
    {
      agent: 'orchestrator',
      step: 'pipeline_awaiting_human',
      payload: {
        status: 'awaiting_human',
        settlement: '820000.00',
        fired_rule_names: ['settlement_over_ceiling'],
      },
      afterMs: STEP_MS.terminal,
    },
  ])
}

/** Coral Bay: the fixture Adjuster, the Guardrail's failed verdict, two rules. */
export function guardrailFailureRows(): AuditEntry[] {
  return build([
    started,
    docExtract,
    coverageCheck(true, 0.9),
    settlementEstimate('1400000.00', 0.82, true),
    outputCheck(false, [CORAL_BAY_FLAG]),
    escalationDecision([GUARDRAIL_RULE, { ...CEILING_RULE, observed_value: '1400000.00' }]),
    {
      agent: 'orchestrator',
      step: 'pipeline_awaiting_human',
      payload: {
        status: 'awaiting_human',
        fired_rule_names: ['guardrail_failed', 'settlement_over_ceiling'],
      },
      afterMs: STEP_MS.terminal,
    },
  ])
}

/** A background claim of an unsupported type: the Adjuster failed before its model call. */
export function abortedRows(): AuditEntry[] {
  return build([
    started,
    docExtract,
    coverageCheck(true, 0.88),
    {
      agent: 'orchestrator',
      step: 'pipeline_aborted',
      payload: {
        status: 'aborted',
        failing_agent: 'adjuster',
        error_type: 'ValueError',
        error_message: ABORT_MESSAGE,
      },
      afterMs: STEP_MS.terminal,
    },
  ])
}

/** Fail-closed: the Guardrail itself raised; no output_check row; awaiting a person. */
export function guardrailThrewRows(): AuditEntry[] {
  return build([
    started,
    docExtract,
    coverageCheck(true, 0.92),
    settlementEstimate('82500.00', 0.85),
    {
      agent: 'orchestrator',
      step: 'pipeline_awaiting_human',
      payload: {
        status: 'awaiting_human',
        escalate: true,
        fired_rule_names: ['guardrail_failed'],
        reason: 'guardrail_threw',
        error_type: 'LLMProviderError',
        error_message: 'anthropic: 529 overloaded',
      },
      afterMs: STEP_MS.terminal,
    },
  ])
}

// --- Prompt 30: the claim page ---------------------------------------------------

function summary(
  correlationId: string,
  status: RunStatus,
  startedAt: string,
  variant = 'default',
): RunSummary {
  const finished = status !== 'running'
  return {
    correlation_id: correlationId,
    variant,
    status,
    started_at: startedAt,
    completed_at: finished ? startedAt : null,
    escalate: status === 'awaiting_human' ? true : finished ? false : null,
  }
}

/** Harborline's three settled runs of 10 November 2026, newest first as the API orders them. */
export const RUN_SUMMARIES: RunSummary[] = [
  summary('f8d3cc84-0000-4000-8000-000000000001', 'settled', '2026-11-10T17:24:00.000Z'),
  summary('432cbc91-0000-4000-8000-000000000002', 'settled', '2026-11-10T17:19:00.000Z'),
  summary('f368c2c5-0000-4000-8000-000000000003', 'settled', '2026-11-10T16:20:00.000Z'),
]

/** One run that broke at the Adjuster (Background Claimant 04). */
export const ABORTED_SUMMARY = summary(
  '0aca331d-0000-4000-8000-000000000004',
  'aborted',
  '2026-11-10T15:30:00.000Z',
)

/** Northwood's run, awaiting a person. */
export const AWAITING_SUMMARY = summary(
  '67bdf225-0000-4000-8000-000000000005',
  'awaiting_human',
  '2026-11-04T11:08:00.000Z',
)

/** A run with no terminal row yet. */
export const RUNNING_SUMMARY = summary(
  'aaaaaaaa-0000-4000-8000-000000000006',
  'running',
  '2026-11-13T09:00:00.000Z',
)

export const DECIDED_AT = '2026-11-10T18:50:06.000Z'

/** Northwood's rows, then the human row api/human.py writes under the same run. */
export function decisionRows(
  decision: 'approved' | 'rejected',
  comment: string | null = 'Test rejection',
): AuditEntry[] {
  const rows = ceilingRows()
  return [
    ...rows,
    {
      audit_id: rows.length + 1,
      agent: 'human',
      step: decision === 'approved' ? 'human_approval' : 'human_rejection',
      created_at: DECIDED_AT,
      payload: { decision, decided_by: 'Dermot', comment, decided_at: DECIDED_AT },
      chain_hash: `hash-${rows.length + 1}`,
    },
  ]
}
