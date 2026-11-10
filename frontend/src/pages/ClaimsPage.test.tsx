import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClaimRecord } from '../api/types'
import { formatDateTime } from '../copy/format'
import { guideCopy } from '../copy/guide'
import { tooltips } from '../copy/tooltips'
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
  created_at: '2026-11-04T11:08:00Z',
  updated_at: '2026-11-04T11:08:00Z',
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

  // Prompt 26: the data notice is the first line above the form.
  it('shows the synthetic-data notice above the form', () => {
    renderWithProviders(<ClaimsPage />)
    const notice = screen.getByText(guideCopy.dataNotice)
    const form = screen.getByRole('form', { name: 'Submit a claim' })
    expect(notice.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  // Prompt 28: the row shows plain words, a currency amount and the submitted time.
  it('shows the amount as currency, the type and status in plain words, and when it was submitted', async () => {
    renderWithProviders(<ClaimsPage />)
    await waitFor(() => expect(screen.getByText('Acme Logistics Ltd')).toBeInTheDocument())
    const row = screen.getByText('Acme Logistics Ltd').closest('tr') as HTMLElement
    expect(row).toHaveTextContent('$85,000')
    expect(row).toHaveTextContent('Water damage')
    expect(row).toHaveTextContent('Received')
    expect(row).not.toHaveTextContent('water_damage')
    expect(row).toHaveTextContent(formatDateTime('2026-11-04T11:08:00Z'))
    expect(screen.getByRole('columnheader', { name: 'Submitted' })).toBeInTheDocument()
  })

  it('names the second action and says why it is disabled before a finished run', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ClaimsPage />)
    await waitFor(() => expect(screen.getByText('Acme Logistics Ltd')).toBeInTheDocument())
    const rerun = screen.getByRole('button', { name: 'Strict re-run' })
    expect(rerun).toBeDisabled()
    expect(screen.queryByRole('button', { name: /re-process/i })).not.toBeInTheDocument()
    // Both actions sit side by side in one non-wrapping cell, at the small size.
    const cell = screen.getByTestId('claim-actions')
    expect(cell).toHaveClass('whitespace-nowrap')
    expect(cell).toContainElement(screen.getByRole('button', { name: 'Process' }))
    expect(cell).toContainElement(rerun)
    expect(rerun).toHaveClass('text-xs', 'border-blue-700')
    expect(screen.getByRole('button', { name: 'Process' })).toHaveClass('text-xs', 'bg-blue-700')
    expect(screen.getByText('Received')).toHaveClass('whitespace-nowrap')
    expect(screen.getByRole('columnheader', { name: 'Amount' })).toHaveClass('text-right')
    const icons = screen.getAllByRole('button', { name: 'About this action' })
    await user.hover(icons[icons.length - 1])
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      tooltips.disabledNoFinishedRun + tooltips.strictRerun,
    )
  })

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
      expect(screen.getByTestId('location').textContent).toMatch(/^\/claims\/claim-1\/runs\//),
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
