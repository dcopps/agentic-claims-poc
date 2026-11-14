import { useQueryClient } from '@tanstack/react-query'
import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { submitHumanDecision } from '../api/client'
import type { AuditEntry } from '../api/types'
import { claimCopy } from '../copy/claim'
import { ruleLine } from '../copy/run'
import { deriveWhyHere } from '../pages/claimDerivation'
import { deriveCards } from '../pages/runDerivation'
import { Badge, Button, Card, Spinner } from './ui'
import { WakingNotice } from './WakingNotice'

type Decision = 'approved' | 'rejected'

interface HumanReviewPanelProps {
  claimId: string
  // The latest run: api/human.py writes the decision's audit row under it.
  correlationId: string
  rows: AuditEntry[]
  loading: boolean
}

// The human review panel (Phase 6; rewritten by Prompt 30). The evidence is the
// latest run's audit rows, which the claim page loads once and passes down, in
// the order a reviewer needs it: why the claim is here, the figure, the
// reasoning, the Guardrail's verdict, the passages. The sentences are the run
// page's own, so a reviewer reads one vocabulary on both pages.
export function HumanReviewPanel({ claimId, correlationId, rows, loading }: HumanReviewPanelProps) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const decide = async (decision: Decision, decidedBy: string, comment: string) => {
    setError(null)
    setBusy(true)
    try {
      await submitHumanDecision(claimId, { decision, decided_by: decidedBy, comment })
      // The claim's status changes and the human row lands under this run, so
      // both caches are refreshed and the page swaps this panel for the
      // Decision card without a reload.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['claim', claimId] }),
        queryClient.invalidateQueries({ queryKey: ['audit', correlationId] }),
      ])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title={claimCopy.panelHeading}>
      {loading && <Spinner label={claimCopy.loadingEvidence} />}
      <WakingNotice waiting={loading} />
      {rows.length > 0 && <Evidence rows={rows} />}
      <DecisionForm busy={busy} error={error} onDecide={decide} />
    </Card>
  )
}

type Obj = Record<string, unknown>

function obj(value: unknown): Obj {
  return typeof value === 'object' && value !== null ? (value as Obj) : {}
}

// Card states that say nothing yet about what the agent concluded.
const UNDECIDED = new Set(['queued', 'running', 'not_run'])

function Evidence({ rows }: { rows: AuditEntry[] }) {
  const rules = deriveWhyHere(rows)
  const cards = deriveCards(rows, [])
  const adjusterRow = rows.find((r) => r.step === 'settlement_estimate')?.payload
  const reasoning = obj(adjusterRow?.output).reasoning
  const coverage = rows.find((r) => r.step === 'coverage_check')?.payload
  return (
    <dl className="space-y-3 text-sm">
      {rules.length > 0 && (
        <Section heading={claimCopy.whyHeading} testId="why-here">
          <ul className="list-disc pl-5 text-slate-700">
            {rules.map((rule) => (
              <li key={rule.name}>{ruleLine(rule)}</li>
            ))}
          </ul>
        </Section>
      )}
      {cards.adjuster.status === 'done' && (
        <Section heading={claimCopy.settlementHeading} testId="settlement">
          {cards.adjuster.summary}
        </Section>
      )}
      {typeof reasoning === 'string' && reasoning !== '' && (
        <Section heading={claimCopy.reasoningHeading} testId="reasoning">
          <p className="text-slate-700">{reasoning}</p>
        </Section>
      )}
      {!UNDECIDED.has(cards.guardrail.status) && (
        <Section heading={claimCopy.guardrailHeading} testId="guardrail-verdict">
          {cards.guardrail.summary}
          {cards.guardrail.detail && (
            <span className="block text-xs text-slate-500">{cards.guardrail.detail}</span>
          )}
        </Section>
      )}
      <Passages coverage={coverage} />
    </dl>
  )
}

function Section({
  heading,
  testId,
  children,
}: {
  heading: string
  testId: string
  children: ReactNode
}) {
  return (
    <div data-testid={testId}>
      <dt className="text-slate-500">{heading}</dt>
      <dd className="text-slate-700">{children}</dd>
    </div>
  )
}

