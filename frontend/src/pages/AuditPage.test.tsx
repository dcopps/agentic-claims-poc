import { cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RunListItem } from '../api/types'
import { tooltips } from '../copy/tooltips'
import { CLAIM, decisionRows, settledRows } from '../test/runFixtures'
import { renderWithProviders, stubFetch } from '../test/utils'
import { AuditPage } from './AuditPage'

const CID = 'cid-1'
const FULL_ID = 'f23ea4dc-2292-480e-8b4b-344eb1464b0a'

const RECENT: RunListItem[] = [
  {
    correlation_id: CID,
    claim_id: 'c1',
    claim_number: 'CLM-2026-9BB57A86',
    claimant_name: 'Harborline Logistics Ltd',
    variant: 'default',
    status: 'settled',
    started_at: '2026-11-15T15:09:03Z',
    completed_at: '2026-11-15T15:09:12Z',
    escalate: false,
    human_decision: null,
  },
  {
    correlation_id: 'cid-2',
    claim_id: 'c2',
    claim_number: 'CLM-2026-5855FB8E',
    claimant_name: 'Northwood Manufacturing Inc',
    variant: 'v2_strict_validator',
    status: 'awaiting_human',
    started_at: '2026-11-15T15:04:52Z',
    completed_at: '2026-11-15T15:05:02Z',
    escalate: true,
    human_decision: 'rejected',
  },
]

type Routes = Array<[string, unknown]>

// The verify and prefix routes come first: stubFetch matches the first substring.
function stubAudit(extra: Routes = [], rows = settledRows()) {
  return stubFetch([
    ...extra,
    ['/api/audit/verify/', { ok: true, rows_checked: 5, first_break: null }],
    [`/api/audit?correlation_id=${CID}`, rows],
    ['/api/claims/c1', CLAIM],
    ['/api/runs', RECENT],
  ])
}

const ROUTE = `/audit?correlation_id=${CID}`
const prefixCalls = (fetchMock: ReturnType<typeof stubFetch>) =>
  fetchMock.mock.calls.filter((call) => String(call[0]).includes('/api/runs?prefix=')).length

async function typeAndLoad(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.clear(screen.getByLabelText('Run id'))
  await user.type(screen.getByLabelText('Run id'), text)
  await user.click(screen.getByRole('button', { name: 'Load' }))
}

