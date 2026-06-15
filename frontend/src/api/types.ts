// TypeScript mirrors of the backend Pydantic models. Kept in one place so the
// fetch client and the components share a single source of truth. Monetary
// fields arrive as strings (the backend serialises Decimal as a string), so they
// are typed as string here too.

export type ClaimStatus =
  | 'received'
  | 'extracted'
  | 'coverage_verified'
  | 'estimated'
  | 'guardrail_checked'
  | 'settled'
  | 'awaiting_human'

export type ClaimType =
  | 'water_damage'
  | 'fire'
  | 'wind'
  | 'theft'
  | 'flood'
  | 'storm_complex'

export type ScenarioTag =
  | 'auto_approve'
  | 'threshold_escalation'
  | 'guardrail_escalation'

export interface ClaimSubmission {
  claimant_name: string
  policy_number: string
  loss_date: string
  reported_date: string
  jurisdiction: string
  narrative: string
  claim_type: ClaimType
  reported_amount: string
  scenario_tag?: ScenarioTag | null
}

export interface ClaimRecord {
  claim_id: string
  claim_number: string
  line_of_business: string
  claimant_name: string
  policy_number: string
  loss_date: string
  reported_date: string
  jurisdiction: string
  narrative: string
  claim_type: string
  reported_amount: string
  status: ClaimStatus
  scenario_tag: ScenarioTag | null
  created_at: string
  updated_at: string
}

export type RunStatus = 'running' | 'settled' | 'awaiting_human' | 'aborted'

export interface RunSummary {
  correlation_id: string
  variant: string
  status: RunStatus
  started_at: string
  completed_at: string | null
  escalate: boolean | null
}

export interface FiredRule {
  name: string
  rule_type: string
  description: string
  observed_value?: string | null
}

export interface EscalationDecision {
  escalate: boolean
  fired_rules: FiredRule[]
  reasoning: string
}

export interface AdjusterOutput {
  recommended_settlement: string
  confidence: number
  reasoning: string
}

export interface GuardrailOutput {
  passed: boolean
  summary: string
}

export interface PipelineResult {
  status: string
  claim_id: string
  correlation_id: string
  escalation_decision: EscalationDecision | null
  adjuster_output: AdjusterOutput | null
  guardrail_output: GuardrailOutput | null
  aborted_agent?: string | null
  error_type?: string | null
  completed_at: string
}

export interface DiffSummary {
  settlement_changed: boolean
  settlement_a: string | null
  settlement_b: string | null
  escalation_changed: boolean
  escalate_a: boolean | null
  escalate_b: boolean | null
  fired_rules_added: string[]
  fired_rules_removed: string[]
  guardrail_changed: boolean
  guardrail_passed_a: boolean | null
  guardrail_passed_b: boolean | null
}

export interface RunComparison {
  run_a: PipelineResult
  run_b: PipelineResult
  diff: DiffSummary
}

export interface AuditEntry {
  audit_id: number
  agent: string
  step: string
  created_at: string
  payload: Record<string, unknown>
  chain_hash: string
}

export interface AuditBreak {
  audit_id: number
  kind: string
  expected: string
  actual: string
}

export interface ChainVerification {
  ok: boolean
  rows_checked: number
  first_break: AuditBreak | null
}

export interface HumanDecisionBody {
  decision: 'approved' | 'rejected'
  decided_by: string
  comment?: string | null
}

export interface AgentPrompt {
  agent: string
  variant: string
  system: string
  user: string
}

// A loosely-typed SSE event — the strip reads a handful of fields by name.
export interface PipelineEvent {
  event_type: string
  correlation_id: string
  timestamp: string
  claim_id?: string
  variant?: string
  agent?: string
  duration_ms?: number
  summary?: Record<string, unknown>
  escalate?: boolean
  status?: string
  failing_agent?: string
  error_type?: string
  message?: string
}
