import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AuditEntry } from '../api/types'
import { recordHeader } from '../pages/auditDerivation'
import { decisionRows, guardrailFailureRows, settledRows } from '../test/runFixtures'
import { RecordDialog } from './RecordDialog'

// The Validator's row with the instructions it was sent (Phase 8.3's capture).
function validatorWithPrompt(): AuditEntry {
  const row = settledRows()[2]
  return {
    ...row,
    payload: {
      ...row.payload,
      llm_call: {
        provider: 'anthropic',
        prompt: { system: '# Role\nValidate.', user: '# Claim\nA pipe.' },
      },
    },
  }
}

function renderDialog(entry: AuditEntry, onClose = vi.fn()) {
  render(<RecordDialog entry={entry} header={recordHeader(entry)} onClose={onClose} />)
  return onClose
}

// Prompt 32: the record viewer (plan §3, D4).
describe('RecordDialog', () => {
  it('shows a record with a model call on two tabs, the instructions with their line breaks', async () => {
    const user = userEvent.setup()
    const entry = validatorWithPrompt()
    renderDialog(entry)
    expect(screen.getByRole('dialog', { name: recordHeader(entry) })).toBeInTheDocument()
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Record',
      'Instructions sent',
    ])
    expect(screen.getByTestId('record-tree')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Instructions sent' }))
    const panel = screen.getByRole('tabpanel', { name: 'Instructions sent' })
    expect(within(panel).getByRole('heading', { name: 'System instructions' })).toBeInTheDocument()
    expect(within(panel).getByRole('heading', { name: 'Message to the model' })).toBeInTheDocument()
    expect(within(panel).getByText(/# Role\s+Validate\./)).toHaveClass('whitespace-pre-wrap')
    expect(screen.queryByTestId('record-tree')).not.toBeInTheDocument()
    // Left arrow returns to the record.
    fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowLeft' })
    expect(screen.getByRole('tab', { name: 'Record' })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows one tab for a record with no model call: the orchestrator’s and a person’s', () => {
    renderDialog(settledRows()[0])
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Record'])
    expect(screen.queryByTestId('no-model-call')).not.toBeInTheDocument()
    render(<RecordDialog entry={decisionRows('rejected').at(-1)!} header="h" onClose={vi.fn()} />)
    expect(screen.queryByRole('tab', { name: 'Instructions sent' })).not.toBeInTheDocument()
  })

  it('says no model was called for the fixture Adjuster’s record', () => {
    renderDialog(guardrailFailureRows()[3])
    expect(screen.getAllByRole('tab')).toHaveLength(1)
    expect(screen.getByTestId('no-model-call')).toHaveTextContent(
      'No model was called for this record: the Adjuster’s figure came from the fixed demonstration file.',
    )
  })

  it('copies the record as the API served it, not the page’s rendering', () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const entry = validatorWithPrompt()
    renderDialog(entry)
    fireEvent.click(screen.getByRole('button', { name: 'Copy record' }))
    expect(writeText).toHaveBeenCalledWith(JSON.stringify(entry, null, 2))
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument()
  })

  it('closes from its Close button', () => {
    const onClose = renderDialog(settledRows()[1])
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
