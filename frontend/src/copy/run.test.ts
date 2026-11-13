// This test reads a file from the backend tree, so it alone needs Node's
// types; the app's tsconfig stays browser-only. @types/node is already a
// devDependency of the frontend.
/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { failureReason, RULE_THRESHOLDS, ruleLine, runCopy } from './run'

// Prompt 29: every sentence the run page can show, and the thresholds the rule
// lines quote checked against the policy file itself (plan D3).
describe('run copy: the cards', () => {
  it('summarises each agent in one line with the confidence as a percentage in brackets', () => {
    expect(runCopy.docParser('water_damage')).toBe('Summarised the claim (Water damage)')
    expect(runCopy.validator(true, 0.92)).toBe('Covered (92% confident)')
    expect(runCopy.validator(false, 0.41)).toBe('Not covered (41% confident)')
    expect(runCopy.adjuster('82500.00', 0.85)).toBe('Recommends $82,500 (85% confident)')
    expect(runCopy.adjuster('1400000.00', 0.82, true)).toBe(
      'Recommends $1,400,000 from the fixed demonstration file, no model call (82% confident)',
    )
  })

  it('leaves the bracket off while only the live event is known', () => {
    expect(runCopy.validator(true)).toBe('Covered')
    expect(runCopy.adjuster('82500.00')).toBe('Recommends $82,500')
  })

  it('gives the Guardrail’s verdict with its refusals or its findings', () => {
    expect(runCopy.guardrailPassed(0)).toBe('Passed')
    expect(runCopy.guardrailPassed(1)).toBe('Passed; 1 objection refused')
    expect(runCopy.guardrailPassed(3)).toBe('Passed; 3 objections refused')
    expect(runCopy.guardrailFailed(['hallucinated_citation', 'pii'])).toBe(
      'Failed: cited policy wording the policy does not contain; personal data in the reasoning',
    )
    expect(runCopy.guardrailFailed([])).toBe('Failed')
  })

  it('words the other states', () => {
    expect(runCopy.waiting).toBe('Waiting')
    expect(runCopy.notRun('Adjuster')).toBe('Not run: the run stopped at the Adjuster')
    expect(runCopy.failed('the Adjuster raised ValueError')).toBe(
      'Failed: the Adjuster raised ValueError',
    )
    expect(runCopy.guardrailThrew).toBe(
      'Failed: the check itself raised an error, so the claim went to a person',
    )
    expect(runCopy.notFound).toBe('Run not found.')
    expect(runCopy.loading).toBe('Loading this run…')
    expect(runCopy.awaiting).toBe('Waiting for the run to begin…')
    expect(runCopy.aborted('the Adjuster raised ValueError')).toBe(
      'Run aborted: the Adjuster raised ValueError',
    )
  })
})

describe('run copy: the claim line', () => {
  it('gives the type, amount and claim number in plain words after the claimant’s name', () => {
    expect(runCopy.claimDetails('water_damage', '85000.00', 'CLM-2026-9BB57A86')).toBe(
      'Water damage · $85,000 · claim CLM-2026-9BB57A86',
    )
    expect(runCopy.claimDetails('smoke_damage', '29925.00', 'CLM-2026-56AF95EC')).toBe(
      'Smoke damage · $29,925 · claim CLM-2026-56AF95EC',
    )
    expect(runCopy.claimUnavailable).toBe('The claim this run belongs to could not be loaded.')
  })
})

describe('run copy: failure reasons', () => {
  it('names the missing market range and its claim type from the message', () => {
    expect(
      failureReason(
        'Adjuster',
        'ValueError',
        "MarketDataTable.lookup: unknown claim_type 'smoke_damage' (normalised='smoke_damage'); supported types=[]",
      ),
    ).toBe('the Adjuster has no market range for the claim type Smoke damage')
  })

  it('names a provider failure, and otherwise who raised what', () => {
    expect(failureReason('Validator', 'LLMProviderError', 'anthropic: 529')).toBe(
      'the model provider refused or failed the call',
    )
    expect(failureReason('Doc-Parser', 'ValueError', 'claim not found')).toBe(
      'the Doc-Parser raised ValueError',
    )
    expect(
      failureReason('Adjuster', 'KeyError', "MarketDataTable.lookup: unknown claim_type 'hail'"),
    ).toBe('the Adjuster raised KeyError')
  })
})

describe('run copy: the rule lines', () => {
  const rule = (name: string, description: string, observed: string | null = null) => ({
    name,
    rule_type: 'threshold',
    description,
    observed_value: observed,
  })

  it('words each rule with its observed value', () => {
    expect(ruleLine(rule('settlement_over_ceiling', 'settlement > $250,000', '820000.00'))).toBe(
      'Settlement over the $250,000 ceiling: $820,000',
    )
    expect(
      ruleLine(rule('validator_confidence_floor', 'validator confidence < 0.65', '0.58')),
    ).toBe('Validator confidence below the 65% floor (58% confident)')
    expect(ruleLine(rule('adjuster_confidence_floor', 'adjuster confidence < 0.75', '0.7'))).toBe(
      'Adjuster confidence below the 75% floor (70% confident)',
    )
    expect(ruleLine(rule('guardrail_failed', 'Guardrail output check did not pass'))).toBe(
      'Guardrail check did not pass',
    )
    expect(
      ruleLine(rule('guardrail_failed', 'Guardrail check raised an exception; failing closed')),
    ).toBe('Guardrail check itself failed, so the claim went to a person')
    expect(ruleLine(rule('claim_type_watchlist', 'x'))).toBe('Claim type is on the watchlist')
    expect(ruleLine(rule('claimant_watchlist', 'x'))).toBe('Claimant is on the watchlist')
    expect(ruleLine(rule('cross_jurisdictional', 'x'))).toBe(
      'Claim spans more than one jurisdiction',
    )
  })

  it('falls back to the rule’s own description for a rule it does not know', () => {
    expect(ruleLine(rule('reserve_over_limit', 'reserve > $1,000,000', '1200000'))).toBe(
      'reserve > $1,000,000: 1200000',
    )
    expect(ruleLine(rule('reserve_over_limit', 'reserve > $1,000,000'))).toBe(
      'reserve > $1,000,000',
    )
  })

  // The thresholds typed into the copy module must be the ones in
  // backend/app/escalation/policy.yaml, read here from the file (plan D3).
  it('quotes the thresholds policy.yaml holds', () => {
    const policy = readFileSync(
      resolve(__dirname, '../../../backend/app/escalation/policy.yaml'),
      'utf8',
    )
    const fromFile: Record<string, string> = {}
    let current: string | null = null
    for (const line of policy.split('\n')) {
      const name = /^\s*-\s*name:\s*(\S+)/.exec(line)
      if (name) current = name[1]
      const value = /^\s*value:\s*"([^"]+)"/.exec(line)
      if (value && current) fromFile[current] = value[1]
    }
    expect(fromFile).toEqual(RULE_THRESHOLDS)
  })
})
