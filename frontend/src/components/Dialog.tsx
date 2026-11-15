import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from 'react'
import { auditCopy } from '../copy/audit'

// What Tab moves between inside the dialog.
const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

interface DialogProps {
  title: string
  onClose: () => void
  children: ReactNode
}

// A modal dialog that behaves (Prompt 32): focus lands on Close when it opens
// and returns to whatever had it when it closes; Tab and Shift+Tab cycle inside
// it and never leave; Escape, the Close button and a click on the backdrop
// close it; the page behind cannot scroll while it is open; the panel fits a
// laptop screen and scrolls inside itself. Hand-rolled rather than the
// browser's <dialog> with showModal(), which would give the trap for nothing,
// because jsdom cannot drive showModal() and none of this could then be tested
// (plan D2). Built for the record viewer; nothing in it is the Audit page's.
export function Dialog({ title, onClose, children }: DialogProps) {
  const panel = useRef<HTMLDivElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  useModalLifetime(closeButton)

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) =>
    handleKey(event, panel.current, onClose)
  // A mousedown on the backdrop itself, not on anything in the panel.
  const onBackdrop = (event: MouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) onClose()
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4"
      data-testid="dialog-backdrop"
      onMouseDown={onBackdrop}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
        className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded border border-slate-200 bg-white shadow-lg"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 id={titleId} className="text-sm font-medium text-slate-700">
            {title}
          </h2>
          <button
            ref={closeButton}
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-50"
          >
            {auditCopy.close}
          </button>
        </div>
        <div className="overflow-x-hidden overflow-y-auto px-4 py-3">{children}</div>
      </div>
    </div>
  )
}

// On open: remember the opener, lock the page's scroll, move focus to Close.
// On close: put both back. The effect has no dependencies by design — it is
// the dialog's whole lifetime.
function useModalLifetime(closeButton: RefObject<HTMLButtonElement | null>): void {
  useEffect(() => {
    const opener = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeButton.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      if (opener instanceof HTMLElement) opener.focus()
    }
  }, [closeButton])
}

// Escape closes; Tab stays inside; every other key is the content's.
function handleKey(
  event: KeyboardEvent<HTMLDivElement>,
  panel: HTMLDivElement | null,
  onClose: () => void,
): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    onClose()
  } else if (event.key === 'Tab') {
    trapTab(event, panel)
  }
}

// Keep Tab inside the panel: from its last focusable element Tab goes to the
// first, and from the first Shift+Tab goes to the last. Focus that has
// somehow left the panel is brought back the same way.
function trapTab(event: KeyboardEvent<HTMLDivElement>, panel: HTMLDivElement | null): void {
  if (!panel) return
  const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => !element.hasAttribute('disabled'),
  )
  if (focusable.length === 0) {
    event.preventDefault()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement
  const outside = !(active instanceof Node) || !panel.contains(active)
  if (event.shiftKey && (active === first || outside)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || outside)) {
    event.preventDefault()
    first.focus()
  }
}
