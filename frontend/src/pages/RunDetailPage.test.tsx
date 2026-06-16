import { QueryClient } from '@tanstack/react-query'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { PipelineEvent } from '../api/types'
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

describe('RunDetailPage', () => {
  beforeEach(() => {
    streamState.events = []
    stubFetch([]) // runs + audit endpoints 404 (in-flight): expected, not an error
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders queued cards and an awaiting hint when no run data exists yet', async () => {
    renderWithProviders(<App />, { route: ROUTE })
    await waitFor(() =>
      expect(screen.getByTestId('awaiting-hint')).toBeInTheDocument(),
    )
    expect(screen.getByText('Doc-Parser')).toBeInTheDocument()
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
    expect(screen.getByRole('alert')).toHaveTextContent(/aborted at doc_parser/i)
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
    fireEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(writeText).toHaveBeenCalledWith(FULL_CID)
  })

  it('links to the audit view of this run with the correlation id pre-filled', () => {
    renderWithProviders(<App />, { route: FULL_ROUTE })
    const link = screen.getByRole('link', { name: /view audit log/i })
    expect(link).toHaveAttribute('href', `/audit?correlation_id=${FULL_CID}`)
  })
})
