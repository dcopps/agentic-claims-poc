import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ClaimRecord, ClaimStatus } from '../api/types'
import { ClaimList } from './ClaimList'

function claim(overrides: Partial<ClaimRecord> = {}): ClaimRecord {
  return {
    claim_id: 'claim-1',
    claim_number: 'CLM-2026-AAAA',
    line_of_business: 'Commercial Property',
    claimant_name: 'Acme Logistics Ltd',
    policy_number: 'POL-1',
    loss_date: '2026-04-01',
    reported_date: '2026-04-03',
    jurisdiction: 'United Kingdom',
    narrative: 'Loss.',
    claim_type: 'fire',
    reported_amount: '850000.00',
    status: 'received' as ClaimStatus,
    scenario_tag: null,
    created_at: '2026-04-03T00:00:00Z',
    updated_at: '2026-04-03T00:00:00Z',
    ...overrides,
  }
}

describe('ClaimList', () => {
  it('renders a claim row with its status', () => {
    render(
      <ClaimList claims={[claim()]} busyClaimId={null} onProcess={vi.fn()} onReplay={vi.fn()} />,
    )
    expect(screen.getByText('Acme Logistics Ltd')).toBeInTheDocument()
    expect(screen.getByText('received')).toBeInTheDocument()
  })

  it('disables Re-process until the claim is terminal', () => {
    render(
      <ClaimList
        claims={[claim({ status: 'received' })]}
        busyClaimId={null}
        onProcess={vi.fn()}
        onReplay={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /re-process with v2/i })).toBeDisabled()
  })

  it('enables Re-process for a settled claim', () => {
    render(
      <ClaimList
        claims={[claim({ status: 'settled' })]}
        busyClaimId={null}
        onProcess={vi.fn()}
        onReplay={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /re-process with v2/i })).toBeEnabled()
  })

  it('calls onProcess when Process is clicked', async () => {
    const onProcess = vi.fn()
    const user = userEvent.setup()
    render(
      <ClaimList claims={[claim()]} busyClaimId={null} onProcess={onProcess} onReplay={vi.fn()} />,
    )
    await user.click(screen.getByRole('button', { name: 'Process' }))
    expect(onProcess).toHaveBeenCalledWith('claim-1')
  })
})
