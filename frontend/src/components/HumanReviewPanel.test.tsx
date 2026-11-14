import { QueryClient } from '@tanstack/react-query'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuditEntry } from '../api/types'
import { claimCopy } from '../copy/claim'
import {
  ceilingRows,
  CORAL_BAY_FLAG,
  guardrailFailureRows,
  guardrailThrewRows,
} from '../test/runFixtures'
import { renderWithProviders, stubFetch } from '../test/utils'
import { HumanReviewPanel } from './HumanReviewPanel'

const ID_NAMED = '11111111-1111-4111-8111-111111111111'
const ID_EXCL = '22222222-2222-4222-8222-222222222222'

// Prompt 27: the Validator's coverage_check row — three retrieved passages are the
// list; the verdict's cited_chunks says which of them the decision rested on.
const COVERAGE: AuditEntry = {
  audit_id: 99,
  agent: 'validator',
  step: 'coverage_check',
  created_at: '2026-04-03T00:00:01Z',
  payload: {
    retrieval: {
      top_k: 2,
      chunks: [
        {
          chunk_id: ID_NAMED,
          section: 'Named Perils Covered',
          similarity: 0.71,
          content_excerpt: 'Fire, lightning, explosion…',
        },
        {
          chunk_id: ID_EXCL,
          section: 'Exclusions',
          similarity: 0.6,
          content_excerpt: 'We do not cover wear and tear…',
        },
      ],
    },
    verdict: {
      covered: true,
      confidence: 0.9,
      reasoning: 'Fire is a named peril.',
      policy_basis: 'Named Perils Covered',
      cited_chunks: [{ chunk_id: ID_NAMED, section: 'Named Perils Covered' }],
    },
  },
  chain_hash: 'y',
}

// Northwood's rows with the fixture's bare coverage_check swapped for one that
// carries passages.
const withPassages = (): AuditEntry[] =>
  ceilingRows().map((row) => (row.step === 'coverage_check' ? COVERAGE : row))

function renderPanel(rows: AuditEntry[], extra: { loading?: boolean; client?: QueryClient } = {}) {
  return renderWithProviders(
    <HumanReviewPanel
      claimId="c1"
      correlationId="cid-1"
      rows={rows}
      loading={extra.loading ?? false}
    />,
    { client: extra.client },
  )
}

