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
