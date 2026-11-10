import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from './ui'

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
