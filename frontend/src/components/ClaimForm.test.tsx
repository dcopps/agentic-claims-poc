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
    expect(screen.getByRole('button', { name: /submit claim/i })).toBeInTheDocument()
  })

  it('prefills from a demo claim', async () => {
    const user = userEvent.setup()
    render(<ClaimForm onSubmitted={() => {}} />)
    await user.click(screen.getByRole('button', { name: /auto-approve/i }))
    expect(screen.getByLabelText('Claimant name')).toHaveValue('Harborline Logistics Ltd')
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

  // Prompt 28: every field has a visible <label> tied to its input.
  it('labels every field visibly, with the label still present once filled', async () => {
    const user = userEvent.setup()
    render(<ClaimForm onSubmitted={() => {}} />)
    for (const name of [
      'Claimant name',
      'Policy number',
      'Loss date',
      'Reported date',
      'Jurisdiction',
      'Reported amount (USD)',
      'Claim type',
      'Description',
    ]) {
      const control = screen.getByLabelText(name)
      const label = document.querySelector(`label[for="${control.id}"]`)
      expect(label, name).not.toBeNull()
      expect(label).toHaveTextContent(name)
    }
    await user.click(screen.getByRole('button', { name: /guardrail escalation/i }))
    expect(screen.getByLabelText('Loss date')).toHaveValue('2026-02-28')
    expect(document.querySelectorAll('label')).toHaveLength(8)
  })

  it('shows claim types as labels but submits the stored values, not the labels', async () => {
    const user = userEvent.setup()
    render(<ClaimForm onSubmitted={() => {}} />)
    const select = screen.getByLabelText('Claim type') as HTMLSelectElement
    const options = Array.from(select.options).map((o) => [o.value, o.textContent])
    expect(options).toContainEqual(['storm_complex', 'Storm (complex)'])
    expect(options).toContainEqual(['water_damage', 'Water damage'])

    await user.click(screen.getByRole('button', { name: /guardrail escalation/i }))
    expect(select.value).toBe('storm_complex')
    await user.click(screen.getByRole('button', { name: /submit claim/i }))
    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ]
    const body = JSON.parse(String(init.body)) as Record<string, string>
    expect(body.claim_type).toBe('storm_complex')
    expect(body.reported_amount).toBe('1400000.00')
    expect(Object.values(body)).not.toContain('Storm (complex)')
  })
})
