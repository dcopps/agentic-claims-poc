import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClaimRecord } from '../api/types'
import { formatDateTime } from '../copy/format'
import { guideCopy } from '../copy/guide'
import { claimsCopy } from '../copy/claims'
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
  human_decision: null,
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

// Prompt 31: when a claim may be run again.
describe('ClaimsPage: when a claim may be run again', () => {
  const SETTLED: ClaimRecord = {
    ...CLAIM,
    claim_id: 'settled-1',
    claimant_name: 'Harborline Logistics Ltd',
    status: 'settled',
  }
  const SETTLED_TOO: ClaimRecord = {
    ...CLAIM,
    claim_id: 'settled-2',
    claimant_name: 'Northwood Manufacturing Inc',
    status: 'settled',
  }
  const AWAITING: ClaimRecord = {
    ...CLAIM,
    claim_id: 'awaiting-1',
    claimant_name: 'Coral Bay Holdings',
    status: 'awaiting_human',
  }

  function stubClaims(claims: ClaimRecord[]) {
    return stubFetch([
      ['/api/pipeline/run/', { status: 'settled' }],
      ['/api/claims', claims],
    ])
  }
  const rowOf = (claimant: string) => screen.getByText(claimant).closest('tr') as HTMLElement
  const awaitRows = () => screen.findByRole('table', { name: 'Claims' })
  const postedRuns = (fetchMock: ReturnType<typeof stubFetch>) =>
    fetchMock.mock.calls.filter((call) => String(call[0]).includes('/api/pipeline/run/')).length

  afterEach(() => vi.unstubAllGlobals())

  it('reads Process for a claim never run and Run again once it has had one', async () => {
    stubClaims([CLAIM, SETTLED, AWAITING])
    renderWithProviders(<ClaimsPage />)
    await awaitRows()
    expect(
      within(rowOf(CLAIM.claimant_name)).getByRole('button', { name: 'Process' }),
    ).toBeEnabled()
    expect(
      within(rowOf(SETTLED.claimant_name)).getAllByRole('button', { name: 'Run again' }),
    ).toHaveLength(1)
    expect(
      within(rowOf(AWAITING.claimant_name)).getByRole('button', { name: 'Run again' }),
    ).toBeEnabled()
    expect(screen.getAllByRole('button', { name: 'Process' })).toHaveLength(1)
  })

  it('asks once before a settled claim is run again, and Cancel runs nothing', async () => {
    const user = userEvent.setup()
    const fetchMock = stubClaims([SETTLED])
    renderWithProviders(<ClaimsPage />)
    await awaitRows()
    await user.click(screen.getByRole('button', { name: 'Run again' }))
    const panel = screen.getByTestId('confirm-rerun')
    expect(panel).toHaveTextContent(claimsCopy.confirmRerun)
    expect(panel).toHaveClass('absolute')
    expect(screen.getByTestId('claim-actions')).toContainElement(panel)
    expect(screen.getAllByRole('columnheader')).toHaveLength(6)
    await user.click(within(panel).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByTestId('confirm-rerun')).not.toBeInTheDocument()
    expect(postedRuns(fetchMock)).toBe(0)
  })

  it('runs the settled claim once the question is answered Run again', async () => {
    const user = userEvent.setup()
    const fetchMock = stubClaims([SETTLED])
    renderWithProviders(
      <>
        <ClaimsPage />
        <LocationEcho />
      </>,
    )
    await awaitRows()
    await user.click(screen.getByRole('button', { name: 'Run again' }))
    await user.click(
      within(screen.getByTestId('confirm-rerun')).getByRole('button', { name: 'Run again' }),
    )
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toMatch(/^\/claims\/settled-1\/runs\//),
    )
    await waitFor(() => expect(postedRuns(fetchMock)).toBe(1))
    expect(
      String(fetchMock.mock.calls.find((c) => String(c[0]).includes('/api/pipeline/run/'))![0]),
    ).toContain('/api/pipeline/run/settled-1')
  })

  it('closes the question on Escape, on a click outside, and when another row opens its own', async () => {
    const user = userEvent.setup()
    stubClaims([SETTLED, SETTLED_TOO])
    renderWithProviders(<ClaimsPage />)
    await awaitRows()
    const first = within(rowOf(SETTLED.claimant_name)).getByRole('button', { name: 'Run again' })
    const second = within(rowOf(SETTLED_TOO.claimant_name)).getByRole('button', {
      name: 'Run again',
    })

    await user.click(first)
    expect(screen.getByTestId('confirm-rerun')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByTestId('confirm-rerun')).not.toBeInTheDocument()

    await user.click(first)
    expect(screen.getByTestId('confirm-rerun')).toBeInTheDocument()
    await user.click(screen.getByRole('columnheader', { name: 'Claimant' }))
    expect(screen.queryByTestId('confirm-rerun')).not.toBeInTheDocument()

    await user.click(first)
    await user.click(second)
    const panels = screen.getAllByTestId('confirm-rerun')
    expect(panels).toHaveLength(1)
    expect(rowOf(SETTLED_TOO.claimant_name)).toContainElement(panels[0])
  })

  it('does not ask before running a claim that is awaiting a person again', async () => {
    const user = userEvent.setup()
    const fetchMock = stubClaims([AWAITING])
    renderWithProviders(<ClaimsPage />)
    await awaitRows()
    await user.click(screen.getByRole('button', { name: 'Run again' }))
    expect(screen.queryByTestId('confirm-rerun')).not.toBeInTheDocument()
    await waitFor(() => expect(postedRuns(fetchMock)).toBe(1))
  })

  it('disables both actions for a claim a person decided, saying why', async () => {
    const user = userEvent.setup()
    stubClaims([
      { ...SETTLED, human_decision: 'approved' },
      { ...AWAITING, status: 'aborted', human_decision: 'rejected' },
    ])
    renderWithProviders(<ClaimsPage />)
    await awaitRows()
    const approvedRow = rowOf(SETTLED.claimant_name)
    const rejectedRow = rowOf(AWAITING.claimant_name)
    for (const row of [approvedRow, rejectedRow]) {
      expect(within(row).getByRole('button', { name: 'Run again' })).toBeDisabled()
      expect(within(row).getByRole('button', { name: 'Strict re-run' })).toBeDisabled()
    }
    const [approvedInfo] = within(approvedRow).getAllByRole('button', { name: 'About this action' })
    await user.hover(approvedInfo)
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      tooltips.disabledClosedApproved + tooltips.processClaim,
    )
    await user.unhover(approvedInfo)
    const rejectedInfos = within(rejectedRow).getAllByRole('button', { name: 'About this action' })
    await user.hover(rejectedInfos[1])
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      tooltips.disabledClosedRejected + tooltips.strictRerun,
    )
  })
})
