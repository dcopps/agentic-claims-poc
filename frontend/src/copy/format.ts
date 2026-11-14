// Display formatting for the values the API stores as strings (Prompt 28). Both
// helpers return the raw input unchanged when it does not parse: a value a reader
// cannot interpret is still better shown than hidden, and a formatter must never
// be the thing that breaks a page.

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

const USD_CENTS = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

// "850000.00" → "$850,000"; "85000.50" → "$85,000.50"; "abc" → "abc". Cents are
// shown as two digits or not at all: "$85,000.5" would read as a typo.
export function formatUsd(value: string | number): string {
  const amount = typeof value === 'number' ? value : Number(value.trim())
  if (value === '' || Number.isNaN(amount)) return String(value)
  const wholeDollars = Math.round(amount * 100) % 100 === 0
  return (wholeDollars ? USD : USD_CENTS).format(amount)
}

export interface DateTimeOptions {
  locale?: string
  timeZone?: string
}

// A short date and time in the reader's locale: "4 Nov 2026, 11:08" in en-GB,
// "Nov 4, 2026, 11:08 AM" in en-US. `locale` and `timeZone` exist so tests do
// not depend on the machine they run on; callers leave them unset.
export function formatDateTime(iso: string, options: DateTimeOptions = {}): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat(options.locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: options.timeZone,
  }).format(date)
}

// A date-only value, "2026-02-10" → "10 Feb 2026" (Prompt 30). The loss and
// reported dates are calendar dates with no time, and `new Date('2026-02-10')`
// is midnight UTC, which `formatDateTime` would print as 9 February anywhere
// west of Greenwich. So the zone is fixed to UTC here and is not an option: a
// calendar date must read the same in every zone. Unparseable input is returned
// as is, like the others.
export function formatDate(isoDate: string, options: Pick<DateTimeOptions, 'locale'> = {}): string {
  const date = new Date(isoDate)
  if (Number.isNaN(date.getTime())) return isoDate
  return new Intl.DateTimeFormat(options.locale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(date)
}

// Milliseconds as seconds to one decimal: 3421 → "3.4 s", 0 → "0.0 s" (Prompt 29).
// A card's duration is read at a glance, so one decimal is the whole of the
// precision shown; the millisecond value stays in the audit trail.
export function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

// A confidence held as a fraction, shown as a whole percentage: 0.92 → "92%".
// Dermot, 11 November 2026: a confidence is shown as a percentage in brackets,
// "Covered (92% confident)", so the fraction never reaches the page.
export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`
}
