import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AuditEntry, ClaimRecord, RunSummary } from '../api/types'
import { formatDate, formatDateTime } from '../copy/format'
import { tooltips } from '../copy/tooltips'
import {
  ABORTED_SUMMARY,
  abortedRows,
  AWAITING_SUMMARY,
  ceilingRows,
  CLAIM,
  DECIDED_AT,
  decisionRows,
  RUN_SUMMARIES,
  RUNNING_SUMMARY,
  settledRows,
} from '../test/runFixtures'
import { renderWithProviders, stubFetch } from '../test/utils'
import { ClaimDetailPage } from './ClaimDetailPage'

// Where Compare selected took the page.
function LocationEcho() {
  return <div data-testid="location">{useLocation().pathname}</div>
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/claims/:claimId" element={<ClaimDetailPage />} />
      <Route path="/claims/:claimId/compare/:a/:b" element={<LocationEcho />} />
    </Routes>,
    { route: '/claims/c1' },
  )
}

// The runs route must come first: "/api/claims/c1" is a prefix of it.
function stubClaim(claim: ClaimRecord, runs: RunSummary[], rows: AuditEntry[] = []) {
  return stubFetch([
    ['/api/claims/c1/runs', runs],
    ['/api/audit', rows],
    ['/api/claims/c1', claim],
  ])
}

const awaitClaimant = () =>
  waitFor(() => expect(screen.getByText(CLAIM.claimant_name)).toBeInTheDocument())

const runLines = () => screen.getAllByTestId('run-line')

