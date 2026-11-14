import { QueryClient } from '@tanstack/react-query'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { PipelineEvent } from '../api/types'
import { formatDateTime } from '../copy/format'
import {
  ABORT_MESSAGE,
  abortedRows,
  CLAIM,
  DECIDED_AT,
  decisionRows,
  guardrailFailureRows,
  settledRows,
} from '../test/runFixtures'
import { renderWithProviders, stubFetch } from '../test/utils'

// useRunStream uses an EventSource (a no-op stub in tests), so mock it to return
// a controllable event list per test.
const { streamState } = vi.hoisted(() => ({
  streamState: { events: [] as PipelineEvent[] },
}))
vi.mock('../hooks/useRunStream', () => ({
  useRunStream: () => streamState.events,
}))

const ROUTE = '/claims/c1/runs/cid-1'
// The Claims page's trigger navigates with `started` (Prompt 29).
const STARTED_HERE = { pathname: ROUTE, state: { started: true } }

// A fetch that answers nothing until `release` is called, then 404s every held
// call: the backend waking from zero replicas, as the run page sees it.
function holdFetch(): () => void {
  let release = () => {}
  const held = new Promise<Response>((resolve) => {
    release = () => resolve(new Response('{"detail":"not found"}', { status: 404 }))
  })
  ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn(() => held)
  return release
}

describe('RunDetailPage', () => {
  beforeEach(() => {
    streamState.events = []
    stubFetch([]) // runs + audit endpoints 404 (in-flight): expected, not an error
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders waiting cards and an awaiting hint for a run started here with no data yet', async () => {
    renderWithProviders(<App />, { route: STARTED_HERE })
    await waitFor(() => expect(screen.getByTestId('awaiting-hint')).toBeInTheDocument())
    expect(screen.getByTestId('awaiting-hint')).toHaveTextContent('Waiting for the run to begin…')
    expect(screen.getByText('Doc-Parser')).toBeInTheDocument()
    expect(screen.getAllByText('Waiting')).toHaveLength(4)
    expect(screen.queryByTestId('run-not-found')).not.toBeInTheDocument()
  })

  it('says "Loading this run…" in place of the cards until the queries answer', async () => {
    const release = holdFetch()
    renderWithProviders(<App />, { route: STARTED_HERE })
    expect(screen.getByTestId('run-loading')).toHaveTextContent('Loading this run…')
    expect(screen.queryByText('Waiting')).not.toBeInTheDocument()
    expect(screen.queryByTestId('awaiting-hint')).not.toBeInTheDocument()
    expect(screen.queryByTestId('run-not-found')).not.toBeInTheDocument()
    release()
    await waitFor(() => expect(screen.getByTestId('awaiting-hint')).toBeInTheDocument())
    expect(screen.getAllByText('Waiting')).toHaveLength(4)
    expect(screen.queryByTestId('run-loading')).not.toBeInTheDocument()
  })

  it('does not say "Run not found" while the queries are still in flight', async () => {
    const release = holdFetch()
    renderWithProviders(<App />, { route: ROUTE })
    expect(screen.getByTestId('run-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('run-not-found')).not.toBeInTheDocument()
    release()
    await waitFor(() => expect(screen.getByTestId('run-not-found')).toBeInTheDocument())
    expect(screen.queryByTestId('run-loading')).not.toBeInTheDocument()
  })

  it('names the claim from the address for a run started here with nothing recorded yet', async () => {
    stubFetch([['/api/claims/c1', CLAIM]])
    renderWithProviders(<App />, { route: STARTED_HERE })
    const link = await screen.findByRole('link', { name: 'Harborline Logistics Ltd' })
    expect(link).toHaveAttribute('href', '/claims/c1')
  })

  it('says "Run not found" for an id opened from elsewhere that nothing has recorded', async () => {
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() =>
      expect(screen.getByTestId('run-not-found')).toHaveTextContent('Run not found.'),
    )
    expect(screen.queryByTestId('awaiting-hint')).not.toBeInTheDocument()
  })

  it('renders an error banner when a pipeline_aborted event arrives', () => {
    streamState.events = [
      {
        event_type: 'pipeline_aborted',
        correlation_id: 'cid-1',
        timestamp: 't',
        failing_agent: 'doc_parser',
        error_type: 'ValueError',
        message: 'claim not found',
      },
    ]
    renderWithProviders(<App />, { route: ROUTE })
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Run aborted: the Doc-Parser raised ValueError',
    )
  })

  it('renders an error banner when a run-error was recorded for this correlation id', () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    client.setQueryData(['runError', 'cid-1'], '502 Bad Gateway')
    renderWithProviders(<App />, { route: ROUTE, client })
    expect(screen.getByRole('alert')).toHaveTextContent(/could not start the run: 502/i)
  })
})