const before = (a: HTMLElement, b: HTMLElement) =>
  (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0

describe('HumanReviewPanel', () => {
  let fetchMock: ReturnType<typeof stubFetch>
  beforeEach(() => {
    fetchMock = stubFetch([['human-decision', { status: 'settled' }]])
  })
  afterEach(() => vi.unstubAllGlobals())

  // Prompt 30: the evidence in reading order, in the run page's words.
  it('says first why the claim is here, then the settlement with its confidence', () => {
    renderPanel(ceilingRows())
    const why = screen.getByTestId('why-here')
    expect(why).toHaveTextContent('Why this claim is here')
    expect(within(why).getByRole('listitem')).toHaveTextContent(
      'Settlement over the $250,000 ceiling: $820,000',
    )
    const settlement = screen.getByTestId('settlement')
    expect(settlement).toHaveTextContent('Recommends $820,000 (85% confident)')
    expect(settlement).not.toHaveTextContent('820000.00')
    expect(before(why, settlement)).toBe(true)
    expect(screen.getByTestId('reasoning')).toHaveTextContent('The Adjuster’s reasoning')
    expect(screen.getByTestId('reasoning')).toHaveTextContent('Within range.')
    expect(screen.getByTestId('guardrail-verdict')).toHaveTextContent('Passed')
    expect(screen.queryByText(/flagged/)).not.toBeInTheDocument()
  })

  it('reads Coral Bay: two rules, the fixture sentence, the Guardrail’s failure with its detail', () => {
    renderPanel(guardrailFailureRows())
    const rules = within(screen.getByTestId('why-here')).getAllByRole('listitem')
    expect(rules.map((li) => li.textContent)).toEqual([
      'Guardrail check did not pass',
      'Settlement over the $250,000 ceiling: $1,400,000',
    ])
    expect(screen.getByTestId('settlement')).toHaveTextContent(
      'Recommends $1,400,000 from the fixed demonstration file, no model call (82% confident)',
    )
    const guardrail = screen.getByTestId('guardrail-verdict')
    expect(guardrail).toHaveTextContent('Failed: cited policy wording the policy does not contain')
    expect(guardrail).toHaveTextContent(CORAL_BAY_FLAG.detail)
  })

  it('gives the fail-closed line when the Guardrail itself threw', () => {
    renderPanel(guardrailThrewRows())
    expect(screen.getByTestId('why-here')).toHaveTextContent(
      'Guardrail check itself failed, so the claim went to a person',
    )
    expect(screen.getByTestId('guardrail-verdict')).toHaveTextContent(
      'Failed: the check itself raised an error, so the claim went to a person',
    )
  })

  it('links each retrieved passage to the Policy page and badges the cited one', () => {
    renderPanel(withPassages())
    expect(screen.getByText('Retrieved policy passages')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Named Perils Covered' })).toHaveAttribute(
      'href',
      `/policy#${ID_NAMED}`,
    )
    expect(screen.getByRole('link', { name: 'Exclusions' })).toHaveAttribute(
      'href',
      `/policy#${ID_EXCL}`,
    )
    expect(screen.getAllByText('cited')).toHaveLength(1)
    expect(screen.getByText(/We do not cover wear and tear/)).toBeInTheDocument()
    expect(screen.queryByText('Cited policy clauses')).not.toBeInTheDocument()
  })

  it('shows the evidence spinner while the rows load', () => {
    renderPanel([], { loading: true })
    expect(screen.getByRole('status')).toHaveTextContent('Loading evidence…')
  })

  it('labels the inputs, explains the disabled buttons, and says what each does', async () => {
    const user = userEvent.setup()
    renderPanel(ceilingRows())
    expect(screen.getByLabelText('Your name')).toBeInTheDocument()
    expect(screen.getByLabelText('Comment (optional)')).toBeInTheDocument()
    const approve = screen.getByRole('button', { name: 'Approve' })
    const reject = screen.getByRole('button', { name: 'Reject' })
    expect(approve).toBeDisabled()
    expect(reject).toBeDisabled()
    expect(screen.getByTestId('name-required')).toHaveTextContent('Enter your name to decide.')
    const effects = within(screen.getByTestId('button-effects')).getAllByRole('listitem')
    expect(effects.map((li) => li.textContent)).toEqual([
      claimCopy.approveDoes,
      claimCopy.rejectDoes,
      claimCopy.decisionRecorded,
    ])
    expect(claimCopy.rejectDoes).toContain('marks the claim Rejected')

    await user.type(screen.getByLabelText('Your name'), 'A. Reviewer')
    expect(approve).toBeEnabled()
    expect(reject).toBeEnabled()
    expect(screen.queryByTestId('name-required')).not.toBeInTheDocument()
  })

  it('posts the decision, then refreshes the claim and this run’s audit rows', async () => {
    const user = userEvent.setup()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderPanel(ceilingRows(), { client })
    await user.type(screen.getByLabelText('Your name'), 'A. Reviewer')
    await user.type(screen.getByLabelText('Comment (optional)'), 'Agreed.')
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/claims/c1/human-decision'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            decision: 'approved',
            decided_by: 'A. Reviewer',
            comment: 'Agreed.',
          }),
        }),
      ),
    )
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['audit', 'cid-1'] }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['claim', 'c1'] })
  })

  it('shows the backend’s reason when the decision is refused', async () => {
    const user = userEvent.setup()
    const detail = 'claim c1 is not awaiting human review (status=settled)'
    ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ detail }), { status: 409 })),
    )
    renderPanel(ceilingRows())
    await user.type(screen.getByLabelText('Your name'), 'A. Reviewer')
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(screen.getByText(detail)).toBeInTheDocument())
  })
})
