import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuditEntry } from '../api/types'
import { tooltips } from '../copy/tooltips'
import { renderWithProviders, stubFetch } from '../test/utils'
import { AgentCard, type CardState } from './AgentCard'

// The states the run page derives (Prompt 29); the card renders what it is given.
const DONE: CardState = { status: 'done', summary: 'Done' }
const RUNNING: CardState = { status: 'running', summary: 'Running' }

// The raw template the fallback endpoint serves — placeholders intact.
const TEMPLATE = {
  agent: 'validator',
  variant: 'default',
  system: 'TEMPLATE-SYSTEM',
  user: 'TEMPLATE-USER {claim_narrative}',
}

// An audit entry whose llm_call carries the *filled* prompt (Phase 8.3) plus a
// verdict block — the normal post-capture shape.
function entryWithPrompt(): AuditEntry {
  return {
    audit_id: 1,
    agent: 'validator',
    step: 'coverage_check',
    created_at: '2026-06-16T00:00:00Z',
    chain_hash: 'deadbeef',
    payload: {
      llm_call: {
        provider: 'mock',
        prompt: { system: 'FILLED-SYSTEM', user: 'FILLED-USER mentions water damage' },
      },
      verdict: { covered: true },
    },
  }
}

// A historical entry: no llm_call.prompt (pre-dates the capture). Output present.
function entryWithoutPrompt(): AuditEntry {
  return {
    audit_id: 2,
    agent: 'validator',
    step: 'coverage_check',
    created_at: '2026-06-16T00:00:00Z',
    chain_hash: 'cafebabe',
    payload: { llm_call: { provider: 'mock' }, verdict: { covered: false } },
  }
}

describe('AgentCard', () => {
  beforeEach(() => stubFetch([['/api/agents/validator/prompt', TEMPLATE]]))
  afterEach(() => vi.unstubAllGlobals())

  it('renders collapsed with the label and status', () => {
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" state={DONE} variant="default" />,
    )
    expect(screen.getByText('Validator')).toBeInTheDocument()
    expect(screen.queryByText('FILLED-SYSTEM')).not.toBeInTheDocument()
  })

  it('renders the filled prompt from the audit entry without fetching the template', async () => {
    const user = userEvent.setup()
    const fetchMock = stubFetch([['/api/agents/validator/prompt', TEMPLATE]])
    renderWithProviders(
      <AgentCard
        agent="validator"
        label="Validator"
        state={DONE}
        variant="default"
        auditEntry={entryWithPrompt()}
      />,
    )
    await user.click(screen.getByRole('button'))
    expect(screen.getByText('FILLED-SYSTEM')).toBeInTheDocument()
    expect(screen.getByText(/FILLED-USER mentions water damage/)).toBeInTheDocument()
    // No placeholder leaks, and the template endpoint was never hit.
    expect(screen.queryByText(/\{claim_narrative\}/)).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('falls back to the template with a caveat when the entry has no captured prompt', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentCard
        agent="validator"
        label="Validator"
        state={DONE}
        variant="default"
        auditEntry={entryWithoutPrompt()}
      />,
    )
    await user.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByText('TEMPLATE-SYSTEM')).toBeInTheDocument())
    expect(screen.getByText(/pre-dates the audit-prompt-capture/i)).toBeInTheDocument()
  })

  it('renders the response from the audit entry output when present', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentCard
        agent="validator"
        label="Validator"
        state={DONE}
        variant="default"
        auditEntry={entryWithPrompt()}
      />,
    )
    await user.click(screen.getByRole('button'))
    expect(screen.getByText(/covered/)).toBeInTheDocument()
    expect(screen.queryByText(/waiting for this agent/i)).not.toBeInTheDocument()
  })

  it('shows the waiting state when no entry exists and the agent is not done', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" state={RUNNING} variant="default" />,
    )
    await user.click(screen.getByRole('button'))
    expect(await screen.findByText(/waiting for this agent/i)).toBeInTheDocument()
  })

  it('shows an audit-integrity error when no entry exists but the agent is done', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" state={DONE} variant="default" />,
    )
    await user.click(screen.getByRole('button'))
    expect(
      await screen.findByText(/audit entry not found for this completed agent/i),
    ).toBeInTheDocument()
  })
})

