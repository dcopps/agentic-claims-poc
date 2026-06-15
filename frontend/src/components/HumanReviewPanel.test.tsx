import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunSummary } from '../api/types'
import { renderWithProviders, stubFetch } from '../test/utils'
import { HumanReviewPanel } from './HumanReviewPanel'

const RUNS: RunSummary[] = [
  {
    correlation_id: 'cid-1',
    variant: 'default',
    status: 'awaiting_human',
    started_at: 't',
    completed_at: 't',
    escalate: true,
  },
]

const AUDIT = [
  {
    audit_id: 1,
    agent: 'adjuster',
    step: 'settlement_estimate',
    created_at: '2026-04-03T00:00:00Z',
    payload: { output: { recommended_settlement: '850000.00', reasoning: 'High value loss.' } },
    chain_hash: 'x',
  },
]

describe('HumanReviewPanel', () => {
  let fetchMock: ReturnType<typeof stubFetch>
  beforeEach(() => {
    fetchMock = stubFetch([
      ['human-decision', { status: 'settled' }],
      ['/api/audit', AUDIT],
    ])
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows the adjuster evidence from the audit payload', async () => {
    renderWithProviders(<HumanReviewPanel claimId="c1" runs={RUNS} />)
    await waitFor(() => expect(screen.getByText('850000.00')).toBeInTheDocument())
    expect(screen.getByText(/high value loss/i)).toBeInTheDocument()
  })

  it('disables approve until a reviewer name is entered', () => {
    renderWithProviders(<HumanReviewPanel claimId="c1" runs={RUNS} />)
    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled()
  })

  it('submits an approval decision', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HumanReviewPanel claimId="c1" runs={RUNS} />)
    await user.type(screen.getByLabelText('Decided by'), 'A. Reviewer')
    await user.click(screen.getByRole('button', { name: /approve/i }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('human-decision'),
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })
})
