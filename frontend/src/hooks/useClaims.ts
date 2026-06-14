import { useCallback, useEffect, useState } from 'react'
import { listClaims } from '../api/client'
import type { ClaimRecord } from '../api/types'

interface UseClaims {
  claims: ClaimRecord[]
  error: string | null
  refetch: () => Promise<void>
}

// Loads the claims list on mount and exposes a refetch the caller invokes after a
// submission or a run completes. Plain fetch + state — no query library. The
// mount load sets state inside the fetch's resolution callback (not synchronously
// in the effect body); `refetch` is for the event-handler call sites.
export function useClaims(): UseClaims {
  const [claims, setClaims] = useState<ClaimRecord[]>([])
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(async () => {
    try {
      setClaims(await listClaims())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    let active = true
    listClaims()
      .then((data) => {
        if (active) {
          setClaims(data)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      active = false
    }
  }, [])

  return { claims, error, refetch }
}
