import { useState } from 'react'
import { testAgent } from '../api/client'
import { Button, Card, JsonBlock } from './ui'

// One agent's test-bench panel. The request body is a JSON textarea (pre-filled
// with a valid sample); submit posts to the agent's test endpoint and renders the
// typed output + LLM-call metadata. Out-of-band: no claim, no audit entry.
export function AgentTestPanel({
  agent,
  label,
  sample,
}: {
  agent: string
  label: string
  sample: string
}) {
  const [body, setBody] = useState(sample)
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    setError(null)
    setBusy(true)
    try {
      const parsed = JSON.parse(body)
      setResult(await testAgent(agent, parsed))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title={label}>
      <textarea
        aria-label={`${label} input`}
        className="w-full rounded border border-slate-300 p-2 font-mono text-xs"
        rows={5}
        value={body}
        onChange={(e) => setBody(e.target.value)}
      />
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      <div className="mt-2">
        <Button onClick={run} disabled={busy}>
          {busy ? 'Running…' : `Run ${label}`}
        </Button>
      </div>
      {result !== null && (
        <div className="mt-3">
          <JsonBlock value={result} />
        </div>
      )}
    </Card>
  )
}
