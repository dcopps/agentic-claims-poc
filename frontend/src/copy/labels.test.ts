import { describe, expect, it } from 'vitest'
import {
  claimStatusLabel,
  claimTypeLabel,
  guardrailFinding,
  readableFallback,
  refusalReason,
  runStatusLabel,
  variantLabel,
} from './labels'

describe('labels', () => {
  it('maps every claim type the form offers or the seed generator produces', () => {
    expect(
      [
        'water_damage',
        'fire',
        'wind',
        'theft',
        'flood',
        'storm_complex',
        'sprinkler_leakage',
        'vandalism',
        'smoke_damage',
        'hail',
        'windstorm',
      ].map(claimTypeLabel),
    ).toEqual([
      'Water damage',
      'Fire',
      'Wind',
      'Theft',
      'Flood',
      'Storm (complex)',
      'Sprinkler leakage',
      'Vandalism',
      'Smoke damage',
      'Hail',
      'Windstorm',
    ])
  })

  // Prompt 30 (D4): a claim is stored `aborted` only by a person's rejection,
  // so the claim's word is Rejected; a run's `aborted` means an agent broke.
  it('maps every claim status, reading a stored aborted claim as Rejected', () => {
    expect(
      [
        'received',
        'extracted',
        'coverage_verified',
        'estimated',
        'guardrail_checked',
        'settled',
        'awaiting_human',
        'aborted',
      ].map(claimStatusLabel),
    ).toEqual([
      'Received',
      'Summarised',
      'Coverage checked',
      'Settlement estimated',
      'Guardrail checked',
      'Settled',
      'Awaiting human review',
      'Rejected',
    ])
  })

  it('maps the run statuses, keeping Aborted for a run that broke', () => {
    expect(['running', 'settled', 'awaiting_human', 'aborted'].map(runStatusLabel)).toEqual([
      'Running',
      'Settled',
      'Awaiting human review',
      'Aborted',
    ])
  })

  it('shows an unmapped claim type in a readable fallback form, never hidden', () => {
    expect(claimTypeLabel('hail_storm')).toBe('Hail storm')
    expect(claimTypeLabel('subsidence')).toBe('Subsidence')
    expect(claimTypeLabel('')).toBe('')
  })

  it('shows an unmapped status the same way', () => {
    expect(claimStatusLabel('under_review')).toBe('Under review')
    expect(runStatusLabel('timed_out')).toBe('Timed out')
    expect(readableFallback('  two__words ')).toBe('Two words')
  })

  // Prompt 29: the run page's words.
  it('names the three replay variants as sentences and reads any other one', () => {
    expect(['default', 'v2_strict_validator', 'v1_mistral'].map(variantLabel)).toEqual([
      'Standard run',
      'Strict Validator run',
      'Mistral run',
    ])
    expect(variantLabel('v3_haiku_adjuster')).toBe('V3 haiku adjuster run')
  })

  it('gives the three refusal reasons in words and reads any other code', () => {
    expect(
      ['no_quote', 'quote_not_in_reasoning', 'quote_not_a_provision'].map(refusalReason),
    ).toEqual([
      'the model gave no quotation',
      'those words are not in the Adjuster’s reasoning',
      'those words do not name a policy provision',
    ])
    expect(refusalReason('quote_too_short')).toBe('Quote too short')
  })

  it('names what a Guardrail flag of each kind found', () => {
    expect(['hallucinated_citation', 'pii', 'bias'].map(guardrailFinding)).toEqual([
      'cited policy wording the policy does not contain',
      'personal data in the reasoning',
      'biased language in the reasoning',
    ])
    expect(guardrailFinding('profanity')).toBe('Profanity')
  })
})