// Fix C — the run header exposes the full correlation id for copy/share and a
// one-click jump to the audit view of the same run.
describe('RunDetailPage header (correlation id)', () => {
  const FULL_CID = '0fa06cb9-1234-5678-9abc-def012345678'
  const FULL_ROUTE = `/claims/c1/runs/${FULL_CID}`

  beforeEach(() => {
    streamState.events = []
    stubFetch([])
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders the full correlation id, not a truncated prefix', () => {
    renderWithProviders(<App />, { route: FULL_ROUTE })
    expect(screen.getByText(FULL_CID)).toBeInTheDocument()
  })

  it('copies the full correlation id to the clipboard', () => {
    // fireEvent (not userEvent) so userEvent's own clipboard stub does not
    // shadow this spy — the component reads navigator.clipboard at click time.
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    renderWithProviders(<App />, { route: FULL_ROUTE })
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    expect(writeText).toHaveBeenCalledWith(FULL_CID)
  })

  it('copies a ready-made question for an MCP client naming the run', () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })
    renderWithProviders(<App />, { route: FULL_ROUTE })
    fireEvent.click(screen.getByRole('button', { name: 'Copy question for Claude' }))
    expect(writeText).toHaveBeenCalledWith(
      `Using the claims MCP server, explain run ${FULL_CID} and tell me whether its audit chain verifies.`,
    )
  })

  it('links to the audit view of this run with the correlation id pre-filled', () => {
    renderWithProviders(<App />, { route: FULL_ROUTE })
    const link = screen.getByRole('link', { name: /view audit log/i })
    expect(link).toHaveAttribute('href', `/audit?correlation_id=${FULL_CID}`)
  })
})

// Prompt 29: the audit rows are the source of each card's state, so a run reads
// the same while it happens and when it is opened afterwards.
describe('RunDetailPage after the event (audit rows, no live events)', () => {
  const RUN = { status: 'settled', escalation_decision: null }

  beforeEach(() => {
    streamState.events = []
  })
  afterEach(() => vi.unstubAllGlobals())

  function cardText(label: string) {
    return screen.getByText(label).closest('button')!
  }

  it('renders a settled run: four sentences, durations, the header, no awaiting hint', async () => {
    stubFetch([
      ['/api/runs/', RUN],
      ['/api/audit', settledRows()],
    ])
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() =>
      expect(cardText('Doc-Parser')).toHaveTextContent('Summarised the claim (Water damage)'),
    )
    expect(cardText('Doc-Parser')).toHaveTextContent('1.3 s')
    expect(cardText('Validator')).toHaveTextContent('Covered (92% confident)')
    expect(cardText('Adjuster')).toHaveTextContent('Recommends $82,500 (85% confident)')
    expect(cardText('Guardrail')).toHaveTextContent('Passed')
    expect(screen.getByTestId('run-variant')).toHaveTextContent('Standard run')
    // The sentence is enough: the stored name is not shown (Dermot, 12 November 2026).
    expect(screen.getByTestId('run-variant').parentElement).not.toHaveTextContent('default')
    expect(screen.getByText('Settled')).toBeInTheDocument()
    expect(screen.queryByTestId('awaiting-hint')).not.toBeInTheDocument()
    expect(screen.queryByTestId('run-not-found')).not.toBeInTheDocument()
    expect(screen.queryByTestId('fired-rules')).not.toBeInTheDocument()
    expect(screen.queryByTestId('run-loading')).not.toBeInTheDocument()
  })

  it('names the claim from the audit rows, not the address, linking back to the claim page', async () => {
    const fetchMock = stubFetch([
      ['/api/runs/', RUN],
      ['/api/audit', settledRows()],
      ['/api/claims/c1', CLAIM],
    ])
    renderWithProviders(<App />, { route: '/claims/c-address/runs/cid-1' })
    const link = await screen.findByRole('link', { name: 'Harborline Logistics Ltd' })
    expect(link).toHaveAttribute('href', '/claims/c1')
    expect(screen.getByTestId('run-claim')).toHaveTextContent(
      'Harborline Logistics Ltd · Water damage · $85,000 · claim CLM-2026-9BB57A86',
    )
    const requested = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(requested.some((url) => url.includes('/api/claims/c-address'))).toBe(false)
  })

  it('says so when the claim the rows name cannot be loaded', async () => {
    stubFetch([
      ['/api/runs/', RUN],
      ['/api/audit', settledRows()],
    ])
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() =>
      expect(screen.getByTestId('run-claim')).toHaveTextContent(
        'The claim this run belongs to could not be loaded.',
      ),
    )
  })

  it('renders an aborted run: the failed agent with its reason and message, the later agent not run', async () => {
    stubFetch([
      ['/api/runs/', { status: 'aborted', escalation_decision: null, aborted_agent: 'adjuster' }],
      ['/api/audit', abortedRows()],
    ])
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() =>
      expect(cardText('Adjuster')).toHaveTextContent(
        'Failed: the Adjuster has no market range for the claim type Smoke damage',
      ),
    )
    expect(screen.getByTestId('card-detail')).toHaveTextContent(ABORT_MESSAGE)
    expect(cardText('Guardrail')).toHaveTextContent('Not run: the run stopped at the Adjuster')
    expect(cardText('Validator')).toHaveTextContent('Covered (88% confident)')
    expect(screen.getByText('Aborted')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Run aborted: the Adjuster has no market range',
    )
  })

  it('renders the Guardrail failure as awaiting human review with two rule lines', async () => {
    stubFetch([
      ['/api/runs/', { status: 'awaiting_human', escalation_decision: null }],
      ['/api/audit', guardrailFailureRows()],
    ])
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() =>
      expect(cardText('Guardrail')).toHaveTextContent(
        'Failed: cited policy wording the policy does not contain',
      ),
    )
    expect(cardText('Adjuster')).toHaveTextContent(
      'Recommends $1,400,000 from the fixed demonstration file, no model call (82% confident)',
    )
    expect(screen.getByText('Awaiting human review')).toBeInTheDocument()
    const rules = screen.getByTestId('fired-rules')
    expect(rules).toHaveTextContent('Why it went to a person')
    expect(
      within(rules)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Guardrail check did not pass', 'Settlement over the $250,000 ceiling: $1,400,000'])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

// Prompt 30 addition: a person's decision does not change the run's recorded
// status, so the page reads the human row under the run.
describe('RunDetailPage after a person has decided', () => {
  const AWAITING = { status: 'awaiting_human', escalation_decision: null }

  beforeEach(() => {
    streamState.events = []
  })
  afterEach(() => vi.unstubAllGlobals())

  it('reads an approval: the badge says Approved and the header says who, when and why', async () => {
    stubFetch([
      ['/api/runs/', AWAITING],
      ['/api/audit', decisionRows('approved', 'Within the reinsurance layer.')],
    ])
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() => expect(screen.getByTestId('run-decision')).toBeInTheDocument())
    const line = screen.getByTestId('run-decision')
    expect(line).toHaveTextContent(`Approved by Dermot on ${formatDateTime(DECIDED_AT)}.`)
    expect(line).toHaveTextContent('Within the reinsurance layer.')
    expect(screen.getByText('Approved')).toHaveClass('bg-green-100')
    expect(screen.queryByText('Awaiting human review')).not.toBeInTheDocument()
    // The rules that sent the claim to the person stay above the decision.
    expect(screen.getByTestId('fired-rules')).toHaveTextContent(
      'Settlement over the $250,000 ceiling',
    )
  })

  it('reads a rejection, saying when no comment was left', async () => {
    stubFetch([
      ['/api/runs/', AWAITING],
      ['/api/audit', decisionRows('rejected', null)],
    ])
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() =>
      expect(screen.getByTestId('run-decision')).toHaveTextContent('Rejected by Dermot on'),
    )
    expect(screen.getByTestId('run-decision')).toHaveTextContent('No comment was left.')
    expect(screen.getByText('Rejected')).toHaveClass('bg-red-100')
  })

  it('keeps the recorded status while no person has decided', async () => {
    stubFetch([
      ['/api/runs/', AWAITING],
      ['/api/audit', guardrailFailureRows()],
    ])
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() => expect(screen.getByText('Awaiting human review')).toBeInTheDocument())
    expect(screen.queryByTestId('run-decision')).not.toBeInTheDocument()
  })
})

