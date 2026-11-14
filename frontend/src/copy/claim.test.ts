import { describe, expect, it } from 'vitest'
import { claimCopy } from './claim'

// Every sentence the claim page can show, verbatim (Prompt 30).
describe('claimCopy', () => {
  it('labels the claim card as the form does and names the two pages', () => {
    expect(claimCopy.fields).toEqual({
      claimNumber: 'Claim number',
      policyNumber: 'Policy number',
      claimType: 'Claim type',
      reportedAmount: 'Reported amount',
      jurisdiction: 'Jurisdiction',
      lossDate: 'Loss date',
      reportedDate: 'Reported date',
      submitted: 'Submitted',
      status: 'Status',
      description: 'Description',
    })
    expect(claimCopy.backToClaims).toBe('← Claims list')
    expect(claimCopy.notFound).toBe('Claim not found.')
  })

  it('says beside the badge where the latest run stopped, linking to it', () => {
    expect(claimCopy.stoppedAt('Adjuster', '/claims/c1/runs/r1')).toEqual([
      'The ',
      { link: 'latest run', to: '/claims/c1/runs/r1' },
      ' stopped at the Adjuster.',
    ])
    expect(claimCopy.runInProgress('/claims/c1/runs/r2')).toEqual([
      { link: 'A run is in progress.', to: '/claims/c1/runs/r2' },
    ])
  })

  it('words the latest run’s outcome from its rows, and the word alone without them', () => {
    expect(claimCopy.runOutcome({ kind: 'settled', settlement: '82500.00' })).toBe(
      'Settled at $82,500',
    )
    expect(claimCopy.runOutcome({ kind: 'settled' })).toBe('Settled')
    expect(claimCopy.runOutcome({ kind: 'aborted', failingAgent: 'Adjuster' })).toBe(
      'Aborted at the Adjuster',
    )
    expect(claimCopy.runOutcome({ kind: 'aborted' })).toBe('Aborted')
    expect(claimCopy.runOutcome({ kind: 'awaiting_human' })).toBe('Awaiting human review')
    expect(claimCopy.runOutcome({ kind: 'running' })).toBe('Running')
  })

  it('explains the runs list', () => {
    expect(claimCopy.compareHint).toBe('Tick two runs to compare them side by side.')
    expect(claimCopy.compareSelected).toBe('Compare selected')
    expect(claimCopy.latest).toBe('latest')
    expect(claimCopy.auditLog).toBe('Audit log')
    expect(claimCopy.selectRun('10 Nov 2026, 17:24')).toBe('Select the run of 10 Nov 2026, 17:24')
    expect(claimCopy.noRuns).toEqual([
      'No runs yet. Go back to the ',
      { link: 'Claims list', to: '/' },
      ' and press Process on this claim.',
    ])
  })

  it('heads the review panel in reading order and labels its inputs', () => {
    expect([
      claimCopy.whyHeading,
      claimCopy.settlementHeading,
      claimCopy.reasoningHeading,
      claimCopy.guardrailHeading,
      claimCopy.passagesHeading,
    ]).toEqual([
      'Why this claim is here',
      'Recommended settlement',
      'The Adjuster’s reasoning',
      'Guardrail',
      'Retrieved policy passages',
    ])
    expect(claimCopy.nameLabel).toBe('Your name')
    expect(claimCopy.commentLabel).toBe('Comment (optional)')
    expect(claimCopy.nameRequired).toBe('Enter your name to decide.')
  })

  // Checked against api/human.py: one audit row and the claim's status, no figure.
  it('says what each button does, in the words Dermot approved', () => {
    expect(claimCopy.approveDoes).toBe(
      'Approve marks the claim Settled; the Adjuster’s recommendation above stands as the settlement.',
    )
    expect(claimCopy.rejectDoes).toBe('Reject marks the claim Rejected; no settlement is made.')
    expect(claimCopy.decisionRecorded).toBe(
      'Your name, your comment and the time are written to the audit trail under this run.',
    )
  })

  it('records a decision in one sentence with the run linked', () => {
    expect(claimCopy.decided('approved', 'A. Reviewer', '13 Nov 2026, 15:02')).toBe(
      'Approved by A. Reviewer on 13 Nov 2026, 15:02.',
    )
    expect(claimCopy.decided('rejected', 'Dermot', '10 Nov 2026, 18:50')).toBe(
      'Rejected by Dermot on 10 Nov 2026, 18:50.',
    )
    expect(claimCopy.noComment).toBe('No comment was left.')
    expect(claimCopy.decisionInAudit('/claims/c1/runs/r1')).toEqual([
      'The decision is recorded in the audit trail under ',
      { link: 'the run', to: '/claims/c1/runs/r1' },
      ' it was made on.',
    ])
  })
})
