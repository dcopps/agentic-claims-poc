import type { ReactNode } from 'react'

interface TooltipProps {
  text: string
  children: ReactNode
}

// Minimal tooltip: wraps its child and exposes the production-equivalent copy via
// the native `title` attribute (hover to read; queryable by title in tests).
// Phase 6 polish can replace this with a styled popover without touching callers.
export function Tooltip({ text, children }: TooltipProps) {
  return (
    <span title={text} className="inline-flex items-center gap-1">
      {children}
      <span className="text-slate-400 text-xs" aria-hidden="true">
        ⓘ
      </span>
    </span>
  )
}
