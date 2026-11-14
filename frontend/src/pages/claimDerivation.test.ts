import { describe, expect, it } from 'vitest'
import { FAIL_CLOSED_DESCRIPTION, ruleLine } from '../copy/run'
import {
  abortedRows,
  AWAITING_SUMMARY,
  ceilingRows,
  DECIDED_AT,
  decisionRows,
  guardrailThrewRows,
  RUN_SUMMARIES,
  settledRows,
} from '../test/runFixtures'
import {
  deriveDecision,
  deriveRunOutcome,
  deriveStoppedAt,
  deriveWhyHere,
  latestRun,
} from './claimDerivation'

describe('latestRun', () => {
  it('is the first summary, as the API orders them, or nothing', () => {
    expect(latestRun(RUN_SUMMARIES)?.correlation_id).toBe(RUN_SUMMARIES[0].correlation_id)
    expect(latestRun([])).toBeUndefined()
  })
})

describe('deriveRunOutcome', () => {
  it('adds the settled figure from the pipeline_settled row', () => {
    expect(deriveRunOutcome('settled', settledRows())).toEqual({
      kind: 'settled',
      settlement: '82500.00',
    })
  })

  it('adds the failing agent from the pipeline_aborted row', () => {
    expect(deriveRunOutcome('aborted', abortedRows())).toEqual({
      kind: 'aborted',
      failingAgent: 'Adjuster',
    })
  })

  it('reads a person’s decision from the human row, whatever the summary still says', () => {
    expect(deriveRunOutcome('awaiting_human', decisionRows('approved'))).toEqual({
      kind: 'decided',
      decision: 'approved',
    })
    expect(deriveRunOutcome('awaiting_human', decisionRows('rejected'))).toEqual({
      kind: 'decided',
      decision: 'rejected',
    })
  })

  it('carries the word alone when the rows are not there yet', () => {
    expect(deriveRunOutcome('settled', [])).toEqual({ kind: 'settled', settlement: undefined })
    expect(deriveRunOutcome('aborted', [])).toEqual({ kind: 'aborted', failingAgent: undefined })
    expect(deriveRunOutcome('awaiting_human', ceilingRows())).toEqual({ kind: 'awaiting_human' })
    expect(deriveRunOutcome('running', [])).toEqual({ kind: 'running' })
  })
})

describe('deriveStoppedAt', () => {
  it('names the agent when a mid-pipeline status meets an abort row', () => {
    expect(deriveStoppedAt('coverage_verified', abortedRows())).toBe('Adjuster')
  })

  it('says nothing for a terminal status or without an abort row', () => {
    expect(deriveStoppedAt('settled', abortedRows())).toBeNull()
    expect(deriveStoppedAt('awaiting_human', ceilingRows())).toBeNull()
    expect(deriveStoppedAt('coverage_verified', [])).toBeNull()
    expect(deriveStoppedAt('received', [])).toBeNull()
  })
})

describe('deriveDecision', () => {
  it('reads the human row api/human.py writes', () => {
    expect(deriveDecision(decisionRows('rejected'))).toEqual({
      decision: 'rejected',
      decidedBy: 'Dermot',
      comment: 'Test rejection',
      decidedAt: DECIDED_AT,
    })
    expect(deriveDecision(decisionRows('approved'))?.decision).toBe('approved')
  })

  it('treats a null or blank comment as none', () => {
    expect(deriveDecision(decisionRows('approved', null))?.comment).toBeNull()
    expect(deriveDecision(decisionRows('approved', '  '))?.comment).toBeNull()
  })

  it('is null while no person has decided', () => {
    expect(deriveDecision(ceilingRows())).toBeNull()
    expect(deriveDecision(settledRows())).toBeNull()
    expect(deriveDecision([])).toBeNull()
  })

  it('takes the last human row if there were ever two', () => {
    const rows = [...decisionRows('rejected'), ...decisionRows('approved').slice(-1)]
    expect(deriveDecision(rows)?.decision).toBe('approved')
  })
})

describe('deriveWhyHere', () => {
  it('gives the fired rules from the escalation_decision row', () => {
    expect(deriveWhyHere(ceilingRows()).map((r) => r.name)).toEqual(['settlement_over_ceiling'])
    expect(deriveWhyHere(ceilingRows()).map(ruleLine)).toEqual([
      'Settlement over the $250,000 ceiling: $820,000',
    ])
  })

  it('stands in one fail-closed rule when the Guardrail itself threw', () => {
    const rules = deriveWhyHere(guardrailThrewRows())
    expect(rules).toEqual([
      {
        name: 'guardrail_failed',
        rule_type: 'hard',
        description: FAIL_CLOSED_DESCRIPTION,
        observed_value: null,
      },
    ])
    expect(rules.map(ruleLine)).toEqual([
      'Guardrail check itself failed, so the claim went to a person',
    ])
  })

  it('is empty for a run that settled', () => {
    expect(deriveWhyHere(settledRows())).toEqual([])
    expect(AWAITING_SUMMARY.escalate).toBe(true)
  })
})
