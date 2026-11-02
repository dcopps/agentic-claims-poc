import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { McpCatalogue, ToolCallRecord } from '../api/types'
import { TOKEN_PLACEHOLDER } from '../copy/integrations'
import { renderWithProviders, stubFetch } from '../test/utils'

// The feed hook opens an EventSource (stubbed in tests); mock it to return a
// controllable record list per test, as the Run Detail tests do for the stream.
const { feedState } = vi.hoisted(() => ({
  feedState: { records: [] as ToolCallRecord[] },
}))
vi.mock('../hooks/useMcpActivity', () => ({
  useMcpActivity: () => feedState.records,
}))

function catalogue(mounted: boolean): McpCatalogue {
  return {
    mounted,
    path: '/mcp',
    tools: [
      {
        name: 'list_claims',
        title: 'List claims',
        description: 'List the claims on record.',
        kind: 'read',
        parameters: {},
      },
      {
        name: 'explain_decision',
        title: 'Explain a decision',
        description: 'Why a run settled or escalated.',
        kind: 'read',
        parameters: {},
      },
      {
        name: 'run_scenario',
        title: 'Run a scripted scenario',
        description: 'Submit one of the three scripted claims and run it.',
        kind: 'action',
        parameters: {},
      },
    ],
    prompts: [
      {
        name: 'audit_this_run',
        title: 'Audit this run',
        description: 'Verify the chain and explain the run.',
        arguments: [{ name: 'correlation_id', required: true }],
      },
    ],
    resources: [
      {
        uri: 'policy://excerpt',
        name: 'policy_excerpt',
        title: 'The policy excerpt',
        description: 'The policy wording the Validator searches.',
        mime_type: 'text/plain',
      },
    ],
  }
}

function record(call_id: number, overrides: Partial<ToolCallRecord> = {}): ToolCallRecord {
  return {
    call_id,
    called_at: '2026-11-02T10:00:00Z',
    tool: 'get_run',
    arguments: {},
    target: { kind: 'run', id: '0cdfa114-dde7-4fbe-971e-7fe3e64f2a97' },
    caller: 'shared-token',
    outcome: 'ok',
    error_class: null,
    latency_ms: 12,
    ...overrides,
  }
}

describe('IntegrationsPage', () => {
  beforeEach(() => {
    feedState.records = []
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders every tool the backend reports, with its kind', async () => {
    stubFetch([['/api/mcp/tools', catalogue(true)]])
    renderWithProviders(<App />, { route: '/integrations' })
    const table = await screen.findByLabelText('MCP tools')
    const rows = within(table).getAllByRole('row').slice(1) // minus the header
    expect(rows).toHaveLength(3)
    expect(within(table).getAllByText('read-only')).toHaveLength(2)
    expect(within(table).getByText('action')).toBeInTheDocument()
    expect(within(table).getByText('explain_decision')).toBeInTheDocument()
    const extras = screen.getByLabelText('MCP prompts and resources')
    expect(within(extras).getByText('audit_this_run')).toBeInTheDocument()
    expect(within(extras).getByText('policy://excerpt')).toBeInTheDocument()
    expect(screen.queryByTestId('not-configured')).not.toBeInTheDocument()
  })

  it('says plainly when the endpoint is not configured', async () => {
    stubFetch([['/api/mcp/tools', catalogue(false)]])
    renderWithProviders(<App />, { route: '/integrations' })
    await waitFor(() =>
      expect(screen.getByTestId('not-configured')).toHaveTextContent(/no shared token is set/),
    )
  })

  it('shows the feed newest first with outcome badges and audit links', async () => {
    stubFetch([['/api/mcp/tools', catalogue(true)]])
    feedState.records = [
      record(2, { tool: 'verify_chain', outcome: 'error', error_class: 'ToolError' }),
      record(1, { tool: 'list_claims', target: null }),
    ]
    renderWithProviders(<App />, { route: '/integrations' })
    const feed = await screen.findByLabelText('MCP activity')
    const rows = within(feed).getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('verify_chain')
    expect(rows[0]).toHaveTextContent('ToolError')
    expect(rows[1]).toHaveTextContent('list_claims')
    expect(within(rows[0]).getByRole('link', { name: /run 0cdfa114/ })).toHaveAttribute(
      'href',
      '/audit?correlation_id=0cdfa114-dde7-4fbe-971e-7fe3e64f2a97',
    )
  })

  it('shows an empty-feed message when nothing has been called', async () => {
    stubFetch([['/api/mcp/tools', catalogue(true)]])
    renderWithProviders(<App />, { route: '/integrations' })
    expect(await screen.findByText('No tool calls yet.')).toBeInTheDocument()
  })

  it('copies the Claude Code command with the placeholder, never a token', async () => {
    stubFetch([['/api/mcp/tools', catalogue(true)]])
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderWithProviders(<App />, { route: '/integrations' })
    fireEvent.click(await screen.findByRole('button', { name: 'Copy command' }))
    const copied = writeText.mock.calls[0][0] as string
    expect(copied).toContain('claude mcp add-json')
    expect(copied).toContain('/mcp')
    expect(copied).toContain(TOKEN_PLACEHOLDER)
  })

  it('links to the Guide', async () => {
    stubFetch([['/api/mcp/tools', catalogue(true)]])
    renderWithProviders(<App />, { route: '/integrations' })
    expect(await screen.findByRole('link', { name: /read the guide/i })).toHaveAttribute(
      'href',
      '/guide',
    )
  })
})
