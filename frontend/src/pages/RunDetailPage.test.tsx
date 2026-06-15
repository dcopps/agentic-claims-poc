import { QueryClient } from '@tanstack/react-query'
import { screen, waitFor } from '@testing-library/react'
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
