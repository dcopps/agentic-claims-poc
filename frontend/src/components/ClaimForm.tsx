import { useState } from 'react'
import { submitClaim } from '../api/client'
import type { ClaimSubmission, ClaimType } from '../api/types'
import { demoClaims } from '../fixtures/demoClaims'
import { tooltips } from '../copy/tooltips'
import { Tooltip } from './Tooltip'

const CLAIM_TYPES: ClaimType[] = [
  'water_damage',
  'fire',
  'wind',
  'theft',
  'flood',
  'storm_complex',
]

const EMPTY: ClaimSubmission = {
  claimant_name: '',
  policy_number: '',
  loss_date: '',
  reported_date: '',
  jurisdiction: '',
  narrative: '',
  claim_type: 'water_damage',
  reported_amount: '',
}

interface ClaimFormProps {
  onSubmitted: () => void
}

// Claim submission form. The three "Load demo claim" buttons pre-fill from the
// client-side fixtures; submit posts to /api/claims and notifies the parent so
// the list refreshes. Field-level validation is the backend's (a 422 surfaces
// here as an error message).
export function ClaimForm({ onSubmitted }: ClaimFormProps) {
  const [form, setForm] = useState<ClaimSubmission>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const update = (field: keyof ClaimSubmission, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await submitClaim(form)
      setForm(EMPTY)
      onSubmitted()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3" aria-label="Submit a claim">
      <div className="flex flex-wrap gap-2">
        {demoClaims.map((demo) => (
          <button
            key={demo.label}
            type="button"
            className="rounded border border-slate-300 px-2 py-1 text-xs"
            onClick={() => setForm(demo.submission)}
          >
            {demo.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <input
          aria-label="Claimant name"
          placeholder="Claimant name"
          className="rounded border border-slate-300 px-2 py-1"
          value={form.claimant_name}
          onChange={(e) => update('claimant_name', e.target.value)}
        />
        <input
          aria-label="Policy number"
          placeholder="Policy number"
          className="rounded border border-slate-300 px-2 py-1"
          value={form.policy_number}
          onChange={(e) => update('policy_number', e.target.value)}
        />
        <input
          aria-label="Loss date"
          type="date"
          className="rounded border border-slate-300 px-2 py-1"
          value={form.loss_date}
          onChange={(e) => update('loss_date', e.target.value)}
        />
        <input
          aria-label="Reported date"
          type="date"
          className="rounded border border-slate-300 px-2 py-1"
          value={form.reported_date}
          onChange={(e) => update('reported_date', e.target.value)}
        />
        <input
          aria-label="Jurisdiction"
          placeholder="Jurisdiction"
          className="rounded border border-slate-300 px-2 py-1"
          value={form.jurisdiction}
          onChange={(e) => update('jurisdiction', e.target.value)}
        />
        <input
          aria-label="Reported amount"
          placeholder="Reported amount"
          className="rounded border border-slate-300 px-2 py-1"
          value={form.reported_amount}
          onChange={(e) => update('reported_amount', e.target.value)}
        />
        <select
          aria-label="Claim type"
          className="rounded border border-slate-300 px-2 py-1"
          value={form.claim_type}
          onChange={(e) => update('claim_type', e.target.value)}
        >
          {CLAIM_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      <textarea
        aria-label="Narrative"
        placeholder="Narrative"
        className="w-full rounded border border-slate-300 px-2 py-1"
        rows={3}
        value={form.narrative}
        onChange={(e) => update('narrative', e.target.value)}
      />

      {error && <p className="text-sm text-red-600">{error}</p>}

      <Tooltip text={tooltips.submitClaim}>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-slate-800 px-3 py-1.5 text-white disabled:opacity-50"
        >
          {busy ? 'Submitting…' : 'Submit Claim'}
        </button>
      </Tooltip>
    </form>
  )
}
