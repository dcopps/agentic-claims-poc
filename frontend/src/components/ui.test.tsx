import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Button, StatusBadge } from './ui'

describe('StatusBadge', () => {
  it('colours settled green', () => {
    render(<StatusBadge status="settled" />)
    expect(screen.getByText('settled')).toHaveClass('bg-green-100')
  })

  it('colours awaiting_human amber', () => {
    render(<StatusBadge status="awaiting_human" />)
    expect(screen.getByText('awaiting_human')).toHaveClass('bg-amber-100')
  })

  it('colours aborted red', () => {
    render(<StatusBadge status="aborted" />)
    expect(screen.getByText('aborted')).toHaveClass('bg-red-100')
  })

  it('shows a plain-words label when given one and keeps the status colour', () => {
    render(<StatusBadge status="awaiting_human" label="Awaiting human review" />)
    const badge = screen.getByText('Awaiting human review')
    expect(badge).toHaveClass('bg-amber-100')
    expect(badge).not.toHaveClass('font-mono')
    expect(screen.queryByText('awaiting_human')).not.toBeInTheDocument()
  })

  it('falls back to neutral for an unknown status', () => {
    render(<StatusBadge status="mystery" />)
    expect(screen.getByText('mystery')).toHaveClass('bg-slate-100')
  })
})

// Prompt 28: primary is solid blue (the link colour), secondary a blue outline on
// white, disabled greyed; `sm` is the table-row size.
describe('Button', () => {
  it('styles primary as solid blue and secondary as a blue outline', () => {
    render(
      <>
        <Button>Go</Button>
        <Button variant="secondary">Maybe</Button>
      </>,
    )
    expect(screen.getByRole('button', { name: 'Go' })).toHaveClass('bg-blue-700', 'text-white')
    const secondary = screen.getByRole('button', { name: 'Maybe' })
    expect(secondary).toHaveClass('border-blue-700', 'bg-white', 'text-blue-700')
  })

  it('offers a small size and keeps the greyed disabled look', () => {
    render(
      <Button size="sm" disabled>
        Later
      </Button>,
    )
    const button = screen.getByRole('button', { name: 'Later' })
    expect(button).toHaveClass('text-xs', 'disabled:opacity-50', 'whitespace-nowrap')
    expect(button).toBeDisabled()
  })
})
