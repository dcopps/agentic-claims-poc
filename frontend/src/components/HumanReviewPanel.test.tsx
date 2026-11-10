import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunSummary } from '../api/types'
import { renderWithProviders, stubFetch } from '../test/utils'
import { HumanReviewPanel } from './HumanReviewPanel'

const RUNS: RunSummary[] = [
  {
    correlation_id: 'cid-1',
    variant: 'default',
    status: 'awaiting_human',
    started_at: 't',
    completed_at: 't',
    escalate: true,
  },
]

const AUDIT = [
  {
    audit_id: 1,
    agent: 'adjuster',
    step: 'settlement_estimate',
    created_at: '2026-04-03T00:00:00Z',
    payload: { output: { recommended_settlement: '850000.00', reasoning: 'High value loss.' } },
    chain_hash: 'x',
  },
]

const ID_NAMED = '11111111-1111-4111-8111-111111111111'
const ID_EXCL = '22222222-2222-4222-8222-222222222222'

// Prompt 27: the Validator's coverage_check row — three retrieved passages are the
// list; the verdict's cited_chunks says which of them the decision rested on.
const COVERAGE = {
  audit_id: 2,
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

describe('HumanReviewPanel', () => {
  let fetchMock: ReturnType<typeof stubFetch>
  beforeEach(() => {
    fetchMock = stubFetch([
      ['human-decision', { status: 'settled' }],
      ['/api/audit', AUDIT],
    ])
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows the adjuster evidence from the audit payload', async () => {
    renderWithProviders(<HumanReviewPanel claimId="c1" runs={RUNS} />)
    await waitFor(() => expect(screen.getByText('850000.00')).toBeInTheDocument())
    expect(screen.getByText(/high value loss/i)).toBeInTheDocument()
  })

  it('links each retrieved passage to the Policy page and badges the cited one', async () => {
    stubFetch([
      ['human-decision', { status: 'settled' }],
      ['/api/audit', [...AUDIT, COVERAGE]],
    ])
    renderWithProviders(<HumanReviewPanel claimId="c1" runs={RUNS} />)
    await waitFor(() => expect(screen.getByText('Retrieved policy passages')).toBeInTheDocument())
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

  it('disables approve until a reviewer name is entered', () => {
    renderWithProviders(<HumanReviewPanel claimId="c1" runs={RUNS} />)
    expect(screen.getByRole('button', { name: /approve/i })).toBeDisabled()
  })

  it('submits an approval decision', async () => {
    const user = userEvent.setup()
    renderWithProviders(<HumanReviewPanel claimId="c1" runs={RUNS} />)
    await user.type(screen.getByLabelText('Decided by'), 'A. Reviewer')
    await user.click(screen.getByRole('button', { name: /approve/i }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('human-decision'),
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })
})
