// Design-system tokens — the single source for colour, status mapping, and
// typography. Components reference these rather than hardcoding Tailwind classes
// for status colours, so the visual language stays consistent and Phase 7 can
// retune in one place. Locked at end of Phase 6.

export const colors = {
  primary: '#2563eb',
  success: '#16a34a',
  warning: '#d97706',
  danger: '#dc2626',
  ink: '#0f172a',
  muted: '#475569',
  faint: '#94a3b8',
  line: '#e2e8f0',
  surface: '#f8fafc',
} as const

// Tailwind class sets per status badge. The four mid-pipeline statuses share a
// blue progression; terminal/escalation states get their own semantics.
export const statusBadgeClass: Record<string, string> = {
  received: 'bg-slate-100 text-slate-700',
  extracted: 'bg-blue-50 text-blue-700',
  coverage_verified: 'bg-blue-100 text-blue-700',
  estimated: 'bg-blue-100 text-blue-800',
  guardrail_checked: 'bg-indigo-100 text-indigo-800',
  settled: 'bg-green-100 text-green-800',
  awaiting_human: 'bg-amber-100 text-amber-800',
  aborted: 'bg-red-100 text-red-800',
  // Run statuses
  running: 'bg-blue-100 text-blue-800 animate-pulse',
}

export const typography = {
  pageTitle: 'text-2xl font-semibold',
  sectionTitle: 'text-lg font-medium',
  body: 'text-sm',
  caption: 'text-xs text-slate-500',
  mono: 'font-mono text-xs',
} as const
