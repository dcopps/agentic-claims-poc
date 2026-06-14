import { useState } from 'react'
import { replayPipeline, runPipeline } from './api/client'
import { ClaimForm } from './components/ClaimForm'
import { ClaimList } from './components/ClaimList'
import { CompareView } from './components/CompareView'
import { ProgressStrip } from './components/ProgressStrip'
import { useClaims } from './hooks/useClaims'
import { useRunStream } from './hooks/useRunStream'

type View = 'claims' | 'compare'

// The default replay variant the "Re-process with v2" button uses.
const REPLAY_VARIANT = 'v2_strict_validator'

function App() {
  const { claims, error, refetch } = useClaims()
  const [view, setView] = useState<View>('claims')
  const [correlationId, setCorrelationId] = useState<string | null>(null)
  const [busyClaimId, setBusyClaimId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const events = useRunStream(correlationId)

  const trigger = async (claimId: string, kind: 'process' | 'replay') => {
    const cid = crypto.randomUUID()
    setActionError(null)
    setBusyClaimId(claimId)
    // Set the correlation id first so the SSE stream subscribes before the run
    // publishes events; the bus buffers anything published before it attaches.
    setCorrelationId(cid)
    try {
      if (kind === 'process') {
        await runPipeline(claimId, cid)
      } else {
        await replayPipeline(claimId, cid, REPLAY_VARIANT)
      }
      await refetch()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyClaimId(null)
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-4xl bg-slate-50 p-8 text-slate-800">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Agentic Claims POC</h1>
        <nav className="space-x-2 text-sm">
          <button
            type="button"
            className={view === 'claims' ? 'font-semibold underline' : ''}
            onClick={() => setView('claims')}
          >
            Claims
          </button>
          <button
            type="button"
            className={view === 'compare' ? 'font-semibold underline' : ''}
            onClick={() => setView('compare')}
          >
            Compare runs
          </button>
        </nav>
      </header>

      {error && <p className="mt-2 text-sm text-red-600">Failed to load claims: {error}</p>}
      {actionError && <p className="mt-2 text-sm text-red-600">{actionError}</p>}

      {view === 'claims' ? (
        <div className="mt-6 space-y-6">
          <section className="rounded border border-slate-200 p-4">
            <h2 className="mb-3 font-medium">Submit a claim</h2>
            <ClaimForm onSubmitted={refetch} />
          </section>

          {events.length > 0 && <ProgressStrip events={events} />}

          <section className="rounded border border-slate-200 p-4">
            <h2 className="mb-3 font-medium">Claims</h2>
            <ClaimList
              claims={claims}
              busyClaimId={busyClaimId}
              onProcess={(id) => trigger(id, 'process')}
              onReplay={(id) => trigger(id, 'replay')}
            />
          </section>
        </div>
      ) : (
        <section className="mt-6 rounded border border-slate-200 p-4">
          <h2 className="mb-3 font-medium">Compare runs</h2>
          <CompareView claims={claims} />
        </section>
      )}
    </main>
  )
}

export default App
