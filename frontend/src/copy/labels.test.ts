import { describe, expect, it } from 'vitest'
import {
  claimTypeLabel,
  guardrailFinding,
  readableFallback,
  refusalReason,
  statusLabel,
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

  it('maps every claim status and the run status', () => {
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
        'running',
      ].map(statusLabel),
    ).toEqual([
      'Received',
      'Summarised',
      'Coverage checked',
      'Settlement estimated',
      'Guardrail checked',
      'Settled',
      'Awaiting human review',
      'Aborted',
      'Running',
    ])
  })

  it('shows an unmapped claim type in a readable fallback form, never hidden', () => {
    expect(claimTypeLabel('hail_storm')).toBe('Hail storm')
    expect(claimTypeLabel('subsidence')).toBe('Subsidence')
    expect(claimTypeLabel('')).toBe('')
  })

  it('shows an unmapped status the same way', () => {
    expect(statusLabel('under_review')).toBe('Under review')
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
