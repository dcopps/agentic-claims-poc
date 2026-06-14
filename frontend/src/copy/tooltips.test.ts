import { describe, expect, it } from 'vitest'
import { tooltips } from './tooltips'

describe('tooltips', () => {
  it('names the production equivalents', () => {
    expect(tooltips.submitClaim).toContain('Service Bus')
    expect(tooltips.processClaim).toContain('Durable Functions')
    expect(tooltips.reprocessV2).toContain('Azure DevOps')
    expect(tooltips.verifyChain).toContain('Ledger Tables')
  })
})
