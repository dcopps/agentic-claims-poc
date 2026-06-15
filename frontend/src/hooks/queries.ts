import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import {
  getAgentPrompt,
  getClaim,
  getRun,
  listAuditEntries,
  listClaimRuns,
  listClaims,
} from '../api/client'
import type {
  AgentPrompt,
  AuditEntry,
  ClaimRecord,
  PipelineResult,
  RunSummary,
} from '../api/types'

// Read hooks over the API, backed by TanStack Query. Query keys are namespaced so
// mutations (submit, run, replay, human-decision) and the SSE stream can
// invalidate precisely. In-flight data uses staleTime 0; claims/audit are stable
// enough for a short cache.

const FRESH = 5 * 60 * 1000 // 5 minutes — claims/audit don't change mid-view

export function useClaims(): UseQueryResult<ClaimRecord[]> {
  return useQuery({ queryKey: ['claims'], queryFn: () => listClaims(), staleTime: FRESH })
}

export function useClaim(claimId: string): UseQueryResult<ClaimRecord> {
  return useQuery({
    queryKey: ['claim', claimId],
    queryFn: () => getClaim(claimId),
    staleTime: FRESH,
  })
}

export function useClaimRuns(claimId: string): UseQueryResult<RunSummary[]> {
  return useQuery({
    queryKey: ['claim', claimId, 'runs'],
    queryFn: () => listClaimRuns(claimId),
    staleTime: 0, // a run in flight changes this
  })
}

export function useRun(correlationId: string): UseQueryResult<PipelineResult> {
  return useQuery({
    queryKey: ['run', correlationId],
    queryFn: () => getRun(correlationId),
    staleTime: 0,
    retry: false, // an in-flight run 404s until it terminates; don't hammer
  })
}

export function useAuditEntries(correlationId: string): UseQueryResult<AuditEntry[]> {
  return useQuery({
    queryKey: ['audit', correlationId],
    queryFn: () => listAuditEntries(correlationId),
    staleTime: 0,
    retry: false,
  })
}

export function useAgentPrompt(
  agent: string,
  variant: string,
  enabled: boolean,
): UseQueryResult<AgentPrompt> {
  return useQuery({
    queryKey: ['agentPrompt', agent, variant],
    queryFn: () => getAgentPrompt(agent, variant),
    staleTime: FRESH,
    enabled, // lazy — only fetched when the agent card is expanded
  })
}
