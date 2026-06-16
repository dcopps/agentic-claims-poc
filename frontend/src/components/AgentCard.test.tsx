import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuditEntry } from '../api/types'
import { renderWithProviders, stubFetch } from '../test/utils'
import { AgentCard } from './AgentCard'

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
      <AgentCard agent="validator" label="Validator" status="done" variant="default" />,
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
        status="done"
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
        status="done"
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
        status="done"
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
      <AgentCard agent="validator" label="Validator" status="running" variant="default" />,
    )
    await user.click(screen.getByRole('button'))
    expect(await screen.findByText(/waiting for this agent/i)).toBeInTheDocument()
  })

  it('shows an audit-integrity error when no entry exists but the agent is done', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" status="done" variant="default" />,
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
      <AgentCard agent="validator" label="Validator" status="running" variant="default" />,
    )
    expect(screen.getByText(/retrieving policy clauses/i)).toBeInTheDocument()
    expect(screen.getByText(/~9s/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('advances the progress bar as time passes', () => {
    vi.useFakeTimers()
    renderWithProviders(
      <AgentCard agent="guardrail" label="Guardrail" status="running" variant="default" />,
    )
    const before = Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))
    act(() => vi.advanceTimersByTime(1000)) // 1s of a 5s expected → ~20%
    const after = Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))
    expect(after).toBeGreaterThan(before)
  })

  it('shows no running bar once the agent is done', () => {
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" status="done" variant="default" />,
    )
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByText('Validator')).toBeInTheDocument()
  })
})
