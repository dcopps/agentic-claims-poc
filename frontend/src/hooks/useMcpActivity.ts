import { useEffect, useState } from 'react'
import { mcpActivityUrl } from '../api/client'
import type { ToolCallRecord } from '../api/types'

// The SSE event name the backend's feed emits (backend/app/api/mcp.py).
const ACTIVITY_EVENT = 'tool_call'
// How many records the page keeps; the table-backed replay restores the latest
// on every connect, so an in-memory cap loses nothing that matters.
const MAX_RECORDS = 100

// Open the activity feed and keep the newest records first. Mirrors
// useRunStream's shape (native EventSource, named event, JSON.parse guarded)
// but with no terminal event: the feed is endless and closes only on unmount.
// Records are de-duplicated by call_id because every connect replays the last
// N, and a reconnect would otherwise show them twice.
export function useMcpActivity(): ToolCallRecord[] {
  const [records, setRecords] = useState<ToolCallRecord[]>([])

  useEffect(() => {
    const source = new EventSource(mcpActivityUrl())
    const onEvent = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as ToolCallRecord
        setRecords((prev) => prependRecord(prev, parsed))
      } catch {
        // A malformed frame is ignored rather than tearing the feed down.
      }
    }
    source.addEventListener(ACTIVITY_EVENT, onEvent as EventListener)
    return () => source.close()
  }, [])

  return records
}

// Newest first, no duplicate call_id, capped. Exported for its own tests.
export function prependRecord(prev: ToolCallRecord[], record: ToolCallRecord): ToolCallRecord[] {
  if (prev.some((r) => r.call_id === record.call_id)) return prev
  return [record, ...prev].slice(0, MAX_RECORDS)
}
