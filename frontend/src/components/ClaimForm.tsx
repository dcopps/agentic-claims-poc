import { cloneElement, useId, useState } from 'react'
import { submitClaim } from '../api/client'
import type { ClaimSubmission, ClaimType } from '../api/types'
import { claimTypeLabel } from '../copy/labels'
import { tooltips } from '../copy/tooltips'
import { demoClaims } from '../fixtures/demoClaims'
import { Tooltip } from './Tooltip'

const CLAIM_TYPES: ClaimType[] = ['water_damage', 'fire', 'wind', 'theft', 'flood', 'storm_complex']

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

// The visible label for each field (Prompt 28). The stored field names are the
// API's; the labels are the reader's.
type FieldName = Exclude<keyof ClaimSubmission, 'scenario_tag'>

const FIELD_LABELS: Record<FieldName, string> = {
  claimant_name: 'Claimant name',
  policy_number: 'Policy number',
  loss_date: 'Loss date',
  reported_date: 'Reported date',
  jurisdiction: 'Jurisdiction',
  reported_amount: 'Reported amount (USD)',
  claim_type: 'Claim type',
  narrative: 'Description',
}

const INPUT_CLASS = 'rounded border border-slate-300 px-2 py-1'

interface ClaimFormProps {
  onSubmitted: () => void
}

// Claim submission form. The three "Load demo claim" buttons pre-fill from the
// client-side fixtures; submit posts to /api/claims and notifies the parent so
// the list refreshes. Field-level validation is the backend's (a 422 surfaces
// here as an error message). Every field has a visible <label> tied to its
// input, so the two date fields stay distinguishable once filled; option text
// is the plain-words label while the submitted value is the stored one.
export function ClaimForm({ onSubmitted }: ClaimFormProps) {
  const [form, setForm] = useState<ClaimSubmission>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const idPrefix = useId()

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

  const field = (name: FieldName, input: React.ReactElement<{ id?: string }>) => (
    <Field id={`${idPrefix}-${name}`} label={FIELD_LABELS[name]}>
      {input}
    </Field>
  )

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
        {field(
          'claimant_name',
          <TextInput value={form.claimant_name} onChange={(v) => update('claimant_name', v)} />,
        )}
        {field(
          'policy_number',
          <TextInput value={form.policy_number} onChange={(v) => update('policy_number', v)} />,
        )}
        {field(
          'loss_date',
          <TextInput type="date" value={form.loss_date} onChange={(v) => update('loss_date', v)} />,
        )}
        {field(
          'reported_date',
          <TextInput
            type="date"
            value={form.reported_date}
            onChange={(v) => update('reported_date', v)}
          />,
        )}
        {field(
          'jurisdiction',
          <TextInput value={form.jurisdiction} onChange={(v) => update('jurisdiction', v)} />,
        )}
        {field(
          'reported_amount',
          <TextInput
            inputMode="decimal"
            value={form.reported_amount}
            onChange={(v) => update('reported_amount', v)}
          />,
        )}
        {field(
          'claim_type',
          <select
            className={INPUT_CLASS}
            value={form.claim_type}
            onChange={(e) => update('claim_type', e.target.value)}
          >
            {CLAIM_TYPES.map((type) => (
              <option key={type} value={type}>
                {claimTypeLabel(type)}
              </option>
            ))}
          </select>,
        )}
      </div>

      {field(
        'narrative',
        <textarea
          className={`w-full ${INPUT_CLASS}`}
          rows={3}
          value={form.narrative}
          onChange={(e) => update('narrative', e.target.value)}
        />,
      )}

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

// A labelled field: the <label> is tied to the input by id, so it stays visible
// once the field is filled and `getByLabelText` finds the control.
function Field({
  id,
  label,
  children,
}: {
  id: string
  label: string
  children: React.ReactElement<{ id?: string }>
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-slate-600">
        {label}
      </label>
      {cloneElement(children, { id })}
    </div>
  )
}

function TextInput({
  value,
  onChange,
  type = 'text',
  inputMode,
  id,
}: {
  value: string
  onChange: (value: string) => void
  type?: string
  inputMode?: 'decimal'
  id?: string
}) {
  return (
    <input
      id={id}
      type={type}
      inputMode={inputMode}
      className={INPUT_CLASS}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}
