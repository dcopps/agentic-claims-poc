import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClaimRecord } from '../api/types'
import { CompareView } from './CompareView'

function claim(): ClaimRecord {
  return {
    claim_id: 'claim-1',
    claim_number: 'CLM-2026-AAAA',
    line_of_business: 'Commercial Property',
    claimant_name: 'Acme Logistics Ltd',
    policy_number: 'POL-1',
    loss_date: '2026-04-01',
    reported_date: '2026-04-03',
    jurisdiction: 'United Kingdom',
    narrative: 'Loss.',
    claim_type: 'water_damage',
    reported_amount: '85000.00',
    status: 'settled',
    scenario_tag: null,
    created_at: '2026-04-03T00:00:00Z',
    updated_at: '2026-04-03T00:00:00Z',
  }
}

const RUNS = [
  { correlation_id: 'aaaaaaaa-1111', variant: 'default', status: 'settled', started_at: 't', completed_at: 't', escalate: false },
  { correlation_id: 'bbbbbbbb-2222', variant: 'v2_strict_validator', status: 'awaiting_human', started_at: 't', completed_at: 't', escalate: true },
]

const COMPARISON = {
  run_a: {},
  run_b: {},
  diff: {
    settlement_changed: false,
    settlement_a: '85000.00',
    settlement_b: '85000.00',
    escalation_changed: true,
    escalate_a: false,
    escalate_b: true,
    fired_rules_added: ['validator_confidence_floor'],
    fired_rules_removed: [],
    guardrail_changed: false,
    guardrail_passed_a: true,
    guardrail_passed_b: true,
  },
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('CompareView', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        Promise.resolve(
          url.includes('/compare/') ? jsonResponse(COMPARISON) : jsonResponse(RUNS),
        ),
      ),
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('loads runs, compares, and highlights the diff', async () => {
    const user = userEvent.setup()
    render(<CompareView claims={[claim()]} />)

    await user.selectOptions(screen.getByLabelText('Select a claim'), 'claim-1')
    await waitFor(() => expect(screen.getByLabelText('Run A')).toBeInTheDocument())

    await user.selectOptions(screen.getByLabelText('Run A'), 'aaaaaaaa-1111')
    await user.selectOptions(screen.getByLabelText('Run B'), 'bbbbbbbb-2222')
    await user.click(screen.getByRole('button', { name: /compare/i }))

    await waitFor(() =>
      expect(screen.getByLabelText('Comparison diff')).toBeInTheDocument(),
    )
    expect(screen.getByText('validator_confidence_floor', { exact: false })).toBeInTheDocument()
  })
})
