import { useEffect, useState } from 'react'

type BackendStatus = 'unknown' | 'ok' | 'unreachable'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function App() {
  const [status, setStatus] = useState<BackendStatus>('unknown')

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE}/health`)
      .then((res) => (res.ok ? 'ok' : 'unreachable'))
      .catch(() => 'unreachable' as const)
      .then((s) => {
        if (!cancelled) {
          setStatus(s as BackendStatus)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="min-h-screen bg-slate-50 text-slate-800 p-8">
      <h1 className="text-2xl font-semibold">Agentic Claims POC</h1>
      <p className="mt-2 text-slate-600">
        Phase 0 scaffold — backend health indicator.
      </p>
      <p className="mt-6" data-testid="backend-status">
        backend: <span className="font-mono">{status}</span>
      </p>
    </main>
  )
}

export default App
