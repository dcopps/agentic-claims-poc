import { describe, expect, it } from 'vitest'
import { formatDate, formatDateTime, formatPercent, formatSeconds, formatUsd } from './format'

describe('formatUsd', () => {
  it('shows whole dollars without cents', () => {
    expect(formatUsd('850000.00')).toBe('$850,000')
    expect(formatUsd('1400000.00')).toBe('$1,400,000')
    expect(formatUsd(85000)).toBe('$85,000')
  })

  it('keeps cents only when they are not zero', () => {
    expect(formatUsd('85000.50')).toBe('$85,000.50')
    expect(formatUsd('0.07')).toBe('$0.07')
  })

  it('returns the raw value when it does not parse', () => {
    expect(formatUsd('abc')).toBe('abc')
    expect(formatUsd('')).toBe('')
  })
})

describe('formatDateTime', () => {
  // Locale and time zone are fixed here so the test does not depend on the machine.
  const fixed = { locale: 'en-GB', timeZone: 'UTC' }

  it('gives a short date and time in the given locale', () => {
    const text = formatDateTime('2026-11-04T11:08:00Z', fixed)
    expect(text).toContain('4 Nov 2026')
    expect(text).toContain('11:08')
  })

  it('returns the raw string when it does not parse', () => {
    expect(formatDateTime('not a date', fixed)).toBe('not a date')
  })
})

// Prompt 30: the loss and reported dates are calendar dates.
describe('formatDate', () => {
  it('gives a short date with no time', () => {
    expect(formatDate('2026-02-10', { locale: 'en-GB' })).toBe('10 Feb 2026')
    expect(formatDate('2026-11-01', { locale: 'en-US' })).toBe('Nov 1, 2026')
  })

  it('does not shift the day with the zone, which formatDateTime would', () => {
    // The hazard: "2026-02-10" is midnight UTC, the evening of the 9th in New York.
    expect(
      formatDateTime('2026-02-10', { locale: 'en-GB', timeZone: 'America/New_York' }),
    ).toContain('9 Feb 2026')
    expect(formatDate('2026-02-10', { locale: 'en-GB' })).toBe('10 Feb 2026')
  })

  it('returns the raw string when it does not parse', () => {
    expect(formatDate('yesterday', { locale: 'en-GB' })).toBe('yesterday')
  })
})

describe('formatSeconds', () => {
  it('gives seconds to one decimal place', () => {
    expect(formatSeconds(3421)).toBe('3.4 s')
    expect(formatSeconds(0)).toBe('0.0 s')
    expect(formatSeconds(27900)).toBe('27.9 s')
  })
})

describe('formatPercent', () => {
  it('shows a fraction as a whole percentage', () => {
    expect(formatPercent(0.92)).toBe('92%')
    expect(formatPercent(0.585)).toBe('59%')
    expect(formatPercent(1)).toBe('100%')
  })
})
