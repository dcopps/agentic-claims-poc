import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClaimRecord } from '../api/types'
import { formatDateTime } from '../copy/format'
import { guideCopy } from '../copy/guide'
import { tooltips } from '../copy/tooltips'
import { renderWithProviders, stubFetch } from '../test/utils'
import { ClaimsPage } from './ClaimsPage'

// Echoes where the page navigated to and whether it marked the run as started
// here (the run page reads that state, Prompt 29).
function LocationEcho() {
  const location = useLocation()
  const started = (location.state as { started?: boolean } | null)?.started === true
  return (
    <div data-testid="location" data-started={String(started)}>
      {location.pathname}
    </div>
  )
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

  // Prompt 30 addition: the claim number as a second line under the name, in
  // the same cell, so the table gains no column.
  it('shows the claim number under the claimant’s name, small, grey and monospace', async () => {
    renderWithProviders(<ClaimsPage />)
    await waitFor(() => expect(screen.getByText('Acme Logistics Ltd')).toBeInTheDocument())
    const number = screen.getByTestId('claim-number')
    expect(number).toHaveTextContent('CLM-2026-AAAA')
    expect(number).toHaveClass('block', 'font-mono', 'text-xs', 'text-slate-500')
    expect(number.closest('td')).toContainElement(
      screen.getByRole('link', { name: 'Acme Logistics Ltd' }),
    )
    expect(screen.getAllByRole('columnheader')).toHaveLength(6)
  })

  // Prompt 30 (D4): a claim's stored `aborted` is a person's rejection.
  it('labels a rejected claim Rejected, never Aborted', async () => {
    stubFetch([['/api/claims', [{ ...CLAIM, status: 'aborted' }]]])
    renderWithProviders(<ClaimsPage />)
    await waitFor(() => expect(screen.getByText('Acme Logistics Ltd')).toBeInTheDocument())
    const row = screen.getByText('Acme Logistics Ltd').closest('tr') as HTMLElement
    expect(within(row).getByText('Rejected')).toHaveClass('bg-red-100')
    expect(row).not.toHaveTextContent('Aborted')
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
    const row = screen.getByText('Acme Logistics Ltd').closest('tr') as HTMLElement
    expect(within(row).getByText('Water damage').closest('td')).toHaveClass('whitespace-nowrap')
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
    expect(screen.getByTestId('location')).toHaveAttribute('data-started', 'true')
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

// Prompt 29: the shared waking notice, seen here on the first page a visitor
// opens. The fetch is held so the claims query waits past the threshold.
describe('ClaimsPage while the server wakes', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('says the server is waking after three seconds and not before', async () => {
    let release = () => {}
    const held = new Promise<Response>((resolve) => {
      release = () =>
        resolve(
          new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
        )
    })
    ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn(() => held)
    renderWithProviders(<ClaimsPage />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading…')
    act(() => vi.advanceTimersByTime(2500))
    expect(screen.queryByTestId('waking-notice')).not.toBeInTheDocument()
    act(() => vi.advanceTimersByTime(600))
    expect(screen.getByTestId('waking-notice')).toHaveTextContent('Waking the server.')
    release()
    await waitFor(() => expect(screen.getByText(/no claims yet/i)).toBeInTheDocument())
    expect(screen.queryByTestId('waking-notice')).not.toBeInTheDocument()
  })
})
