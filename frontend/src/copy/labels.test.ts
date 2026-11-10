import { describe, expect, it } from 'vitest'
import { claimTypeLabel, readableFallback, statusLabel } from './labels'

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
})
