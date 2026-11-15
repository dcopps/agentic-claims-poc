import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { renderWithProviders as render } from '../test/utils'
import { RecordTree } from './RecordTree'

const LONG = 'The loss involves a single ruptured supply line. '.repeat(8).trim() // > 240 chars

const RECORD = {
  output: { confidence: 0.85, reasoning: LONG, nested: { deep: true } },
  flags: [],
  demo_fixture: false,
  error: null,
}

// Prompt 32: the stored record as a tree (plan §3, D3).
describe('RecordTree', () => {
  it('opens the record’s keys and the level beneath, and closes deeper levels with a summary', async () => {
    const user = userEvent.setup()
    render(<RecordTree value={RECORD} />)
    // Depth 1 is open: the Adjuster's confidence reads at once, coloured as a number.
    expect(screen.getByText('confidence:')).toBeInTheDocument()
    expect(screen.getByText('0.85')).toHaveClass('text-blue-700')
    // Depth 2 is closed, with how much it holds.
    const nested = screen.getByRole('button', { name: /nested:/ })
    expect(nested).toHaveAttribute('aria-expanded', 'false')
    expect(nested).toHaveTextContent('{1 key}')
    expect(screen.queryByText('deep:')).not.toBeInTheDocument()
    await user.click(nested)
    expect(nested).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('deep:')).toBeInTheDocument()
    expect(screen.getByText('true')).toHaveClass('text-purple-700')
  })

  it('shows an empty list, a false and a null each in its own way', () => {
    render(<RecordTree value={RECORD} />)
    expect(screen.getByRole('button', { name: /flags:/ })).toHaveTextContent('[empty]')
    expect(screen.getByText('false')).toHaveClass('text-purple-700')
    expect(screen.getByText('null')).toHaveClass('italic')
  })

  // Dermot, 15 November: a passage's id opens that passage on the Policy page.
  it('links a chunk_id to its passage on the Policy page and leaves other ids as text', () => {
    const ID = '0cd714d2-5f6f-462c-b668-bde76d082f6f'
    // At a depth that starts open; deeper ids are the same link once their node is opened.
    render(
      <RecordTree value={{ cited: { chunk_id: ID, section: 'Exclusions' }, claim_id: 'c1' }} />,
    )
    expect(screen.getByRole('link', { name: ID })).toHaveAttribute('href', `/policy#${ID}`)
    expect(screen.queryByRole('link', { name: 'c1' })).not.toBeInTheDocument()
    expect(screen.getByText('“c1”')).toBeInTheDocument()
  })

  it('folds a long text behind Show all and wraps it', async () => {
    const user = userEvent.setup()
    render(<RecordTree value={RECORD} />)
    const tree = screen.getByTestId('record-tree')
    expect(tree).not.toHaveTextContent(LONG)
    expect(tree).toHaveTextContent(`${LONG.slice(0, 240)}…`)
    const showAll = within(tree).getByRole('button', { name: 'Show all' })
    await user.click(showAll)
    expect(tree).toHaveTextContent(LONG)
    expect(screen.getByText(`“${LONG}”`)).toHaveClass('whitespace-pre-wrap', 'break-words')
    await user.click(within(tree).getByRole('button', { name: 'Show less' }))
    expect(tree).not.toHaveTextContent(LONG)
  })
})