describe('AgentCard running state', () => {
  afterEach(() => vi.useRealTimers())

  it('shows the description and expected duration while running', () => {
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" state={RUNNING} variant="default" />,
    )
    expect(screen.getByText(/retrieving policy clauses/i)).toBeInTheDocument()
    expect(screen.getByText(/~9s/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('advances the progress bar as time passes', () => {
    vi.useFakeTimers()
    renderWithProviders(
      <AgentCard agent="guardrail" label="Guardrail" state={RUNNING} variant="default" />,
    )
    const before = Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))
    act(() => vi.advanceTimersByTime(1000)) // 1s of a 5s expected → ~20%
    const after = Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))
    expect(after).toBeGreaterThan(before)
  })

  it('shows no running bar once the agent is done', () => {
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" state={DONE} variant="default" />,
    )
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByText('Validator')).toBeInTheDocument()
  })
})

// Phase 10 (O2): the Guardrail card shows the model's refused citation objections
// without expanding, so the demo talking point is visible on the run page.
describe('AgentCard refused objections', () => {
  function guardrailEntry(discarded: unknown): AuditEntry {
    return {
      audit_id: 74,
      agent: 'guardrail',
      step: 'output_check',
      created_at: '2026-10-30T17:30:33Z',
      chain_hash: '7f7883d7e5e7',
      payload: {
        output: { passed: true, flags: [], summary: 'No additional issues found.' },
        llm_flags_counted: [],
        llm_flags_discarded: discarded,
      },
    }
  }

  it('lists each refused objection with its quote and reason', () => {
    renderWithProviders(
      <AgentCard
        agent="guardrail"
        label="Guardrail"
        state={DONE}
        variant="default"
        auditEntry={guardrailEntry([
          {
            kind: 'hallucinated_citation',
            detail: 'references a provision for inventory valuation',
            quote: 'inventory valuation and depreciation',
            reason: 'quote_not_a_provision',
          },
        ])}
      />,
    )
    const line = screen.getByTestId('refused-objections')
    expect(line).toHaveTextContent('Refused objections (1)')
    // The reason in words (Prompt 29); the code stays in the audit trail.
    expect(line).toHaveTextContent(
      '“inventory valuation and depreciation” — those words do not name a policy provision',
    )
    expect(line).not.toHaveTextContent('quote_not_a_provision')
    // The ⓘ beside the heading explains the line in Dermot's words (12 November 2026).
    fireEvent.focus(within(line).getByRole('button', { name: 'About refused objections' }))
    expect(screen.getByRole('tooltip')).toHaveTextContent(tooltips.refusedObjections)
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      'The Guardrail’s model said these words cite policy wording that is not in the policy.',
    )
  })

  it('shows nothing when the list is empty or absent', () => {
    renderWithProviders(
      <AgentCard
        agent="guardrail"
        label="Guardrail"
        state={DONE}
        variant="default"
        auditEntry={guardrailEntry([])}
      />,
    )
    expect(screen.queryByTestId('refused-objections')).not.toBeInTheDocument()
  })
})

