import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, stubFetch } from '../test/utils'
import { AgentCard } from './AgentCard'

const PROMPT = {
  agent: 'validator',
  variant: 'default',
  system: 'SYSTEM-PROMPT-TEXT',
  user: 'USER-PROMPT-TEXT',
}

describe('AgentCard', () => {
  beforeEach(() => stubFetch([['/api/agents/validator/prompt', PROMPT]]))
  afterEach(() => vi.unstubAllGlobals())

  it('renders collapsed with the label and status', () => {
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" status="done" variant="default" />,
    )
    expect(screen.getByText('Validator')).toBeInTheDocument()
    expect(screen.queryByText('SYSTEM-PROMPT-TEXT')).not.toBeInTheDocument()
  })

  it('lazily fetches the prompt and shows the response on expand', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentCard
        agent="validator"
        label="Validator"
        status="done"
        variant="default"
        responsePayload={{ covered: true }}
      />,
    )
    await user.click(screen.getByRole('button'))
    await waitFor(() => expect(screen.getByText('SYSTEM-PROMPT-TEXT')).toBeInTheDocument())
    expect(screen.getByText('USER-PROMPT-TEXT')).toBeInTheDocument()
    expect(screen.getByText(/covered/)).toBeInTheDocument()
  })

  it('shows a waiting state when no response payload is present', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentCard agent="validator" label="Validator" status="running" variant="default" />,
    )
    await user.click(screen.getByRole('button'))
    expect(await screen.findByText(/waiting for this agent/i)).toBeInTheDocument()
  })
})
