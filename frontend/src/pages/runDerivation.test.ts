import { describe, expect, it } from 'vitest'
import type { PipelineEvent } from '../api/types'
import {
  ABORT_MESSAGE,
  abortedRows,
  ceilingRows,
  guardrailFailureRows,
  guardrailThrewRows,
  settledRows,
} from '../test/runFixtures'
import {
  deriveAbort,
  deriveCards,
  deriveFiredRules,
  deriveStatus,
  deriveVariant,
} from './runDerivation'

function event(partial: Partial<PipelineEvent> & { event_type: string }): PipelineEvent {
  return { correlation_id: 'cid-1', timestamp: 't', ...partial }
}

// Prompt 29: the audit rows decide a card's state wherever they can; the live
// stream speaks only where the rows are silent.
describe('deriveCards from audit rows alone', () => {
  it('reads a settled run: four agents done, with sentences and durations from the rows', () => {
    const cards = deriveCards(settledRows(), [])
    expect(cards.doc_parser).toEqual({
      status: 'done',
      summary: 'Summarised the claim (Water damage)',
      durationMs: 1310,
      durationFromAudit: true,
    })
    expect(cards.validator.summary).toBe('Covered (92% confident)')
    expect(cards.validator.durationMs).toBe(3400)
    expect(cards.adjuster.summary).toBe('Recommends $82,500 (85% confident)')
    expect(cards.guardrail).toMatchObject({ status: 'done', summary: 'Passed', durationMs: 1600 })
  })

  it('reads the ceiling escalation: the agents done, the rule in the header', () => {
    const rows = ceilingRows()
    expect(deriveCards(rows, []).adjuster.summary).toBe('Recommends $820,000 (85% confident)')
    expect(deriveStatus(rows, [])).toBe('awaiting_human')
    expect(deriveFiredRules(rows).map((r) => r.name)).toEqual(['settlement_over_ceiling'])
  })

  it('reads the Guardrail failure as the outcome it is: the fixture named, ⚠ not ✗, the finding beneath', () => {
    const cards = deriveCards(guardrailFailureRows(), [])
    expect(cards.adjuster.summary).toBe(
      'Recommends $1,400,000 from the fixed demonstration file, no model call (82% confident)',
    )
    expect(cards.guardrail).toMatchObject({
      status: 'escalated',
      summary: 'Failed: cited policy wording the policy does not contain',
      detail: "endorsement 'Coastal Surge Rider' not in retrieved chunks",
    })
    expect(deriveFiredRules(guardrailFailureRows()).map((r) => r.name)).toEqual([
      'guardrail_failed',
      'settlement_over_ceiling',
    ])
  })

  it('reads an aborted run: the failing agent Failed with the reason and message, the later agent Not run', () => {
    const rows = abortedRows()
    const cards = deriveCards(rows, [])
    expect(cards.doc_parser.status).toBe('done')
    expect(cards.validator.summary).toBe('Covered (88% confident)')
    expect(cards.adjuster).toEqual({
      status: 'failed',
      summary: 'Failed: the Adjuster has no market range for the claim type Smoke damage',
      detail: ABORT_MESSAGE,
    })
    expect(cards.guardrail).toEqual({
      status: 'not_run',
      summary: 'Not run: the run stopped at the Adjuster',
    })
    expect(deriveStatus(rows, [])).toBe('aborted')
    expect(deriveAbort(rows, [])).toEqual({
      failingAgent: 'adjuster',
      errorType: 'ValueError',
      message: ABORT_MESSAGE,
    })
  })

  it('reads the fail-closed path: the Guardrail Failed in its own words, the run awaiting a person', () => {
    const rows = guardrailThrewRows()
    const cards = deriveCards(rows, [])
    expect(cards.adjuster.status).toBe('done')
    expect(cards.guardrail).toEqual({
      status: 'failed',
      summary: 'Failed: the check itself raised an error, so the claim went to a person',
      detail: 'anthropic: 529 overloaded',
    })
    expect(deriveStatus(rows, [])).toBe('awaiting_human')
  })

  it('counts refused objections on a passed Guardrail', () => {
    const rows = settledRows()
    const guardrail = rows.find((r) => r.step === 'output_check')!
    guardrail.payload = {
      ...guardrail.payload,
      llm_flags_discarded: [
        { reason: 'quote_not_a_provision' },
        { reason: 'no_quote' },
        { reason: 'no_quote' },
      ],
    }
    expect(deriveCards(rows, []).guardrail.summary).toBe('Passed; 3 objections refused')
  })

  it('gives no duration for the first row and none when a timestamp does not parse', () => {
    const rows = settledRows()
    rows[1].created_at = 'not a date'
    expect(deriveCards(rows, []).doc_parser.durationMs).toBeUndefined()
  })
})

