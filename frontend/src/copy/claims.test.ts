import { describe, expect, it } from 'vitest'
import { claimsCopy } from './claims'

// Every label and sentence the Claims page's list can show, verbatim (Prompt 31).
describe('claimsCopy', () => {
  it('names the two actions and the second label of the primary one', () => {
    expect(claimsCopy.process).toBe('Process')
    expect(claimsCopy.runAgain).toBe('Run again')
    expect(claimsCopy.strictRerun).toBe('Strict re-run')
  })

  it('asks once before a settled claim is run again', () => {
    expect(claimsCopy.confirmRerun).toBe('This claim has already settled. Run it again?')
    expect(claimsCopy.confirm).toBe('Run again')
    expect(claimsCopy.cancel).toBe('Cancel')
  })

  it('keeps the two list messages as they were', () => {
    expect(claimsCopy.loadFailed).toBe('Failed to load claims.')
    expect(claimsCopy.noClaims).toBe('No claims yet — submit one above.')
  })
})