// Prompt 27: the Validator card lists the retrieved passages, each linked to the
// Policy page, with the cited ones marked.
describe('AgentCard retrieved passages', () => {
  const ID_A = '11111111-1111-4111-8111-111111111111'
  const ID_B = '22222222-2222-4222-8222-222222222222'

  function validatorEntry(payload: Record<string, unknown>): AuditEntry {
    return {
      audit_id: 2,
      agent: 'validator',
      step: 'coverage_check',
      created_at: '2026-10-30T17:30:20Z',
      chain_hash: 'abc',
      payload,
    }
  }

  it('links each retrieved passage and marks the cited one', () => {
    renderWithProviders(
      <AgentCard
        agent="validator"
        label="Validator"
        state={DONE}
        variant="default"
        auditEntry={validatorEntry({
          retrieval: {
            top_k: 2,
            chunks: [
              {
                chunk_id: ID_A,
                section: 'Named Perils Covered',
                similarity: 0.7,
                content_excerpt: 'x',
              },
              { chunk_id: ID_B, section: 'Exclusions', similarity: 0.6, content_excerpt: 'y' },
            ],
          },
          verdict: {
            covered: true,
            cited_chunks: [{ chunk_id: ID_A, section: 'Named Perils Covered' }],
          },
        })}
      />,
    )
    const line = screen.getByTestId('validator-passages')
    expect(line).toHaveTextContent('Passages: Named Perils Covered (cited) · Exclusions')
    expect(within(line).getByRole('link', { name: 'Named Perils Covered' })).toHaveAttribute(
      'href',
      `/policy#${ID_A}`,
    )
    expect(within(line).getByRole('link', { name: 'Exclusions' })).toHaveAttribute(
      'href',
      `/policy#${ID_B}`,
    )
  })

  it('shows nothing when the entry has no retrieval block', () => {
    renderWithProviders(
      <AgentCard
        agent="validator"
        label="Validator"
        state={DONE}
        variant="default"
        auditEntry={validatorEntry({ verdict: { covered: false } })}
      />,
    )
    expect(screen.queryByTestId('validator-passages')).not.toBeInTheDocument()
  })
})

// Prompt 29: the top line is the derived sentence, the duration reads in seconds,
// and a state can carry a line beneath (an exception's message, a finding's detail).
describe('AgentCard derived state', () => {
  function card(state: CardState) {
    renderWithProviders(
      <AgentCard agent="adjuster" label="Adjuster" state={state} variant="default" />,
    )
  }

  it('shows the sentence and the duration in seconds to one decimal', () => {
    card({ status: 'done', summary: 'Recommends $82,500 (85% confident)', durationMs: 3421 })
    expect(screen.getByText('Recommends $82,500 (85% confident)')).toBeInTheDocument()
    expect(screen.getByText('3.4 s')).toBeInTheDocument()
    expect(screen.getByText('3.4 s')).not.toHaveAttribute('title')
  })

  it('says when the duration came from the audit trail', () => {
    card({ status: 'done', summary: 'Done', durationMs: 2600, durationFromAudit: true })
    expect(screen.getByText('2.6 s')).toHaveAttribute('title', 'from the audit trail')
  })

  it('shows a failed agent with its reason and the message beneath', () => {
    card({
      status: 'failed',
      summary: 'Failed: the Adjuster has no market range for the claim type Smoke damage',
      detail: "MarketDataTable.lookup: unknown claim_type 'smoke_damage'",
    })
    expect(screen.getByText(/^Failed: the Adjuster has no market range/)).toBeInTheDocument()
    expect(screen.getByTestId('card-detail')).toHaveTextContent("unknown claim_type 'smoke_damage'")
    expect(screen.getByText('✗')).toBeInTheDocument()
  })

  it('shows an agent that was not run, and a queued one as Waiting', () => {
    card({ status: 'not_run', summary: 'Not run: the run stopped at the Validator' })
    expect(screen.getByText('Not run: the run stopped at the Validator')).toBeInTheDocument()
    expect(screen.getByText('∅')).toBeInTheDocument()
    expect(screen.queryByTestId('card-detail')).not.toBeInTheDocument()
  })

  it('marks the Guardrail’s own failed verdict with ⚠ and the finding’s detail beneath', () => {
    renderWithProviders(
      <AgentCard
        agent="guardrail"
        label="Guardrail"
        variant="default"
        state={{
          status: 'escalated',
          summary: 'Failed: cited policy wording the policy does not contain',
          detail: "endorsement 'Coastal Surge Rider' not in retrieved chunks",
        }}
      />,
    )
    expect(screen.getByText('⚠')).toBeInTheDocument()
    expect(screen.getByTestId('card-detail')).toHaveTextContent('Coastal Surge Rider')
  })
})
