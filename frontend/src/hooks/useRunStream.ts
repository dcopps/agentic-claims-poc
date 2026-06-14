import { useEffect, useState } from 'react'
import { streamUrl } from '../api/client'
import type { PipelineEvent } from '../api/types'

// SSE event names the backend emits; each is dispatched by name, so we subscribe
// to each one. The two terminal events close the stream.
const EVENT_NAMES = [
  'pipeline_started',
  'agent_started',
  'agent_completed',
  'escalation_decision',
  'pipeline_completed',
  'pipeline_aborted',
]
const TERMINAL = new Set(['pipeline_completed', 'pipeline_aborted'])

interface StreamState {
  cid: string | null
  events: PipelineEvent[]
}

// Open an EventSource for `correlationId` and accumulate its events. State is
// keyed by the correlation id so a new run replaces the previous run's events
// without a synchronous reset in the effect body — every setState happens inside
// the subscription callback, which is how effects are meant to feed React.
export function useRunStream(correlationId: string | null): PipelineEvent[] {
  const [state, setState] = useState<StreamState>({ cid: null, events: [] })

  useEffect(() => {
    if (!correlationId) return
    const source = new EventSource(streamUrl(correlationId))
    const onEvent = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as PipelineEvent
        setState((prev) => ({
          cid: correlationId,
          // First event of a new correlation id replaces the prior run's list.
          events: prev.cid === correlationId ? [...prev.events, parsed] : [parsed],
        }))
        if (TERMINAL.has(parsed.event_type)) source.close()
      } catch {
        // Ignore a malformed frame rather than tearing down the strip.
      }
    }
    for (const name of EVENT_NAMES) {
      source.addEventListener(name, onEvent as EventListener)
    }
    return () => source.close()
  }, [correlationId])

  // Show events only for the active correlation id (the previous run's list is
  // discarded the moment the id changes, before the first new event arrives).
  return state.cid === correlationId ? state.events : []
}
