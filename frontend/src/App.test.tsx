import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

describe('App', () => {
  beforeEach(() => {
    // Default: backend reachable. Tests that need the failure path stub fetch
    // themselves.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('', { status: 200 }))),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the heading', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /agentic claims poc/i }),
    ).toBeInTheDocument()
  })

  it('shows backend status as ok when /health returns 200', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByTestId('backend-status')).toHaveTextContent(
        /backend:\s*ok/i,
      )
    })
  })
})
