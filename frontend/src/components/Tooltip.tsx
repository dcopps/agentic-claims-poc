import { cloneElement, isValidElement, useId, useState, type ReactNode } from 'react'

interface TooltipProps {
  text: string
  children: ReactNode
}

// A tooltip a keyboard user can reach (Prompt 28). The earlier version put the
// text in a native `title`, which browsers show on mouse hover only and never
// announce. Now the ⓘ is a real, labelled button and the text renders as a
// `role="tooltip"` element while the pointer is over the group or focus is inside
// it; the wrapped control is described by it. State-driven rather than CSS-only
// so the behaviour is observable in tests. Callers are unchanged.
export function Tooltip({ text, children }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const described = isValidElement<{ 'aria-describedby'?: string }>(children)
    ? cloneElement(children, { 'aria-describedby': id })
    : children

  return (
    <span
      className="relative inline-flex items-center gap-1"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      {described}
      <button
        type="button"
        aria-label="About this action"
        className="text-xs text-slate-400 hover:text-slate-600 focus:text-slate-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-slate-400 rounded"
      >
        ⓘ
      </button>
      {open && (
        <span
          role="tooltip"
          id={id}
          className="absolute left-0 top-full z-20 mt-1 w-72 rounded border border-slate-200 bg-white p-2 text-xs font-normal text-slate-700 shadow"
        >
          {text}
        </span>
      )}
    </span>
  )
}
