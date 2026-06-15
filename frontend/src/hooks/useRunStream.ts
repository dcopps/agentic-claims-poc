import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { streamUrl } from '../api/client'
import type { PipelineEvent } from '../api/types'

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

// Open an EventSource for `correlationId`, accumulate its events, AND feed the
// TanStack Query cache: each agent completion invalidates the run + audit queries
// so a lazily-expanded agent card sees its payload as soon as it is written; the
// terminal event invalidates the claim and its runs list. State is keyed by the
// correlation id so a new run replaces the previous run's events without a
// synchronous reset in the effect body.
export function useRunStream(
  correlationId: string | null,
  claimId?: string,
): PipelineEvent[] {
  const [state, setState] = useState<StreamState>({ cid: null, events: [] })
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!correlationId) return
    const source = new EventSource(streamUrl(correlationId))
    const onEvent = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data) as PipelineEvent
        setState((prev) => ({
          cid: correlationId,
          events: prev.cid === correlationId ? [...prev.events, parsed] : [parsed],
        }))
        if (parsed.event_type === 'agent_completed') {
          void queryClient.invalidateQueries({ queryKey: ['run', correlationId] })
          void queryClient.invalidateQueries({ queryKey: ['audit', correlationId] })
        }
        if (TERMINAL.has(parsed.event_type)) {
          source.close()
          void queryClient.invalidateQueries({ queryKey: ['claims'] })
          if (claimId) void queryClient.invalidateQueries({ queryKey: ['claim', claimId] })
        }
      } catch {
        // Ignore a malformed frame rather than tearing down the strip.
      }
    }
    for (const name of EVENT_NAMES) {
      source.addEventListener(name, onEvent as EventListener)
    }
    return () => source.close()
  }, [correlationId, claimId, queryClient])

  return state.cid === correlationId ? state.events : []
}
