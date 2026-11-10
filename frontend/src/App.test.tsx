import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { renderWithProviders, stubFetch } from './test/utils'

describe('App routing', () => {
  beforeEach(() => stubFetch([['/api/claims', []]]))
  afterEach(() => vi.unstubAllGlobals())

  it('renders the nav and the claims landing page', async () => {
    renderWithProviders(<App />)
    expect(screen.getByRole('link', { name: /agentic claims poc/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Audit' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Agents' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Integrations' })).toHaveAttribute(
      'href',
      '/integrations',
    )
    expect(screen.getByRole('link', { name: 'Guide' })).toHaveAttribute('href', '/guide')
    expect(screen.getByRole('button', { name: /submit claim/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/no claims yet/i)).toBeInTheDocument())
  })

  it('keeps the navigation stuck to the top of the window', () => {
    renderWithProviders(<App />)
    const nav = screen.getByRole('navigation')
    expect(nav.className).toMatch(/\bsticky\b/)
    expect(nav.className).toMatch(/\btop-0\b/)
    expect(screen.getByRole('link', { name: 'Policy' })).toHaveAttribute('href', '/policy')
  })

  it('deep-links to the audit viewer', () => {
    renderWithProviders(<App />, { route: '/audit' })
    expect(screen.getByLabelText('Correlation id')).toBeInTheDocument()
  })

  it('deep-links to the agent test bench', () => {
    renderWithProviders(<App />, { route: '/agents' })
    expect(screen.getByRole('button', { name: /run doc-parser/i })).toBeInTheDocument()
  })

  it('deep-links to a comparison view and renders the diff', async () => {
    stubFetch([
      [
        '/api/runs/compare/',
        {
          run_a: {},
          run_b: {},
          diff: {
            settlement_changed: true,
            settlement_a: '85000.00',
            settlement_b: '850000.00',
            escalation_changed: true,
            escalate_a: false,
            escalate_b: true,
            fired_rules_added: ['settlement_over_ceiling'],
            fired_rules_removed: [],
            guardrail_changed: false,
            guardrail_passed_a: true,
            guardrail_passed_b: true,
          },
        },
      ],
    ])
    renderWithProviders(<App />, { route: '/claims/c1/compare/aaa/bbb' })
    await waitFor(() => expect(screen.getByLabelText('Comparison diff')).toBeInTheDocument())
    expect(screen.getByText('850000.00')).toBeInTheDocument()
    expect(screen.getByText(/settlement_over_ceiling/)).toBeInTheDocument()
  })
})
