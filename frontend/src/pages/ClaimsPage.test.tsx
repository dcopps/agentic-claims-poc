import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClaimRecord } from '../api/types'
import { renderWithProviders, stubFetch } from '../test/utils'
import { ClaimsPage } from './ClaimsPage'

function LocationEcho() {
  return <div data-testid="location">{useLocation().pathname}</div>
}

const CLAIM: ClaimRecord = {
  claim_id: 'claim-1',
  claim_number: 'CLM-2026-AAAA',
  line_of_business: 'Commercial Property',
  claimant_name: 'Acme Logistics Ltd',
  policy_number: 'POL-1',
  loss_date: '2026-04-01',
  reported_date: '2026-04-03',
  jurisdiction: 'United Kingdom',
  narrative: 'Loss.',
  claim_type: 'water_damage',
  reported_amount: '85000.00',
  status: 'received',
  scenario_tag: null,
  created_at: 't',
  updated_at: 't',
}

describe('ClaimsPage', () => {
  let fetchMock: ReturnType<typeof stubFetch>
  beforeEach(() => {
    fetchMock = stubFetch([
      ['/api/pipeline/run/', { status: 'settled' }],
      ['/api/claims', [CLAIM]],
    ])
  })
  afterEach(() => vi.unstubAllGlobals())

  it('navigates to the run page immediately on Process', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <>
        <ClaimsPage />
        <LocationEcho />
      </>,
    )
    await waitFor(() => expect(screen.getByText('Acme Logistics Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Process' }))
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toMatch(
        /^\/claims\/claim-1\/runs\//,
      ),
    )
  })

  it('fires the run POST in the background', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ClaimsPage />)
    await waitFor(() => expect(screen.getByText('Acme Logistics Ltd')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Process' }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/pipeline/run/claim-1'),
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })
})
