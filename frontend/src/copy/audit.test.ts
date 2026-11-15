import { describe, expect, it } from 'vitest'
import { auditCopy } from './audit'

// Prompt 32: every sentence the Audit page and the viewer show, verbatim.
describe('auditCopy', () => {
  it('names the run id and says how much of it is enough', () => {
    expect(auditCopy.runIdLabel).toBe('Run id')
    expect(auditCopy.runIdHint).toBe('Paste a run id, or its first eight characters.')
    expect(auditCopy.tooShort).toBe('Give at least the first eight characters of the run id.')
    expect(auditCopy.noneStartWith('00000000')).toBe('No run starts with 00000000.')
    expect(auditCopy.severalStartWith(3, '2bd08a61')).toBe(
      '3 runs start with 2bd08a61; give more of the id.',
    )
    expect(auditCopy.chooseRun).toBe('Enter a run id, or choose a run above, to see its records.')
    expect(auditCopy.unknownId).toBe('No run has this id.')
    expect(auditCopy.loadFailed).toBe('The records could not be loaded.')
  })

  it('heads the recent runs as a table in the Claims list’s style', () => {
    expect(auditCopy.recentHeading(20)).toBe('The 20 most recent runs')
    expect(Object.values(auditCopy.recentColumns)).toEqual([
      'Claimant',
      'Kind of run',
      'Started',
      'Outcome',
    ])
  })

  it('names the run and its records', () => {
    expect(auditCopy.runLine('Standard run', '15 Nov 2026, 15:09:03', 'Settled at $78,000')).toBe(
      'Standard run · started 15 Nov 2026, 15:09:03 · Settled at $78,000',
    )
    expect(auditCopy.openRun).toBe('Open the run page')
    expect(Object.values(auditCopy.columns)).toEqual(['When', 'Who', 'What happened', 'Record'])
    expect(auditCopy.recordCell(210, 'a1b2c3d4e5f6a7b8c9')).toBe('#210 · a1b2c3d4e5f6')
    expect(auditCopy.openRecord(210)).toBe('Open record 210')
  })

  it('gives the chain check in sentences, for both kinds of break', () => {
    expect(auditCopy.verify).toBe('Verify chain')
    expect(auditCopy.verified(218)).toBe(
      'Checked all 218 records in the ledger, this run’s included: every hash matches.',
    )
    expect(auditCopy.breakAt(57, 'row_hash_mismatch')).toBe(
      'A break at record 57: the record’s own hash does not match its contents.',
    )
    expect(auditCopy.breakAt(57, 'chain_hash_mismatch')).toBe(
      'A break at record 57: the link to the record before it does not match.',
    )
    expect(auditCopy.breakAt(57, 'something_new')).toBe('A break at record 57: (something_new).')
  })

  it('has the sentences the run page has none for', () => {
    expect(auditCopy.started('default')).toBe('Run started: Standard run')
    expect(auditCopy.started('v2_strict_validator')).toBe('Run started: Strict Validator run')
    expect(auditCopy.noRuleFired).toBe('No rule fired; the claim settles')
    expect(auditCopy.sentToPerson(['A', 'B'])).toBe('Sent to a person: A; B')
    expect(auditCopy.decided('Rejected', 'Dermot Copps')).toBe('Rejected by Dermot Copps')
    expect(auditCopy.who).toEqual({ orchestrator: 'Orchestrator', human: 'A person' })
    expect(Object.keys(auditCopy.stepNames)).toHaveLength(11)
  })

  it('words the viewer', () => {
    expect(
      auditCopy.recordHeader('Validator', 'coverage check', '15 Nov 2026, 15:09:08', 210),
    ).toBe('Validator · coverage check · 15 Nov 2026, 15:09:08 · record 210 in the ledger')
    expect([auditCopy.tabRecord, auditCopy.tabInstructions]).toEqual([
      'Record',
      'Instructions sent',
    ])
    expect([auditCopy.systemHeading, auditCopy.userHeading]).toEqual([
      'System instructions',
      'Message to the model',
    ])
    expect(auditCopy.copyRecord).toBe('Copy record')
    expect(auditCopy.noModelCall).toBe(
      'No model was called for this record: the Adjuster’s figure came from the fixed ' +
        'demonstration file.',
    )
    expect(auditCopy.keys(1)).toBe('1 key')
    expect(auditCopy.keys(5)).toBe('5 keys')
    expect(auditCopy.items(3)).toBe('3 items')
  })
})
