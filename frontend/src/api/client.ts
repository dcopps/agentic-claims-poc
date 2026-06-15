// Typed fetch wrappers over the backend API. One small module so every component
// shares the same base URL and error handling. No state library — plain fetch.

import type {
  AgentPrompt,
  AuditEntry,
  ChainVerification,
  ClaimRecord,
  ClaimStatus,
  ClaimSubmission,
  HumanDecisionBody,
  PipelineResult,
  RunComparison,
  RunSummary,
} from './types'

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    // Surface the backend's detail message so the UI can show why a request
    // failed (a 409 active-run, a 422 validation error, etc.).
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
    } catch {
      // non-JSON error body — keep the status line
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export function submitClaim(submission: ClaimSubmission): Promise<ClaimRecord> {
  return request<ClaimRecord>('/api/claims', {
    method: 'POST',
    body: JSON.stringify(submission),
  })
}

export function listClaims(status?: ClaimStatus): Promise<ClaimRecord[]> {
  const query = status ? `?status=${status}` : ''
  return request<ClaimRecord[]>(`/api/claims${query}`)
}

export function listClaimRuns(claimId: string): Promise<RunSummary[]> {
  return request<RunSummary[]>(`/api/claims/${claimId}/runs`)
}

export function runPipeline(
  claimId: string,
  correlationId: string,
  variant = 'default',
): Promise<PipelineResult> {
  return request<PipelineResult>(
    `/api/pipeline/run/${claimId}?variant=${variant}&correlation_id=${correlationId}`,
    { method: 'POST' },
  )
}

export function replayPipeline(
  claimId: string,
  correlationId: string,
  variant: string,
): Promise<PipelineResult> {
  return request<PipelineResult>(
    `/api/pipeline/replay/${claimId}?variant=${variant}&correlation_id=${correlationId}`,
    { method: 'POST' },
  )
}

export function compareRuns(a: string, b: string): Promise<RunComparison> {
  return request<RunComparison>(`/api/runs/compare/${a}/${b}`)
}

export function getClaim(claimId: string): Promise<ClaimRecord> {
  return request<ClaimRecord>(`/api/claims/${claimId}`)
}

export function getRun(correlationId: string): Promise<PipelineResult> {
  return request<PipelineResult>(`/api/runs/${correlationId}`)
}

export function listAuditEntries(correlationId: string): Promise<AuditEntry[]> {
  return request<AuditEntry[]>(`/api/audit?correlation_id=${correlationId}`)
}

export function verifyChain(correlationId: string): Promise<ChainVerification> {
  return request<ChainVerification>(`/api/audit/verify/${correlationId}`)
}

export function submitHumanDecision(
  claimId: string,
  body: HumanDecisionBody,
): Promise<ClaimRecord> {
  return request<ClaimRecord>(`/api/claims/${claimId}/human-decision`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getAgentPrompt(agent: string, variant = 'default'): Promise<AgentPrompt> {
  return request<AgentPrompt>(`/api/agents/${agent}/prompt?variant=${variant}`)
}

export function testAgent<T>(agent: string, body: unknown, variant = 'default'): Promise<T> {
  return request<T>(`/api/agents/test/${agent}?variant=${variant}`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function streamUrl(correlationId: string): string {
  return `${API_BASE}/api/pipeline/stream/${correlationId}`
}
