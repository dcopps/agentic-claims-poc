import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Dialog } from './Dialog'

function renderDialog(onClose = vi.fn()) {
  render(
    <Dialog title="Record 210" onClose={onClose}>
      <button type="button">First</button>
      <input aria-label="Last" />
    </Dialog>,
  )
  return onClose
}

// Opens the dialog from a button, so focus has somewhere to return to.
function Opener() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      {open && (
        <Dialog title="T" onClose={() => setOpen(false)}>
          <p>body</p>
        </Dialog>
      )}
    </>
  )
}

// Prompt 32: a dialog that behaves (plan §3, D2).
describe('Dialog', () => {
  it('is a labelled modal dialog with focus on Close', () => {
    renderDialog()
    const dialog = screen.getByRole('dialog', { name: 'Record 210' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()
  })

  it('keeps Tab inside: the last element wraps to Close, and Shift+Tab from Close goes to the last', () => {
    renderDialog()
    const close = screen.getByRole('button', { name: 'Close' })
    const last = screen.getByLabelText('Last')
    last.focus()
    fireEvent.keyDown(last, { key: 'Tab' })
    expect(close).toHaveFocus()
    fireEvent.keyDown(close, { key: 'Tab', shiftKey: true })
    expect(last).toHaveFocus()
    // Tab from the middle is left to the browser.
    const first = screen.getByRole('button', { name: 'First' })
    first.focus()
    fireEvent.keyDown(first, { key: 'Tab' })
    expect(first).toHaveFocus()
  })

  it('closes on Escape, on Close, and on a click on the backdrop, but not on a click inside', () => {
    const onClose = renderDialog()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(2)
    fireEvent.mouseDown(screen.getByTestId('dialog-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(3)
    fireEvent.mouseDown(screen.getByRole('button', { name: 'First' }))
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  it('locks the page’s scroll while open and returns focus to the opener on closing', async () => {
    const user = userEvent.setup()
    render(<Opener />)
    const opener = screen.getByRole('button', { name: 'Open' })
    await user.click(opener)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(document.body.style.overflow).toBe('hidden')
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.body.style.overflow).toBe('')
    expect(opener).toHaveFocus()
  })
})