describe('ClaimDetailPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  // Part 1: the record in plain words.
  it('shows the claim in words, with every field the record holds and a way back', async () => {
    stubClaim(CLAIM, RUN_SUMMARIES, settledRows())
    renderPage()
    await awaitClaimant()
    const card = screen.getByText(CLAIM.claimant_name).closest('section') as HTMLElement
    const field = (label: string) =>
      (within(card).getByText(label).nextElementSibling as HTMLElement).textContent
    expect(field('Claim number')).toBe('CLM-2026-9BB57A86')
    expect(within(card).getByText('CLM-2026-9BB57A86')).toHaveClass('font-mono')
    expect(field('Policy number')).toBe('CP-2026-9001')
    expect(field('Claim type')).toBe('Water damage')
    expect(within(card).getByText('Water damage')).not.toHaveClass('font-mono')
    expect(field('Reported amount')).toBe('$85,000')
    expect(field('Jurisdiction')).toBe('United Kingdom')
    expect(field('Loss date')).toBe(formatDate('2026-04-18'))
    expect(field('Reported date')).toBe(formatDate('2026-04-19'))
    expect(field('Submitted')).toBe(formatDateTime(CLAIM.created_at))
    expect(field('Description')).toBe(CLAIM.narrative)
    expect(within(card).getByText('Settled')).toHaveClass('bg-green-100')
    expect(card).not.toHaveTextContent('water_damage')
    expect(card).not.toHaveTextContent('85000.00')
    expect(screen.queryByTestId('claim-status-line')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← Claims list' })).toHaveAttribute('href', '/')
  })

  it('says where the latest run stopped when the pipeline left the claim part-way', async () => {
    stubClaim({ ...CLAIM, status: 'coverage_verified' }, [ABORTED_SUMMARY], abortedRows())
    renderPage()
    await awaitClaimant()
    await waitFor(() =>
      expect(screen.getByTestId('claim-status-line')).toHaveTextContent(
        'The latest run stopped at the Adjuster.',
      ),
    )
    expect(screen.getByText('Coverage checked')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'latest run' })).toHaveAttribute(
      'href',
      `/claims/c1/runs/${ABORTED_SUMMARY.correlation_id}`,
    )
    expect(runLines()).toHaveLength(1)
    expect(runLines()[0]).toHaveTextContent('Aborted at the Adjuster')
    // One run: nothing to compare.
    expect(screen.queryByTestId('compare-hint')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Compare selected' })).not.toBeInTheDocument()
  })

  it('says a run is in progress while the latest has no outcome', async () => {
    stubClaim({ ...CLAIM, status: 'extracted' }, [RUNNING_SUMMARY])
    renderPage()
    await awaitClaimant()
    expect(screen.getByRole('link', { name: 'A run is in progress.' })).toHaveAttribute(
      'href',
      `/claims/c1/runs/${RUNNING_SUMMARY.correlation_id}`,
    )
    expect(runLines()[0]).toHaveTextContent('Running')
  })

  // Part 2: the runs by the time they started.
  it('lists each run by its start time, marks the latest, and says more about it', async () => {
    stubClaim(CLAIM, RUN_SUMMARIES, settledRows())
    renderPage()
    await awaitClaimant()
    await waitFor(() => expect(runLines()[0]).toHaveTextContent('Settled at $82,500'))
    const lines = runLines()
    expect(lines).toHaveLength(3)
    const [latest, second] = lines
    const when = formatDateTime(RUN_SUMMARIES[0].started_at)
    expect(within(latest).getByRole('link', { name: when })).toHaveAttribute(
      'href',
      `/claims/c1/runs/${RUN_SUMMARIES[0].correlation_id}`,
    )
    expect(within(latest).getByText('latest')).toBeInTheDocument()
    expect(latest).toHaveTextContent('Standard run')
    expect(latest).toHaveTextContent('f8d3cc84')
    expect(latest).not.toHaveTextContent('default')
    expect(within(latest).getByRole('link', { name: 'Audit log' })).toHaveAttribute(
      'href',
      `/audit?correlation_id=${RUN_SUMMARIES[0].correlation_id}`,
    )
    expect(within(second).queryByText('latest')).not.toBeInTheDocument()
    expect(second).toHaveTextContent('Settled')
    expect(second).not.toHaveTextContent('Settled at')
    expect(within(latest).getByRole('checkbox')).toHaveAccessibleName(`Select the run of ${when}`)
  })

  it('explains the tick boxes and enables Compare selected on exactly two', async () => {
    const user = userEvent.setup()
    stubClaim(CLAIM, RUN_SUMMARIES, settledRows())
    renderPage()
    await awaitClaimant()
    expect(screen.getByTestId('compare-hint')).toHaveTextContent(
      'Tick two runs to compare them side by side.',
    )
    const compare = screen.getByRole('button', { name: 'Compare selected' })
    expect(compare).toBeDisabled()
    await user.hover(screen.getByRole('button', { name: 'About this action' }))
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      tooltips.disabledCompareNeedsTwo + tooltips.compareSelected,
    )

    const boxes = screen.getAllByRole('checkbox')
    await user.click(boxes[0])
    expect(compare).toBeDisabled()
    await user.click(boxes[2])
    expect(compare).toBeEnabled()
    await user.click(compare)
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(
        `/claims/c1/compare/${RUN_SUMMARIES[0].correlation_id}/${RUN_SUMMARIES[2].correlation_id}`,
      ),
    )
  })

  it('tells a visitor what to do with a claim never run, and fetches no rows', async () => {
    const fetchMock = stubClaim({ ...CLAIM, status: 'received' }, [])
    renderPage()
    await awaitClaimant()
    await waitFor(() => expect(screen.getByTestId('no-runs')).toBeInTheDocument())
    expect(screen.getByTestId('no-runs')).toHaveTextContent(
      'No runs yet. Go back to the Claims list and press Process on this claim.',
    )
    expect(
      within(screen.getByTestId('no-runs')).getByRole('link', { name: 'Claims list' }),
    ).toHaveAttribute('href', '/')
    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls.some((url) => url.includes('/api/audit'))).toBe(false)
  })

  // Part 3: the panel while a person is awaited; the Decision card afterwards.
  it('mounts the review panel for a claim awaiting a person, with no Decision card', async () => {
    stubClaim({ ...CLAIM, status: 'awaiting_human' }, [AWAITING_SUMMARY], ceilingRows())
    renderPage()
    await awaitClaimant()
    await waitFor(() => expect(screen.getByTestId('why-here')).toBeInTheDocument())
    expect(screen.getByText('Human review')).toBeInTheDocument()
    expect(screen.queryByTestId('decision-card')).not.toBeInTheDocument()
    expect(runLines()[0]).toHaveTextContent('Awaiting human review')
  })

  it('shows who rejected the claim, when, and their comment; the badge reads Rejected', async () => {
    stubClaim({ ...CLAIM, status: 'aborted' }, [AWAITING_SUMMARY], decisionRows('rejected'))
    renderPage()
    await awaitClaimant()
    await waitFor(() => expect(screen.getByTestId('decision-card')).toBeInTheDocument())
    const card = screen.getByTestId('decision-card')
    expect(card).toHaveTextContent(`Rejected by Dermot on ${formatDateTime(DECIDED_AT)}.`)
    expect(card).toHaveTextContent('Test rejection')
    expect(within(card).getByRole('link', { name: 'the run' })).toHaveAttribute(
      'href',
      `/claims/c1/runs/${AWAITING_SUMMARY.correlation_id}`,
    )
    expect(screen.getByText('Rejected')).toHaveClass('bg-red-100')
    expect(screen.queryByText('Aborted')).not.toBeInTheDocument()
    expect(screen.queryByText('Human review')).not.toBeInTheDocument()
  })

  it('shows an approval with no comment', async () => {
    stubClaim({ ...CLAIM, status: 'settled' }, [AWAITING_SUMMARY], decisionRows('approved', null))
    renderPage()
    await awaitClaimant()
    await waitFor(() => expect(screen.getByTestId('decision-card')).toBeInTheDocument())
    expect(screen.getByTestId('decision-card')).toHaveTextContent('Approved by Dermot on')
    expect(screen.getByTestId('decision-card')).toHaveTextContent('No comment was left.')
    expect(screen.getByText('Settled')).toHaveClass('bg-green-100')
  })

  it('says when the claim cannot be found', async () => {
    stubFetch([])
    renderPage()
    await waitFor(() => expect(screen.getByText('Claim not found.')).toBeInTheDocument())
  })
})
