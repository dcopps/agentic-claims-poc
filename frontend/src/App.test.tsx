import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('App', () => {
  beforeEach(() => {
    // The claims list loads on mount; default to an empty list.
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse([]))))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders the heading and the submission form', async () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /agentic claims poc/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit claim/i })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByText(/no claims yet/i)).toBeInTheDocument(),
    )
  })

  it('switches to the compare view', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: /compare runs/i }))
    expect(screen.getByLabelText('Select a claim')).toBeInTheDocument()
  })
})