describe('AuditPage: finding a run', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('asks for a run id in words and lists the recent runs by their claims', async () => {
    stubAudit()
    renderWithProviders(<AuditPage />, { route: '/audit' })
    expect(screen.getByLabelText('Run id')).toBeInTheDocument()
    expect(screen.getByText('Paste a run id, or its first eight characters.')).toBeInTheDocument()
    expect(screen.getByTestId('choose-run')).toHaveTextContent(
      'Enter a run id, or choose a run above, to see its records.',
    )
    expect(screen.queryByText('Correlation id')).not.toBeInTheDocument()
    const list = await screen.findByRole('list', { name: 'Recent runs' })
    const links = within(list).getAllByRole('link')
    expect(links[0]).toHaveTextContent(
      /^Harborline Logistics Ltd · CLM-2026-9BB57A86 · Standard run · .+ · Settled$/,
    )
    expect(links[0]).toHaveAttribute('href', ROUTE)
    expect(links[1]).toHaveTextContent(
      /Northwood Manufacturing Inc · CLM-2026-5855FB8E · Strict Validator run · .+ · Rejected$/,
    )
  })

  it('loads a run chosen from the recent list', async () => {
    const user = userEvent.setup()
    stubAudit()
    renderWithProviders(<AuditPage />, { route: '/audit' })
    await user.click((await screen.findAllByRole('link', { name: /Harborline/ }))[0])
    expect(await screen.findByRole('table', { name: 'Records' })).toBeInTheDocument()
    expect(screen.getByLabelText('Run id')).toHaveValue(CID)
  })

  it('refuses fewer than eight characters on the page, with no request', async () => {
    const user = userEvent.setup()
    const fetchMock = stubAudit()
    renderWithProviders(<AuditPage />, { route: '/audit' })
    await typeAndLoad(user, '2bd0')
    expect(screen.getByTestId('finder-message')).toHaveTextContent(
      'Give at least the first eight characters of the run id.',
    )
    await typeAndLoad(user, 'run 2bd08a61')
    expect(screen.getByTestId('finder-message')).toHaveTextContent(
      'A run id is made of the characters 0–9, a–f and hyphens.',
    )
    expect(prefixCalls(fetchMock)).toBe(0)
  })

  it('resolves a short id through the backend: one run loads, several or none say so', async () => {
    const user = userEvent.setup()
    const fetchMock = stubAudit([
      ['/api/runs?prefix=f23ea4dc', [RECENT[0]]],
      ['/api/runs?prefix=aaaaaaaa', RECENT],
      ['/api/runs?prefix=00000000', []],
    ])
    renderWithProviders(<AuditPage />, { route: '/audit' })
    await typeAndLoad(user, 'aaaaaaaa')
    await waitFor(() =>
      expect(screen.getByTestId('finder-message')).toHaveTextContent(
        '2 runs start with aaaaaaaa; give more of the id.',
      ),
    )
    await typeAndLoad(user, '00000000')
    await waitFor(() =>
      expect(screen.getByTestId('finder-message')).toHaveTextContent(
        'No run starts with 00000000.',
      ),
    )
    await typeAndLoad(user, 'F23EA4DC')
    expect(await screen.findByRole('table', { name: 'Records' })).toBeInTheDocument()
    expect(prefixCalls(fetchMock)).toBe(3)
    // The typed id is lower-cased before it is sent, and the lookup asks for every match.
    const lookups = fetchMock.mock.calls
      .map((call) => String(call[0]))
      .filter((u) => u.includes('prefix='))
    expect(lookups.at(-1)).toContain('/api/runs?prefix=f23ea4dc&limit=100')
  })

  it('loads a whole id as typed, without a lookup', async () => {
    const user = userEvent.setup()
    const fetchMock = stubAudit()
    renderWithProviders(<AuditPage />, { route: '/audit' })
    await typeAndLoad(user, FULL_ID)
    expect(await screen.findByTestId('records-state')).toHaveTextContent('No run has this id.')
    expect(prefixCalls(fetchMock)).toBe(0)
  })
})

