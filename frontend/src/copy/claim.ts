// Every sentence and label the claim page, the human review panel and the
// Decision card can show (Prompt 30). The page used to print the record's
// stored values; these are the words a visitor reads instead. Stored values are
// never altered, and no wording lives inline in the components.
import { formatUsd } from './format'
import { runStatusLabel } from './labels'

/** A piece of a sentence: plain text, or an in-app link rendered with <Link>. */
export type Segment = string | { readonly link: string; readonly to: string }

/** What the latest run came to, as the runs list words it. */
export type RunOutcome =
  | { kind: 'settled'; settlement?: string }
  | { kind: 'aborted'; failingAgent?: string }
  | { kind: 'awaiting_human' }
  | { kind: 'running' }

export const claimCopy = {
  notFound: 'Claim not found.',
  backToClaims: '← Claims list',

  // --- Part 1: the claim card. Labels follow the form's where it has the field.
  fields: {
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
  },
  // Beside the badge when the claim's status is a mid-pipeline value: the latest
  // run broke before it finished, and the abort row names where.
  stoppedAt: (agentLabel: string, to: string): Segment[] => [
    'The ',
    { link: 'latest run', to },
    ` stopped at the ${agentLabel}.`,
  ],
  runInProgress: (to: string): Segment[] => [{ link: 'A run is in progress.', to }],

  // --- Part 2: the runs.
  runsHeading: 'Runs',
  compareHint: 'Tick two runs to compare them side by side.',
  compareSelected: 'Compare selected',
  latest: 'latest',
  auditLog: 'Audit log',
  selectRun: (startedAt: string) => `Select the run of ${startedAt}`,
  // The latest run's outcome from its rows; the summary's word when the rows
  // lack the figure or the agent (plan D1).
  runOutcome: (outcome: RunOutcome): string => {
    switch (outcome.kind) {
      case 'settled':
        return outcome.settlement ? `Settled at ${formatUsd(outcome.settlement)}` : 'Settled'
      case 'aborted':
        return outcome.failingAgent
          ? `Aborted at the ${outcome.failingAgent}`
          : runStatusLabel('aborted')
      default:
        return runStatusLabel(outcome.kind)
    }
  },
  noRuns: [
    'No runs yet. Go back to the ',
    { link: 'Claims list', to: '/' },
    ' and press Process on this claim.',
  ] as Segment[],

  // --- Part 3: the human review panel, in reading order.
  panelHeading: 'Human review',
  loadingEvidence: 'Loading evidence…',
  whyHeading: 'Why this claim is here',
  settlementHeading: 'Recommended settlement',
  reasoningHeading: 'The Adjuster’s reasoning',
  guardrailHeading: 'Guardrail',
  passagesHeading: 'Retrieved policy passages',
  cited: 'cited',
  nameLabel: 'Your name',
  commentLabel: 'Comment (optional)',
  approve: 'Approve',
  reject: 'Reject',
  // What each button does, checked against api/human.py: one audit row and the
  // claim's status; nothing writes a figure, so the recommendation stands.
  approveDoes:
    'Approve marks the claim Settled; the Adjuster’s recommendation above stands as the ' +
    'settlement.',
  rejectDoes: 'Reject marks the claim Rejected; no settlement is made.',
  decisionRecorded:
    'Your name, your comment and the time are written to the audit trail under this run.',
  // While the buttons are disabled for want of a name (plan D5).
  nameRequired: 'Enter your name to decide.',

  // --- The Decision card, in the panel's place once a person has decided.
  decisionHeading: 'Decision',
  decided: (decision: 'approved' | 'rejected', decidedBy: string, decidedAt: string) =>
    `${decision === 'approved' ? 'Approved' : 'Rejected'} by ${decidedBy} on ${decidedAt}.`,
  noComment: 'No comment was left.',
  decisionInAudit: (to: string): Segment[] => [
    'The decision is recorded in the audit trail under ',
    { link: 'the run', to },
    ' it was made on.',
  ],
} as const
