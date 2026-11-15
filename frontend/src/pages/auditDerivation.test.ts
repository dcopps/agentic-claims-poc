import { describe, expect, it } from 'vitest'
import type { AuditEntry } from '../api/types'
import {
  abortedRows,
  ceilingRows,
  decisionRows,
  guardrailFailureRows,
  guardrailThrewRows,
  settledRows,
} from '../test/runFixtures'
import {
  classifyRunId,
  deriveStartedAt,
  extractPrompt,
  isDemoFixture,
  recordHeader,
  rowAuthor,
  rowSentence,
  stepName,
} from './auditDerivation'

function entry(partial: Partial<AuditEntry>): AuditEntry {
  return {
    audit_id: 1,
    agent: 'orchestrator',
    step: 'pipeline_started',
    created_at: '2026-11-15T15:09:08Z',
    payload: {},
    chain_hash: 'hash',
    ...partial,
  }
}

// Prompt 32: one sentence per record, the run page's own wherever it has one.
describe('rowSentence', () => {
  it('reads a settled run in seven sentences', () => {
    expect(settledRows().map(rowSentence)).toEqual([
      'Run started: Standard run',
      'Summarised the claim (Water damage)',
      'Covered (92% confident)',
      'Recommends $82,500 (85% confident)',
      'Passed',
      'No rule fired; the claim settles',
      'Settled at $82,500',
    ])
  })

  it('reads the ceiling rule and the wait for a person', () => {
    const rows = ceilingRows()
    expect(rowSentence(rows[5])).toBe(
      'Sent to a person: Settlement over the $250,000 ceiling: $820,000',
    )
    expect(rowSentence(rows[6])).toBe('Awaiting human review')
  })

  it('reads the fixture Adjuster, the Guardrail failure and two rules', () => {
    const rows = guardrailFailureRows()
    expect(rowSentence(rows[3])).toBe(
      'Recommends $1,400,000 from the fixed demonstration file, no model call (82% confident)',
    )
    expect(rowSentence(rows[4])).toBe('Failed: cited policy wording the policy does not contain')
    expect(rowSentence(rows[5])).toBe(
      'Sent to a person: Guardrail check did not pass; Settlement over the $250,000 ceiling: $1,400,000',
    )
  })

  it('reads an abort, the fail-closed wait, and a decision', () => {
    expect(rowSentence(abortedRows()[3])).toBe(
      'Run aborted: the Adjuster has no market range for the claim type Smoke damage',
    )
    expect(rowSentence(guardrailThrewRows()[4])).toBe(
      'Awaiting human review: Guardrail check itself failed, so the claim went to a person',
    )
    expect(rowSentence(decisionRows('approved').at(-1)!)).toBe('Approved by Dermot')
    expect(rowSentence(decisionRows('rejected').at(-1)!)).toBe('Rejected by Dermot')
  })

  it('reads an agent row whose model call failed, and an unknown step', () => {
    const failed = entry({
      agent: 'validator',
      step: 'coverage_check',
      payload: { error: { type: 'LLMProviderError', message: 'anthropic: 529 overloaded' } },
    })
    expect(rowSentence(failed)).toBe('Failed: the model provider refused or failed the call')
    expect(rowSentence(entry({ step: 'custom_step' }))).toBe('Custom step')
    expect(rowSentence(entry({ step: 'pipeline_started', payload: {} }))).toBe(
      'Run started: Standard run',
    )
  })
})

describe('rowAuthor, stepName and recordHeader', () => {
  it('names who wrote the record in words', () => {
    expect(rowAuthor(entry({ agent: 'doc_parser' }))).toBe('Doc-Parser')
    expect(rowAuthor(entry({ agent: 'guardrail' }))).toBe('Guardrail')
    expect(rowAuthor(entry({ agent: 'orchestrator' }))).toBe('Orchestrator')
    expect(rowAuthor(entry({ agent: 'human' }))).toBe('A person')
    expect(rowAuthor(entry({ agent: 'robot_two' }))).toBe('Robot two')
  })

  it('names the step and composes the header line', () => {
    const row = entry({ audit_id: 210, agent: 'validator', step: 'coverage_check' })
    expect(stepName(row)).toBe('coverage check')
    expect(stepName(entry({ step: 'human_rejection' }))).toBe('rejection')
    expect(stepName(entry({ step: 'custom_step' }))).toBe('Custom step')
    const header = recordHeader(row)
    expect(header).toMatch(/^Validator · coverage check · .+ · record 210 in the ledger$/)
    expect(header).toContain('09:08')
  })
})

describe('classifyRunId', () => {
  const FULL = 'F23EA4DC-2292-480E-8B4B-344EB1464B0A'

  it('loads a whole id as typed, lower-cased', () => {
    expect(classifyRunId(` ${FULL} `)).toEqual({ kind: 'full', value: FULL.toLowerCase() })
  })

  it('resolves eight or more characters and refuses fewer on the page', () => {
    expect(classifyRunId('f23ea4dc')).toEqual({ kind: 'short', value: 'f23ea4dc' })
    expect(classifyRunId('f23ea4dc-2292')).toEqual({ kind: 'short', value: 'f23ea4dc-2292' })
    expect(classifyRunId('f23ea4d')).toEqual({ kind: 'too_short' })
    expect(classifyRunId('2bd0')).toEqual({ kind: 'too_short' })
  })

  it('refuses characters a run id never has', () => {
    expect(classifyRunId('')).toEqual({ kind: 'invalid' })
    expect(classifyRunId('run f23ea4dc')).toEqual({ kind: 'invalid' })
  })
})

describe('extractPrompt, isDemoFixture and deriveStartedAt', () => {
  it('finds the instructions under llm_call.prompt and nothing elsewhere', () => {
    const withPrompt = entry({
      payload: { llm_call: { prompt: { system: 'SYS', user: 'USR' } } },
    })
    expect(extractPrompt(withPrompt)).toEqual({ system: 'SYS', user: 'USR' })
    expect(extractPrompt(guardrailFailureRows()[3])).toBeNull()
    expect(extractPrompt(entry({ payload: { llm_call: { prompt: { system: 1 } } } }))).toBeNull()
    expect(extractPrompt(undefined)).toBeNull()
  })

  it('knows the fixture record', () => {
    expect(isDemoFixture(guardrailFailureRows()[3])).toBe(true)
    expect(isDemoFixture(settledRows()[3])).toBe(false)
    expect(isDemoFixture(entry({ payload: { llm_call: { provider: 'demo_fixture' } } }))).toBe(true)
  })

  it('takes the recorded start, else the first row’s time', () => {
    expect(
      deriveStartedAt([entry({ payload: { started_at: '2026-11-15T15:09:03.9+00:00' } })]),
    ).toBe('2026-11-15T15:09:03.9+00:00')
    expect(deriveStartedAt(settledRows())).toBe(settledRows()[0].created_at)
    expect(deriveStartedAt([])).toBeUndefined()
  })
})