describe('deriveCards from live events alone', () => {
  it('moves through queued, running and done as the events arrive', () => {
    const queued = deriveCards([], [event({ event_type: 'pipeline_started', variant: 'default' })])
    expect(queued.doc_parser).toEqual({ status: 'queued', summary: 'Waiting' })

    const running = deriveCards([], [event({ event_type: 'agent_started', agent: 'doc_parser' })])
    expect(running.doc_parser).toEqual({ status: 'running', summary: 'Running' })

    const done = deriveCards(
      [],
      [
        event({
          event_type: 'agent_completed',
          agent: 'doc_parser',
          duration_ms: 1300,
          summary: { claim_type: 'fire' },
        }),
        event({
          event_type: 'agent_completed',
          agent: 'validator',
          duration_ms: 3000,
          summary: { covered: false },
        }),
        event({
          event_type: 'agent_completed',
          agent: 'adjuster',
          duration_ms: 2000,
          summary: { recommended_settlement: '82500.00' },
        }),
        event({
          event_type: 'agent_completed',
          agent: 'guardrail',
          duration_ms: 1000,
          summary: { passed: false },
        }),
      ],
    )
    expect(done.doc_parser).toEqual({
      status: 'done',
      summary: 'Summarised the claim (Fire)',
      durationMs: 1300,
    })
    expect(done.validator.summary).toBe('Not covered')
    expect(done.adjuster.summary).toBe('Recommends $82,500')
    expect(done.guardrail).toMatchObject({ status: 'escalated', summary: 'Failed' })
  })

  it('applies a live abort at once: the failing card Failed, the later cards Not run', () => {
    const cards = deriveCards(
      [],
      [
        event({
          event_type: 'agent_completed',
          agent: 'doc_parser',
          duration_ms: 1300,
          summary: {},
        }),
        event({
          event_type: 'agent_completed',
          agent: 'validator',
          duration_ms: 3000,
          summary: { covered: true },
        }),
        event({ event_type: 'agent_started', agent: 'adjuster' }),
        event({
          event_type: 'pipeline_aborted',
          failing_agent: 'adjuster',
          error_type: 'ValueError',
          message: ABORT_MESSAGE,
        }),
      ],
    )
    expect(cards.validator.status).toBe('done')
    expect(cards.adjuster).toMatchObject({
      status: 'failed',
      summary: 'Failed: the Adjuster has no market range for the claim type Smoke damage',
    })
    expect(cards.guardrail.status).toBe('not_run')
    expect(
      deriveStatus([], [event({ event_type: 'pipeline_aborted', failing_agent: 'adjuster' })]),
    ).toBe('aborted')
  })

  it('reads the fail-closed completion live', () => {
    const cards = deriveCards(
      [],
      [
        event({
          event_type: 'pipeline_completed',
          status: 'awaiting_human',
          summary: { escalate: true, reason: 'guardrail_threw' },
        }),
      ],
    )
    expect(cards.guardrail).toEqual({
      status: 'failed',
      summary: 'Failed: the check itself raised an error, so the claim went to a person',
    })
  })
})

describe('rows and events together', () => {
  it('lets the row give the sentence and the live event give the duration', () => {
    const cards = deriveCards(settledRows(), [
      event({
        event_type: 'agent_completed',
        agent: 'validator',
        duration_ms: 3333,
        summary: { covered: true },
      }),
    ])
    expect(cards.validator).toEqual({
      status: 'done',
      summary: 'Covered (92% confident)',
      durationMs: 3333,
    })
  })

  it('reads the abort from the row even when the failing agent wrote a row of its own', () => {
    // A model-call failure: the Validator writes a row with an error block and
    // the orchestrator's abort row names it.
    const rows = abortedRows().filter((r) => r.step !== 'pipeline_aborted')
    rows.find((r) => r.step === 'coverage_check')!.payload = { error: { type: 'LLMProviderError' } }
    rows.push({
      audit_id: 99,
      agent: 'orchestrator',
      step: 'pipeline_aborted',
      created_at: '2026-11-10T16:20:09.000Z',
      chain_hash: 'h',
      payload: {
        status: 'aborted',
        failing_agent: 'validator',
        error_type: 'LLMProviderError',
        error_message: 'anthropic: 529 overloaded',
      },
    })
    const cards = deriveCards(rows, [])
    expect(cards.validator).toEqual({
      status: 'failed',
      summary: 'Failed: the model provider refused or failed the call',
      detail: 'anthropic: 529 overloaded',
    })
    expect(cards.adjuster.summary).toBe('Not run: the run stopped at the Validator')
    expect(cards.guardrail.status).toBe('not_run')
  })
})

describe('the header', () => {
  it('takes the variant from the live start, then the start row, then the default', () => {
    expect(
      deriveVariant(
        [],
        [event({ event_type: 'pipeline_started', variant: 'v2_strict_validator' })],
      ),
    ).toBe('v2_strict_validator')
    expect(deriveVariant(settledRows(), [])).toBe('default')
    expect(deriveVariant([], [])).toBe('default')
  })

  it('takes the status from the live completion, the terminal row, the run, then "running"', () => {
    expect(
      deriveStatus(ceilingRows(), [event({ event_type: 'pipeline_completed', status: 'settled' })]),
    ).toBe('settled')
    expect(deriveStatus(settledRows(), [])).toBe('settled')
    expect(deriveStatus([], [], { status: 'aborted' } as never)).toBe('aborted')
    expect(deriveStatus([], [event({ event_type: 'pipeline_started' })])).toBe('running')
    expect(deriveStatus([], [])).toBeUndefined()
  })

  it('falls back to the reconstructed run for the fail-closed rule, which has no decision row', () => {
    const run = {
      status: 'awaiting_human',
      escalation_decision: {
        escalate: true,
        fired_rules: [
          {
            name: 'guardrail_failed',
            rule_type: 'hard',
            description: 'Guardrail check raised an exception; failing closed',
          },
        ],
        reasoning: '',
      },
    } as never
    expect(deriveFiredRules(guardrailThrewRows(), run).map((r) => r.name)).toEqual([
      'guardrail_failed',
    ])
    expect(deriveFiredRules(settledRows(), run)).toEqual([])
  })
})
