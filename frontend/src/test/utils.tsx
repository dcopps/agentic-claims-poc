import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderResult } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi, type Mock } from 'vitest'

// Render a component inside the providers the app uses: a fresh QueryClient with
// retries off (tests assert on first response) and a MemoryRouter (so routing
// hooks work and deep-links can be exercised via `route`).
export function renderWithProviders(
  ui: ReactElement,
  { route = '/', client }: { route?: string; client?: QueryClient } = {},
): RenderResult {
  const queryClient =
    client ??
    new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

// A fetch stub that routes by URL substring → JSON body. Pass an array of
// [match, body] pairs; the first match wins. Unmatched URLs resolve to 404.
// Returns the mock so tests can assert on calls.
export function stubFetch(routes: Array<[string, unknown]>): Mock {
  const fn = vi.fn((input: unknown) => {
    // fetch may be called with a string, a URL, or a Request — coerce to a URL
    // string so substring matching is robust.
    const url =
      typeof input === 'string' ? input : ((input as { url?: string })?.url ?? '')
    for (const [match, body] of routes) {
      if (url.includes(match)) {
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        )
      }
    }
    return Promise.resolve(new Response('{"detail":"not found"}', { status: 404 }))
  })
  ;(globalThis as unknown as { fetch: unknown }).fetch = fn
  return fn
}
