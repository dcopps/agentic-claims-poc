import { describe, expect, it } from 'vitest'
import { disabledClosed, tooltips } from './tooltips'

describe('tooltips', () => {
  it('say first what the button does here', () => {
    expect(tooltips.submitClaim).toMatch(
      /^Saves the claim; nothing is processed until you press Process\./,
    )
    expect(tooltips.processClaim).toMatch(/^Runs the four agents on this claim now/)
    expect(tooltips.strictRerun).toMatch(
      /^Runs the claim again with the Validator under a stricter instruction/,
    )
  })

  it('then name the production trigger', () => {
    expect(tooltips.submitClaim).toContain('Azure Service Bus')
    expect(tooltips.processClaim).toContain('Durable Functions')
    expect(tooltips.strictRerun).toContain('deployment pipeline')
    expect(tooltips.verifyChain).toContain('Ledger Tables')
  })

  it('explain the refused objections on the Guardrail card in Dermot’s words', () => {
    expect(tooltips.refusedObjections).toBe(
      'The Guardrail’s model said these words cite policy wording that is not in the policy. ' +
        'The code checked each one and found it does not name a policy provision, so the ' +
        'objection did not count and is recorded here.',
    )
  })

  // Prompt 30: the claim page's compare button.
  it('explain Compare selected and why it is disabled', () => {
    expect(tooltips.compareSelected).toMatch(/^Opens the two runs side by side/)
    expect(tooltips.compareSelected).toContain('before a model is promoted')
    expect(tooltips.disabledCompareNeedsTwo).toBe('Not yet available: tick exactly two runs. ')
  })

  it('explain the disabled second action', () => {
    expect(tooltips.disabledNoFinishedRun).toBe(
      'Not yet available: this claim has no finished run. ',
    )
  })

  // Prompt 31: a claim a person has decided is closed to further runs.
  it('say why both actions are off on a decided claim, the decision named', () => {
    expect(tooltips.disabledClosedApproved).toBe(
      'Closed: a person approved this claim; it cannot be run again. ',
    )
    expect(tooltips.disabledClosedRejected).toBe(
      'Closed: a person rejected this claim; it cannot be run again. ',
    )
    expect(disabledClosed('approved')).toBe(tooltips.disabledClosedApproved)
    expect(disabledClosed('rejected')).toBe(tooltips.disabledClosedRejected)
  })
})
