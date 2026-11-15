import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { MockEventSource } from '../setupTests'
import { useRunStream } from './useRunStream'

// The hook's second job is feeding the query cache, so the test watches which
// queries it invalidates on each kind of event.
function setup() {
  const client = new QueryClient()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useRunStream('cid-1', 'c1'), { wrapper })
  return { hook, invalidate, source: MockEventSource.latest() }
}

function frame(event_type: string, extra: Record<string, unknown> = {}): string {
  return JSON.stringify({ event_type, correlation_id: 'cid-1', timestamp: 't', ...extra })
}

// The query keys the hook invalidated, in order, as strings for a plain equality.
function invalidated(invalidate: ReturnType<typeof setup>['invalidate']): string[] {
  return invalidate.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey))
}

describe('useRunStream', () => {
  it('accumulates events and re-reads the run and its rows at each agent completion', () => {
    const { hook, invalidate, source } = setup()
    expect(source.url).toContain('cid-1')
    act(() => source.emit('pipeline_started', frame('pipeline_started')))
    act(() => source.emit('agent_completed', frame('agent_completed', { agent: 'doc_parser' })))
    expect(hook.result.current.map((e) => e.event_type)).toEqual([
      'pipeline_started',
      'agent_completed',
    ])
    expect(invalidated(invalidate)).toEqual([
      JSON.stringify(['run', 'cid-1']),
      JSON.stringify(['audit', 'cid-1']),
    ])
    expect(source.closed).toBe(false)
  })

  // Prompt 31 fix: the escalation and terminal rows land after the last agent's
  // completion, so the finished record must be read again at the terminal event
  // or the page keeps the rows it read before the decision was written.
  it('re-reads the finished record at the terminal event, then closes the stream', () => {
    const { invalidate, source } = setup()
    act(() =>
      source.emit('pipeline_completed', frame('pipeline_completed', { status: 'awaiting_human' })),
    )
    expect(invalidated(invalidate)).toEqual([
      JSON.stringify(['run', 'cid-1']),
      JSON.stringify(['audit', 'cid-1']),
      JSON.stringify(['claims']),
      JSON.stringify(['claim', 'c1']),
    ])
    expect(source.closed).toBe(true)
  })

  it('ignores a malformed frame and keeps the stream open', () => {
    const { hook, invalidate, source } = setup()
    act(() => source.emit('agent_started', 'not json'))
    expect(hook.result.current).toEqual([])
    expect(invalidate).not.toHaveBeenCalled()
    expect(source.closed).toBe(false)
  })
})
