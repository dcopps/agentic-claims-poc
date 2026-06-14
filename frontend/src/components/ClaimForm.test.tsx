import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ClaimForm } from './ClaimForm'

describe('ClaimForm', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 201,
            headers: { 'Content-Type': 'application/json' },
          }),
        ),
      ),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders the submit button', () => {
    render(<ClaimForm onSubmitted={() => {}} />)
    expect(
      screen.getByRole('button', { name: /submit claim/i }),
    ).toBeInTheDocument()
  })

  it('prefills from a demo claim', async () => {
    const user = userEvent.setup()
    render(<ClaimForm onSubmitted={() => {}} />)
    await user.click(screen.getByRole('button', { name: /auto-approve/i }))
    expect(screen.getByLabelText('Claimant name')).toHaveValue(
      'Harborline Logistics Ltd',
    )
  })

  it('posts to /api/claims on submit', async () => {
    const user = userEvent.setup()
    const onSubmitted = vi.fn()
    render(<ClaimForm onSubmitted={onSubmitted} />)
    await user.click(screen.getByRole('button', { name: /auto-approve/i }))
    await user.click(screen.getByRole('button', { name: /submit claim/i }))
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/claims'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(onSubmitted).toHaveBeenCalled()
  })
})
