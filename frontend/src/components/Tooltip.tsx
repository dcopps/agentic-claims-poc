import {
  cloneElement,
  isValidElement,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

interface TooltipProps {
  text: string
  children: ReactNode
}

// The widest a tooltip grows before its text wraps (Prompt 28).
const MAX_WIDTH_PX = 320

interface Placement {
  alignRight: boolean
  above: boolean
}

const DEFAULT_PLACEMENT: Placement = { alignRight: false, above: false }

// A tooltip a keyboard user can reach (Prompt 28). The earlier version put the
// text in a native `title`, which browsers show on mouse hover only and never
// announce. Now the ⓘ is a real, labelled button and the text renders as a
// `role="tooltip"` element while the pointer is over the group or focus is inside
// it; the wrapped control is described by it. State-driven rather than CSS-only
// so the behaviour is observable in tests. Callers are unchanged.
//
// The box sets its own white-space and width, because a caller may sit inside a
// `whitespace-nowrap` table cell: without `whitespace-normal` the text would run
// on in one line past the box. It opens below and to the right of its group, then
// measures itself: if it would pass the right edge of the viewport it anchors to
// the group's right edge instead, and if it would pass the bottom it opens above.
// So it never leaves the visible page.
export function Tooltip({ text, children }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<Placement>(DEFAULT_PLACEMENT)
  const tip = useRef<HTMLSpanElement>(null)
  const id = useId()
  const described = isValidElement<{ 'aria-describedby'?: string }>(children)
    ? cloneElement(children, { 'aria-describedby': id })
    : children

  // Measured once per opening, before paint, from the default placement.
  useLayoutEffect(() => {
    if (!open) return
    setPlacement(DEFAULT_PLACEMENT)
    const box = tip.current?.getBoundingClientRect()
    if (!box) return
    setPlacement({
      alignRight: box.right > window.innerWidth,
      above: box.bottom > window.innerHeight,
    })
  }, [open])

  const horizontal = placement.alignRight ? 'right-0' : 'left-0'
  const vertical = placement.above ? 'bottom-full mb-1' : 'top-full mt-1'

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
        className="rounded text-xs text-slate-400 hover:text-slate-600 focus:text-slate-600 focus:outline-none focus-visible:ring-1 focus-visible:ring-slate-400"
      >
        ⓘ
      </button>
      {open && (
        <span
          ref={tip}
          role="tooltip"
          id={id}
          style={{ maxWidth: MAX_WIDTH_PX }}
          className={`absolute z-30 w-max whitespace-normal break-words rounded bg-slate-800 px-3 py-2 text-left text-xs font-normal leading-snug text-white shadow-lg ${horizontal} ${vertical}`}
        >
          {text}
        </span>
      )}
    </span>
  )
}
