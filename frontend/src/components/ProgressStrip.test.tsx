import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PipelineEvent } from '../api/types'
import { ProgressStrip } from './ProgressStrip'

const events: PipelineEvent[] = [
  { event_type: 'pipeline_started', correlation_id: 'c', timestamp: 't', variant: 'default' },
  {
    event_type: 'agent_completed',
    correlation_id: 'c',
    timestamp: 't',
    agent: 'doc_parser',
    duration_ms: 5,
    summary: { claim_type: 'fire' },
  },
  { event_type: 'pipeline_completed', correlation_id: 'c', timestamp: 't', status: 'settled' },
]

describe('ProgressStrip', () => {
  it('renders nothing without events', () => {
    const { container } = render(<ProgressStrip events={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders agent progress and the outcome', () => {
    render(<ProgressStrip events={events} />)
    expect(screen.getByText('Doc-Parser')).toBeInTheDocument()
    expect(screen.getByTestId('run-outcome')).toHaveTextContent(/settled/i)
    expect(screen.getByText(/variant: default/i)).toBeInTheDocument()
  })
})
