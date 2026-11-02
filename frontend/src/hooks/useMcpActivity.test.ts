import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ToolCallRecord } from '../api/types'
import { MockEventSource } from '../setupTests'
import { prependRecord, useMcpActivity } from './useMcpActivity'

function record(call_id: number, tool = 'get_run'): ToolCallRecord {
  return {
    call_id,
    called_at: '2026-11-02T10:00:00Z',
    tool,
    arguments: {},
    target: null,
    caller: 'shared-token',
    outcome: 'ok',
    error_class: null,
    latency_ms: 4,
  }
}

describe('prependRecord', () => {
  it('puts the newest first and drops a duplicate call_id', () => {
    const one = prependRecord([], record(1))
    const two = prependRecord(one, record(2))
    expect(two.map((r) => r.call_id)).toEqual([2, 1])
    expect(prependRecord(two, record(2))).toBe(two)
  })

  it('caps the list at 100', () => {
    let list: ToolCallRecord[] = []
    for (let i = 1; i <= 120; i++) list = prependRecord(list, record(i))
    expect(list).toHaveLength(100)
    expect(list[0].call_id).toBe(120)
  })
})

describe('useMcpActivity', () => {
  it('opens the feed, accumulates frames newest first, and ignores a malformed one', () => {
    const { result, unmount } = renderHook(() => useMcpActivity())
    const source = MockEventSource.latest()
    expect(source.url).toContain('/api/mcp/activity')
    act(() => source.emit('tool_call', JSON.stringify(record(1, 'list_claims'))))
    act(() => source.emit('tool_call', 'not json'))
    act(() => source.emit('tool_call', JSON.stringify(record(2, 'verify_chain'))))
    expect(result.current.map((r) => r.tool)).toEqual(['verify_chain', 'list_claims'])
    unmount()
    expect(source.closed).toBe(true)
  })
})
