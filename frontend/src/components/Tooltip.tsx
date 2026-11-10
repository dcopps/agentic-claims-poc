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
// The gap between the control and the box.
const GAP_PX = 4

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
// measures itself before paint: if it would pass the right edge of the viewport
// it anchors to the group's right edge instead, and if it would pass the bottom
// it opens above. So it never leaves the visible page.
export function Tooltip({ text, children }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const tip = useRef<HTMLSpanElement>(null)
  const id = useId()
  const described = isValidElement<{ 'aria-describedby'?: string }>(children)
    ? cloneElement(children, { 'aria-describedby': id })
    : children

  // Placement is written straight to the element: measuring needs the box in the
  // document, and a state update here would re-render for a value only the box
  // itself uses.
  useLayoutEffect(() => {
    if (open) place(tip.current)
  }, [open])

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
          className="absolute z-30 w-max whitespace-normal break-words rounded bg-slate-800 px-3 py-2 text-left text-xs font-normal leading-snug text-white shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  )
}

// Below and to the right by default; flipped on whichever edges the measured
// box would cross. The placement tests exercise it through the component.
function place(box: HTMLElement | null): void {
  if (!box) return
  Object.assign(box.style, { left: '0px', right: 'auto', top: '100%', bottom: 'auto' })
  box.style.marginTop = `${GAP_PX}px`
  box.style.marginBottom = '0px'
  const rect = box.getBoundingClientRect()
  if (rect.right > window.innerWidth) Object.assign(box.style, { left: 'auto', right: '0px' })
  if (rect.bottom > window.innerHeight) {
    Object.assign(box.style, { top: 'auto', bottom: '100%' })
    box.style.marginTop = '0px'
    box.style.marginBottom = `${GAP_PX}px`
  }
}
