import { describe, expect, it } from 'vitest'
import { tooltips } from './tooltips'

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

  it('explain the disabled second action', () => {
    expect(tooltips.disabledNoFinishedRun).toBe(
      'Not yet available: this claim has no finished run. ',
    )
  })
})
