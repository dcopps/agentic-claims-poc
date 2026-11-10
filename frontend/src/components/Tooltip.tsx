import { cloneElement, isValidElement, useId, useRef, useState, type ReactNode } from 'react'

interface TooltipProps {
  text: string
  children: ReactNode
}

// The widest a tooltip grows before its text wraps (Prompt 28).
const MAX_WIDTH_PX = 320

// A tooltip a keyboard user can reach (Prompt 28). The earlier version put the
// text in a native `title`, which browsers show on mouse hover only and never
// announce. Now the ⓘ is a real, labelled button and the text renders as a
// `role="tooltip"` element while the pointer is over the group or focus is inside
// it; the wrapped control is described by it. State-driven rather than CSS-only
// so the behaviour is observable in tests. Callers are unchanged.
//
// The box sets its own white-space and width, because a caller may sit inside a
// `whitespace-nowrap` table cell: without `whitespace-normal` the text would run
// on in one line past the box. It is anchored to the group's left edge unless
// that would carry it past the right of the viewport, in which case it is
// anchored to the right edge instead, so it never leaves the visible page.
export function Tooltip({ text, children }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const [alignRight, setAlignRight] = useState(false)
  const group = useRef<HTMLSpanElement>(null)
  const id = useId()
  const described = isValidElement<{ 'aria-describedby'?: string }>(children)
    ? cloneElement(children, { 'aria-describedby': id })
    : children

  const show = () => {
    const box = group.current?.getBoundingClientRect()
    setAlignRight(box !== undefined && box.left + MAX_WIDTH_PX > window.innerWidth)
    setOpen(true)
  }
  const hide = () => setOpen(false)

  return (
    <span
      ref={group}
      className="relative inline-flex items-center gap-1"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {described}
      <button
        type="button"
        aria-label="About this action"
        className="rounded text-xs text-slate-400 hover:text-slate-600 focus:text-slate-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-slate-400"
      >
        ⓘ
      </button>
      {open && (
        <span
          role="tooltip"
          id={id}
          style={{ maxWidth: MAX_WIDTH_PX }}
          className={`absolute top-full z-30 mt-1 w-max whitespace-normal break-words rounded bg-slate-800 px-3 py-2 text-left text-xs font-normal leading-snug text-white shadow-lg ${alignRight ? 'right-0' : 'left-0'}`}
        >
          {text}
        </span>
      )}
    </span>
  )
}
