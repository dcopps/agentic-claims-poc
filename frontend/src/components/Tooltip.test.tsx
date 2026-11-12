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

  it('names its button as the caller asks, for a tooltip on a line of text', () => {
    render(
      <Tooltip text="Why these did not count." label="About refused objections">
        <span>Refused objections (1):</span>
      </Tooltip>,
    )
    expect(screen.getByRole('button', { name: 'About refused objections' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'About this action' })).not.toBeInTheDocument()
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
  // capped at 320 px, sits above the rows, and never leaves the visible page:
  // it measures itself after opening and flips right or above as needed.
  describe('box', () => {
    afterEach(() => vi.restoreAllMocks())

    function renderAt(rect: { right: number; bottom: number }, viewport = { w: 1280, h: 900 }) {
      vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(viewport.w)
      vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(viewport.h)
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
        left: rect.right - 320,
        right: rect.right,
        top: rect.bottom - 80,
        bottom: rect.bottom,
        width: 320,
        height: 80,
        x: rect.right - 320,
        y: rect.bottom - 80,
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

    it('wraps inside a dark box of at most 320 px, above the rows, below and to the right by default', async () => {
      const user = userEvent.setup()
      renderAt({ right: 600, bottom: 300 })
      await user.hover(screen.getByRole('button', { name: 'About this action' }))
      const tip = screen.getByRole('tooltip')
      expect(tip).toHaveClass('whitespace-normal', 'bg-slate-800', 'text-white', 'z-30')
      expect(tip).toHaveStyle({ maxWidth: '320px', left: '0px', top: '100%' })
    })

    it('aligns to the right of its control when it would pass the right edge', async () => {
      const user = userEvent.setup()
      renderAt({ right: 1300, bottom: 300 }) // 1300 > 1280
      await user.hover(screen.getByRole('button', { name: 'About this action' }))
      const tip = screen.getByRole('tooltip')
      expect(tip).toHaveStyle({ right: '0px', left: 'auto', top: '100%' })
    })

    it('opens above its control when it would pass the bottom edge', async () => {
      const user = userEvent.setup()
      renderAt({ right: 600, bottom: 950 }) // 950 > 900
      await user.hover(screen.getByRole('button', { name: 'About this action' }))
      const tip = screen.getByRole('tooltip')
      expect(tip).toHaveStyle({ bottom: '100%', top: 'auto', left: '0px' })
    })
  })
})
