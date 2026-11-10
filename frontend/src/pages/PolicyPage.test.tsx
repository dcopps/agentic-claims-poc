import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PolicyIndex } from '../api/types'
import { policyCopy } from '../copy/policy'
import { renderWithProviders, stubFetch } from '../test/utils'
import { PolicyPage } from './PolicyPage'

const ID_A1 = '11111111-1111-4111-8111-111111111111'
const ID_B1 = '22222222-2222-4222-8222-222222222222'
const ID_B2 = '33333333-3333-4333-8333-333333333333'

const INDEX: PolicyIndex = {
  source: 'backend/data/sample_policy.txt',
  embedding_model: 'BAAI/bge-small-en-v1.5',
  passage_count: 3,
  sections: [
    {
      name: 'Definitions',
      passages: [
        {
          chunk_id: ID_A1,
          section: 'Definitions',
          chunk_index: 0,
          position: 1,
          section_size: 1,
          text: 'Insured means the named insured.',
          token_count: 8,
        },
      ],
    },
    {
      name: 'Exclusions',
      passages: [
        {
          chunk_id: ID_B1,
          section: 'Exclusions',
          chunk_index: 1,
          position: 1,
          section_size: 2,
          text: 'We do not cover wear and tear.',
          token_count: 9,
        },
        {
          chunk_id: ID_B2,
          section: 'Exclusions',
          chunk_index: 2,
          position: 2,
          section_size: 2,
          text: 'We do not cover flood.',
          token_count: 7,
        },
      ],
    },
  ],
}

const EMPTY: PolicyIndex = {
  source: 'backend/data/sample_policy.txt',
  embedding_model: null,
  passage_count: 0,
  sections: [],
}

describe('PolicyPage', () => {
  // jsdom has no scrollIntoView; the page optional-calls it, the test observes it.
  const scrollIntoView = vi.fn()
  beforeEach(() => {
    Element.prototype.scrollIntoView = scrollIntoView
    scrollIntoView.mockClear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders the sections, the passages with their position labels and the count line', async () => {
    stubFetch([['/api/policy', INDEX]])
    renderWithProviders(<PolicyPage />, { route: '/policy' })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Exclusions' })).toBeVisible())
    expect(screen.getByRole('heading', { name: 'Definitions' })).toBeInTheDocument()
    expect(screen.getByText('We do not cover flood.')).toBeInTheDocument()
    expect(screen.getByText('Exclusions, passage 2 of 2')).toBeInTheDocument()
    expect(screen.getByTestId('policy-count')).toHaveTextContent(
      '3 passages from backend/data/sample_policy.txt, embedded with BAAI/bge-small-en-v1.5.',
    )
    // No passage is highlighted without an anchor, and nothing was scrolled.
    expect(document.querySelector('[aria-current="true"]')).toBeNull()
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it('shows the empty state when nothing is indexed', async () => {
    stubFetch([['/api/policy', EMPTY]])
    renderWithProviders(<PolicyPage />, { route: '/policy' })
    await waitFor(() => expect(screen.getByTestId('policy-empty')).toBeInTheDocument())
    expect(screen.getByTestId('policy-empty')).toHaveTextContent(policyCopy.empty)
    expect(screen.queryByTestId('policy-count')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Exclusions' })).not.toBeInTheDocument()
  })

  it('highlights and scrolls to the passage named by the URL hash', async () => {
    stubFetch([['/api/policy', INDEX]])
    renderWithProviders(<PolicyPage />, { route: `/policy#${ID_B2}` })
    await waitFor(() => expect(document.getElementById(ID_B2)).not.toBeNull())
    const current = document.querySelectorAll('[aria-current="true"]')
    expect(current).toHaveLength(1)
    expect(current[0].id).toBe(ID_B2)
    expect(
      within(current[0] as HTMLElement).getByText('We do not cover flood.'),
    ).toBeInTheDocument()
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))
    // block 'start' plus the article's scroll margin rests it below the sticky menu.
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'start' })
    expect(current[0].className).toMatch(/\bscroll-mt-\d+\b/)
    expect(screen.queryByTestId('policy-missing-anchor')).not.toBeInTheDocument()
  })

  it('shows each passage’s chunk id in short with a copy button for the full id', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    stubFetch([['/api/policy', INDEX]])
    renderWithProviders(<PolicyPage />, { route: '/policy' })
    await waitFor(() => expect(document.getElementById(ID_B2)).not.toBeNull())
    const block = document.getElementById(ID_B2) as HTMLElement
    expect(within(block).getByText(`Chunk ${ID_B2.slice(0, 8)}`)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Copy id' })).toHaveLength(3)
    fireEvent.click(within(block).getByRole('button', { name: 'Copy id' }))
    expect(writeText).toHaveBeenCalledWith(ID_B2)
    // The clicked button acknowledges, as the run id's copy button does.
    expect(within(block).getByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('says so when the URL names a chunk id that is not in the index', async () => {
    stubFetch([['/api/policy', INDEX]])
    renderWithProviders(<PolicyPage />, {
      route: '/policy#99999999-9999-4999-8999-999999999999',
    })
    await waitFor(() => expect(screen.getByTestId('policy-missing-anchor')).toBeInTheDocument())
    expect(screen.getByTestId('policy-missing-anchor')).toHaveTextContent(policyCopy.missingAnchor)
    // The sections still render; nothing is highlighted or scrolled.
    expect(screen.getByRole('heading', { name: 'Exclusions' })).toBeInTheDocument()
    expect(document.querySelector('[aria-current="true"]')).toBeNull()
    expect(scrollIntoView).not.toHaveBeenCalled()
  })

  it('reports a failed load in plain words', async () => {
    stubFetch([]) // every URL 404s
    renderWithProviders(<PolicyPage />, { route: '/policy' })
    await waitFor(() => expect(screen.getByText(policyCopy.loadFailed)).toBeInTheDocument())
  })
})
