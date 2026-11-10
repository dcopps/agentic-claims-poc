import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
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
})
