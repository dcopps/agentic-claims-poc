import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, stubFetch } from '../test/utils'
import { AgentTestPanel } from './AgentTestPanel'

describe('AgentTestPanel', () => {
  beforeEach(() =>
    stubFetch([
      ['/api/agents/test/doc-parser', { output: { claim_type: 'water_damage' }, meta: { model: 'haiku' } }],
    ]),
  )
  afterEach(() => vi.unstubAllGlobals())

  it('runs the agent and renders the typed result', async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentTestPanel agent="doc-parser" label="Doc-Parser" sample='{"narrative":"Burst pipe."}' />,
    )
    await user.click(screen.getByRole('button', { name: /run doc-parser/i }))
    await waitFor(() => expect(screen.getByText(/water_damage/)).toBeInTheDocument())
    expect(screen.getByText(/haiku/)).toBeInTheDocument()
  })

  it('surfaces a JSON parse error without calling the API', async () => {
    const fetchMock = stubFetch([['/api/agents/test/doc-parser', {}]])
    const user = userEvent.setup()
    renderWithProviders(
      <AgentTestPanel agent="doc-parser" label="Doc-Parser" sample="not json" />,
    )
    await user.click(screen.getByRole('button', { name: /run doc-parser/i }))
    // The error paragraph appears; the API is never called for invalid JSON.
    expect(await screen.findByText(/json/i, { selector: 'p' })).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