describe('AuditPage: a run’s records', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('names the claim and the run, and reads every record as a sentence', async () => {
    stubAudit()
    renderWithProviders(<AuditPage />, { route: ROUTE })
    expect(await screen.findByTestId('run-claim')).toHaveTextContent(
      'Harborline Logistics Ltd · Water damage · $85,000 · claim CLM-2026-9BB57A86',
    )
    expect(screen.getByRole('link', { name: 'Harborline Logistics Ltd' })).toHaveAttribute(
      'href',
      '/claims/c1',
    )
    const runLine = screen.getByTestId('audit-run-line')
    expect(runLine).toHaveTextContent(
      /^Standard run · started .+ · Settled at \$82,500 · Open the run page$/,
    )
    expect(screen.getByRole('link', { name: 'Open the run page' })).toHaveAttribute(
      'href',
      `/claims/c1/runs/${CID}`,
    )
    const table = screen.getByRole('table', { name: 'Records' })
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((th) => th.textContent),
    ).toEqual(['When', 'Who', 'What happened', 'Recordⓘ'])
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(7)
    expect(rows.map((row) => within(row).getAllByRole('cell')[1].textContent)).toEqual([
      'Orchestrator',
      'Doc-Parser',
      'Validator',
      'Adjuster',
      'Guardrail',
      'Orchestrator',
      'Orchestrator',
    ])
    expect(rows.map((row) => within(row).getByRole('button').textContent)).toEqual([
      'Run started: Standard run',
      'Summarised the claim (Water damage)',
      'Covered (92% confident)',
      'Recommends $82,500 (85% confident)',
      'Passed',
      'No rule fired; the claim settles',
      'Settled at $82,500',
    ])
    expect(within(rows[2]).getAllByRole('cell')[3]).toHaveTextContent('#3 · hash-3')
    expect(within(rows[2]).getAllByRole('cell')[0]).toHaveTextContent(/\d\d:\d\d:\d\d/)
    expect(screen.queryByText('pipeline_started')).not.toBeInTheDocument()
    expect(screen.queryByText('doc_parser')).not.toBeInTheDocument()
  })

  it('says what a person decided on the run line', async () => {
    stubAudit([], decisionRows('rejected'))
    renderWithProviders(<AuditPage />, { route: ROUTE })
    expect(await screen.findByTestId('audit-run-line')).toHaveTextContent(
      'Rejected after human review',
    )
    expect(screen.getByRole('button', { name: 'Open record 8' })).toHaveTextContent(
      'Rejected by Dermot',
    )
  })

  it('explains the Record column on its ⓘ in the Guide’s words', async () => {
    const user = userEvent.setup()
    stubAudit()
    renderWithProviders(<AuditPage />, { route: ROUTE })
    await screen.findByRole('table', { name: 'Records' })
    await user.hover(screen.getByRole('button', { name: 'About records and hashes' }))
    expect(screen.getByRole('tooltip')).toHaveTextContent(tooltips.chainHash)
  })

  it('verifies the whole ledger and answers in a sentence, ok or broken', async () => {
    const user = userEvent.setup()
    stubAudit()
    renderWithProviders(<AuditPage />, { route: ROUTE })
    await screen.findByRole('table', { name: 'Records' })
    await user.click(screen.getByRole('button', { name: 'Verify chain' }))
    expect(await screen.findByTestId('verify-result')).toHaveTextContent(
      'Checked all 5 records in the ledger, this run’s included: every hash matches.',
    )
    vi.unstubAllGlobals()
    stubAudit([
      [
        '/api/audit/verify/',
        {
          ok: false,
          rows_checked: 2,
          first_break: { audit_id: 2, kind: 'chain_hash_mismatch', expected: 'a', actual: 'b' },
        },
      ],
    ])
    await user.click(screen.getByRole('button', { name: 'Verify chain' }))
    await waitFor(() =>
      expect(screen.getByTestId('verify-result')).toHaveTextContent(
        'A break at record 2: the link to the record before it does not match.',
      ),
    )
    expect(screen.queryByText(/whole ledger/)).not.toBeInTheDocument()
  })

  it('says so for an unknown id and for a failed load', async () => {
    stubFetch([['/api/runs', RECENT]])
    renderWithProviders(<AuditPage />, { route: ROUTE })
    expect(await screen.findByTestId('records-state')).toHaveTextContent('No run has this id.')
    cleanup()
    vi.unstubAllGlobals()
    ;(globalThis as unknown as { fetch: unknown }).fetch = vi.fn(() =>
      Promise.reject(new Error('network down')),
    )
    renderWithProviders(<AuditPage />, { route: ROUTE })
    expect(await screen.findByTestId('records-state')).toHaveTextContent(
      'The records could not be loaded.',
    )
  })

  it('opens a record from its row and returns focus to the row on closing', async () => {
    const user = userEvent.setup()
    stubAudit()
    renderWithProviders(<AuditPage />, { route: ROUTE })
    await screen.findByRole('table', { name: 'Records' })
    const rowButton = screen.getByRole('button', { name: 'Open record 3' })
    await user.click(rowButton)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAccessibleName(
      /^Validator · coverage check · .+ · record 3 in the ledger$/,
    )
    expect(within(dialog).getByText('confidence:')).toBeInTheDocument()
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(rowButton).toHaveFocus()
  })
})
