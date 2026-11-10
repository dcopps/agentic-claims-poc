// Internal UI primitives — small, hand-rolled, Tailwind-native. No component
// library (D3). Components across the app compose these so the visual language
// stays consistent.

import { type ButtonHTMLAttributes, type ReactNode, useEffect, useState } from 'react'
import { statusBadgeClass } from '../styles/tokens'

// How long the "Copied" confirmation shows before reverting to the label.
const COPY_FEEDBACK_MS = 1500

type ButtonVariant = 'primary' | 'secondary' | 'danger'
type ButtonSize = 'md' | 'sm'

// Primary is solid blue matching the link colour (text-blue-700); secondary is
// the same blue as an outline on white; danger stays red. Disabled keeps the
// greyed look (Prompt 28).
const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-blue-700 text-white hover:bg-blue-800',
  secondary: 'border border-blue-700 bg-white text-blue-700 hover:bg-blue-50',
  danger: 'bg-red-600 text-white hover:bg-red-500',
}

// `sm` is for dense places such as a table row, where two actions share a line.
const BUTTON_SIZE: Record<ButtonSize, string> = {
  md: 'px-3 py-1.5 text-sm',
  sm: 'px-2 py-1 text-xs',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

export function Button({ variant = 'primary', size = 'md', className = '', ...rest }: ButtonProps) {
  return (
    <button
      className={`rounded whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_SIZE[size]} ${BUTTON_VARIANT[variant]} ${className}`}
      {...rest}
    />
  )
}

// Copy-to-clipboard button with a brief "Copied" confirmation. Used for sharing
// the full correlation id from the run header. The revert timer lives in an
// effect so it is cleared on unmount — no setState-after-unmount warning.
export function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const id = setTimeout(() => setCopied(false), COPY_FEEDBACK_MS)
    return () => clearTimeout(id)
  }, [copied])
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(value)
        setCopied(true)
      }}
      className="rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
    >
      {copied ? 'Copied' : label}
    </button>
  )
}

// `label` (Prompt 28) is the plain-words text a page may show in place of the
// stored value; the colour is always looked up by the stored value, so the two
// cannot drift. Pages that pass nothing still show the raw status.
export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const cls = statusBadgeClass[status] ?? 'bg-slate-100 text-slate-700'
  const font = label ? '' : 'font-mono '
  return (
    <span className={`inline-block whitespace-nowrap rounded px-2 py-0.5 ${font}text-xs ${cls}`}>
      {label ?? status}
    </span>
  )
}

type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger'

const BADGE_TONE: Record<BadgeTone, string> = {
  neutral: 'bg-slate-100 text-slate-700',
  success: 'bg-green-100 text-green-800',
  // Amber marks the one MCP tool that changes something (Phase 10).
  warning: 'bg-amber-100 text-amber-800',
  danger: 'bg-red-100 text-red-800',
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs ${BADGE_TONE[tone]}`}>
      {children}
    </span>
  )
}

export function Card({ title, children }: { title?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded border border-slate-200 bg-white p-4">
      {title && <h2 className="mb-3 text-lg font-medium">{title}</h2>}
      {children}
    </section>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <span className="text-sm text-slate-500" role="status">
      {label}
    </span>
  )
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
    >
      {message}
    </div>
  )
}

export function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}
