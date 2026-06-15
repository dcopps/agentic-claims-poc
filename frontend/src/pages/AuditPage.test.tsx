import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, stubFetch } from '../test/utils'
import { AuditPage } from './AuditPage'

const ENTRIES = [
  {
    audit_id: 1,
    agent: 'orchestrator',
    step: 'pipeline_started',
    created_at: '2026-04-03T10:00:00Z',
    payload: { variant: 'default' },
    chain_hash: 'abcdef1234567890',
  },
]

describe('AuditPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists entries and verifies the whole ledger (ok)', async () => {
    // verify route listed first so it wins over the generic /api/audit substring.
    stubFetch([
      ['/api/audit/verify/', { ok: true, rows_checked: 5, first_break: null }],
      ['/api/audit', ENTRIES],
    ])
    const user = userEvent.setup()
    renderWithProviders(<AuditPage />, { route: '/audit?correlation_id=cid-1' })
    await waitFor(() => expect(screen.getByText('pipeline_started')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /verify chain/i }))
    await waitFor(() => expect(screen.getByText(/chain verified/i)).toBeInTheDocument())
  })

  it('shows the first break when the chain is broken', async () => {
    stubFetch([
      [
        '/api/audit/verify/',
        { ok: false, rows_checked: 2, first_break: { audit_id: 2, kind: 'row_hash_mismatch', expected: 'a', actual: 'b' } },
      ],
      ['/api/audit', ENTRIES],
    ])
    const user = userEvent.setup()
    renderWithProviders(<AuditPage />, { route: '/audit?correlation_id=cid-1' })
    await user.click(screen.getByRole('button', { name: /verify chain/i }))
    await waitFor(() =>
      expect(screen.getByText(/chain break at audit_id 2/i)).toBeInTheDocument(),
    )
  })
})
