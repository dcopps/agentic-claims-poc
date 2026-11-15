import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import {
  getClaim,
  getMcpCatalogue,
  getPolicy,
  getRun,
  listAuditEntries,
  listClaimRuns,
  listClaims,
  listRuns,
} from '../api/client'
import type {
  AuditEntry,
  ClaimRecord,
  McpCatalogue,
  PipelineResult,
  PolicyIndex,
  RunListItem,
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

// `enabled` lets the run page hold the fetch until it knows which claim the run
// recorded, rather than asking for the address's claim id and correcting later.
export function useClaim(claimId: string, enabled = true): UseQueryResult<ClaimRecord> {
  return useQuery({
    queryKey: ['claim', claimId],
    queryFn: () => getClaim(claimId),
    staleTime: FRESH,
    enabled,
  })
}

export function useClaimRuns(claimId: string): UseQueryResult<RunSummary[]> {
  return useQuery({
    queryKey: ['claim', claimId, 'runs'],
    queryFn: () => listClaimRuns(claimId),
    staleTime: 0, // a run in flight changes this
  })
}

// How many runs the Audit page's Recent runs list shows (Prompt 32).
export const RECENT_RUNS_LIMIT = 20

export function useRecentRuns(): UseQueryResult<RunListItem[]> {
  return useQuery({
    queryKey: ['runs', 'recent', RECENT_RUNS_LIMIT],
    queryFn: () => listRuns({ limit: RECENT_RUNS_LIMIT }),
    staleTime: 0, // a run just started belongs at the top
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

// `enabled` lets the claim page hold the fetch until the runs list names a
// latest run (Prompt 30), so a claim never run costs no audit request.
export function useAuditEntries(
  correlationId: string,
  enabled = true,
): UseQueryResult<AuditEntry[]> {
  return useQuery({
    queryKey: ['audit', correlationId],
    queryFn: () => listAuditEntries(correlationId),
    staleTime: 0,
    retry: false,
    enabled,
  })
}

export function useMcpCatalogue(): UseQueryResult<McpCatalogue> {
  return useQuery({
    queryKey: ['mcpCatalogue'],
    queryFn: () => getMcpCatalogue(),
    staleTime: FRESH, // the server's definitions change only with a deploy
  })
}

export function usePolicy(): UseQueryResult<PolicyIndex> {
  return useQuery({
    queryKey: ['policy'],
    queryFn: () => getPolicy(),
    staleTime: FRESH, // the index changes only when the policy is re-indexed
  })
}
