import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Tooltip } from './Tooltip'

// Prompt 28: the tooltip must reach keyboard users as well as the mouse. It is
// a real `role="tooltip"` element, shown on hover and on focus, and the wrapped
// control is described by it.
describe('Tooltip', () => {
  const TEXT = 'Runs the four agents on this claim now.'

  it('is absent at rest', () => {
    render(
      <Tooltip text={TEXT}>
        <button type="button">Process</button>
      </Tooltip>,
    )
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('appears on hover and names the wrapped control as described by it', async () => {
    const user = userEvent.setup()
    render(
      <Tooltip text={TEXT}>
        <button type="button">Process</button>
      </Tooltip>,
    )
    await user.hover(screen.getByRole('button', { name: 'About this action' }))
    const tip = screen.getByRole('tooltip')
    expect(tip).toHaveTextContent(TEXT)
    expect(screen.getByRole('button', { name: 'Process' })).toHaveAttribute(
      'aria-describedby',
      tip.id,
    )
    await user.unhover(screen.getByRole('button', { name: 'About this action' }))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('appears on keyboard focus and goes when focus leaves', async () => {
    const user = userEvent.setup()
    render(
      <>
        <Tooltip text={TEXT}>
          <button type="button">Process</button>
        </Tooltip>
        <button type="button">Elsewhere</button>
      </>,
    )
    await user.tab() // the wrapped control
    expect(screen.getByRole('tooltip')).toHaveTextContent(TEXT)
    await user.tab() // the ⓘ button, still inside the group
    expect(screen.getByRole('button', { name: 'About this action' })).toHaveFocus()
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    await user.tab() // out of the group
    expect(screen.getByRole('button', { name: 'Elsewhere' })).toHaveFocus()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  // The box wraps its own text (a caller may sit in a nowrap table cell), is
  // capped at 320 px, sits above the rows, and never leaves the visible page.
  describe('box', () => {
    afterEach(() => vi.restoreAllMocks())

    function renderAt(left: number, innerWidth: number) {
      vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(innerWidth)
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
        left,
        right: left + 120,
        top: 0,
        bottom: 20,
        width: 120,
        height: 20,
        x: left,
        y: 0,
        toJSON: () => ({}),
      })
      render(
        <td className="whitespace-nowrap">
          <Tooltip text={TEXT}>
            <button type="button">Process</button>
          </Tooltip>
        </td>,
      )
    }

    it('wraps inside a dark box of at most 320 px, above the rows', async () => {
      const user = userEvent.setup()
      renderAt(100, 1280)
      await user.hover(screen.getByRole('button', { name: 'About this action' }))
      const tip = screen.getByRole('tooltip')
      expect(tip).toHaveClass('whitespace-normal', 'bg-slate-800', 'text-white', 'z-30', 'left-0')
      expect(tip).toHaveStyle({ maxWidth: '320px' })
    })

    it('aligns to the right of its control when it would leave the viewport', async () => {
      const user = userEvent.setup()
      renderAt(1100, 1280) // 1100 + 320 > 1280
      await user.hover(screen.getByRole('button', { name: 'About this action' }))
      expect(screen.getByRole('tooltip')).toHaveClass('right-0')
      expect(screen.getByRole('tooltip')).not.toHaveClass('left-0')
    })
  })
})