describe('RunDetailPage watching a live abort', () => {
  beforeEach(() => stubFetch([]))
  afterEach(() => vi.unstubAllGlobals())

  it('moves the failing card to Failed and the later card to Not run at once', () => {
    const base = { correlation_id: 'cid-1', timestamp: 't' }
    streamState.events = [
      { ...base, event_type: 'pipeline_started', variant: 'default' },
      {
        ...base,
        event_type: 'agent_completed',
        agent: 'doc_parser',
        duration_ms: 1300,
        summary: { claim_type: 'hail' },
      },
      {
        ...base,
        event_type: 'agent_completed',
        agent: 'validator',
        duration_ms: 3000,
        summary: { covered: true },
      },
      { ...base, event_type: 'agent_started', agent: 'adjuster' },
      {
        ...base,
        event_type: 'pipeline_aborted',
        failing_agent: 'adjuster',
        error_type: 'ValueError',
        message:
          "MarketDataTable.lookup: unknown claim_type 'hail' (normalised='hail'); supported types=[]",
      },
    ]
    renderWithProviders(<App />, { route: STARTED_HERE })
    const adjuster = screen.getByText('Adjuster').closest('button')!
    expect(adjuster).toHaveTextContent(
      'Failed: the Adjuster has no market range for the claim type Hail',
    )
    expect(screen.getByText('Guardrail').closest('button')!).toHaveTextContent(
      'Not run: the run stopped at the Adjuster',
    )
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Run aborted')
    expect(screen.getByText('Aborted')).toBeInTheDocument()
    expect(screen.queryByTestId('awaiting-hint')).not.toBeInTheDocument()
  })
})