// The Validator's retrieved passages (Prompt 27): `cited_chunks` carries chunk
// ids without the text, so the list is the coverage_check payload's retrieved
// chunks, each linked to its place on the Policy page and badged when the
// verdict cited it.
function Passages({ coverage }: { coverage: Obj | undefined }) {
  const chunks = obj(coverage?.retrieval).chunks
  const chunkList = Array.isArray(chunks) ? chunks.map(obj) : []
  if (chunkList.length === 0) return null
  const cited = citedIds(coverage)
  return (
    <Section heading={claimCopy.passagesHeading} testId="passages">
      {chunkList.map((chunk, i) => (
        <p key={i} className="text-slate-600">
          <Link
            to={{ pathname: '/policy', hash: String(chunk.chunk_id) }}
            className="font-medium text-blue-700 hover:underline"
          >
            {String(chunk.section)}
          </Link>
          {cited.has(String(chunk.chunk_id)) && (
            <>
              {' '}
              <Badge tone="success">{claimCopy.cited}</Badge>
            </>
          )}
          : {String(chunk.content_excerpt)}
        </p>
      ))}
    </Section>
  )
}

function citedIds(coverage: Obj | undefined): Set<string> {
  const cited = obj(coverage?.verdict).cited_chunks
  if (!Array.isArray(cited)) return new Set()
  return new Set(
    cited.flatMap((c) => {
      const id = obj(c).chunk_id
      return typeof id === 'string' ? [id] : []
    }),
  )
}

interface DecisionFormProps {
  busy: boolean
  error: string | null
  onDecide: (decision: Decision, decidedBy: string, comment: string) => void
}

const INPUT_CLASS = 'rounded border border-slate-300 px-2 py-1 text-sm'

// Labelled inputs, the two buttons, and under them what each does. The buttons
// stay disabled until a name is typed, and a line says so (plan D5), as the
// Claims page explains its disabled action.
function DecisionForm({ busy, error, onDecide }: DecisionFormProps) {
  const [decidedBy, setDecidedBy] = useState('')
  const [comment, setComment] = useState('')
  const id = useId()
  const named = decidedBy.trim() !== ''
  return (
    <div className="mt-4 space-y-2 border-t border-slate-200 pt-3 text-sm">
      <LabelledField id={`${id}-name`} label={claimCopy.nameLabel}>
        <input
          id={`${id}-name`}
          className={`${INPUT_CLASS} max-w-xs`}
          value={decidedBy}
          onChange={(e) => setDecidedBy(e.target.value)}
        />
      </LabelledField>
      <LabelledField id={`${id}-comment`} label={claimCopy.commentLabel}>
        <textarea
          id={`${id}-comment`}
          className={`${INPUT_CLASS} w-full`}
          rows={2}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </LabelledField>
      {error && <p className="text-red-600">{error}</p>}
      <div className="space-x-2">
        <Button onClick={() => onDecide('approved', decidedBy, comment)} disabled={busy || !named}>
          {claimCopy.approve}
        </Button>
        <Button
          variant="danger"
          onClick={() => onDecide('rejected', decidedBy, comment)}
          disabled={busy || !named}
        >
          {claimCopy.reject}
        </Button>
      </div>
      {!named && (
        <p className="text-xs text-slate-500" data-testid="name-required">
          {claimCopy.nameRequired}
        </p>
      )}
      <WhatTheButtonsDo />
    </div>
  )
}

// A visible label over its control, as the claim form's fields have.
function LabelledField({
  id,
  label,
  children,
}: {
  id: string
  label: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-slate-600">
        {label}
      </label>
      {children}
    </div>
  )
}

function WhatTheButtonsDo() {
  return (
    <ul className="space-y-0.5 text-xs text-slate-600" data-testid="button-effects">
      <li>{claimCopy.approveDoes}</li>
      <li>{claimCopy.rejectDoes}</li>
      <li>{claimCopy.decisionRecorded}</li>
    </ul>
  )
}
