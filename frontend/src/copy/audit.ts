// Every sentence, label, heading and tooltip the Audit page and the record
// viewer can show (Prompt 32). The page used to print the stored agent, step
// and hash; these are the words a visitor reads instead. Where the run page or
// the claim page already has a sentence for a row, auditDerivation.ts reuses
// it and nothing is worded twice here.
import { variantLabel } from './labels'

export const auditCopy = {
  heading: 'Audit log',
  runIdLabel: 'Run id',
  runIdHint: 'Paste a run id, or its first eight characters.',
  load: 'Load',
  // Fewer than eight characters never reaches the backend (Dermot, at the gate).
  tooShort: 'Give at least the first eight characters of the run id.',
  invalidId: 'A run id is made of the characters 0–9, a–f and hyphens.',
  resolving: 'Finding the run…',
  noneStartWith: (prefix: string) => `No run starts with ${prefix}.`,
  severalStartWith: (count: number, prefix: string) =>
    `${count} runs start with ${prefix}; give more of the id.`,

  // The table of recent runs, in the Claims list's style (Dermot, 15 November);
  // below the records when a run is loaded, so a visitor sees their run first.
  recentHeading: (count: number) => `The ${count} most recent runs`,
  recentColumns: {
    claimant: 'Claimant',
    kind: 'Kind of run',
    started: 'Started',
    outcome: 'Outcome',
  },
  noRuns: 'No runs recorded yet.',
  recentLoadFailed: 'Recent runs could not be loaded.',

  chooseRun: 'Enter a run id, or choose a run above, to see its records.',
  unknownId: 'No run has this id.',
  loadFailed: 'The records could not be loaded.',
  loading: 'Loading records…',

  // The run's own line under the claim line: kind, start, outcome.
  runLine: (kind: string, started: string, outcome: string) =>
    `${kind} · started ${started} · ${outcome}`,
  openRun: 'Open the run page',

  recordsHeading: 'Records',
  columns: { when: 'When', who: 'Who', what: 'What happened', record: 'Record' },
  recordCell: (auditId: number, chainHash: string) => `#${auditId} · ${chainHash.slice(0, 12)}`,
  openRecord: (auditId: number) => `Open record ${auditId}`,
  aboutRecords: 'About records and hashes',

  verify: 'Verify chain',
  verifying: 'Checking…',
  verifyFailed: 'The chain could not be checked.',
  verified: (count: number) =>
    `Checked all ${count} records in the ledger, this run’s included: every hash matches.`,
  breakAt: (auditId: number, kind: string) => `A break at record ${auditId}: ${breakReason(kind)}`,

  // --- the record viewer
  close: 'Close',
  tabRecord: 'Record',
  tabInstructions: 'Instructions sent',
  systemHeading: 'System instructions',
  userHeading: 'Message to the model',
  copyRecord: 'Copy record',
  noModelCall:
    'No model was called for this record: the Adjuster’s figure came from the fixed ' +
    'demonstration file.',
  // "Validator · coverage check · 15 Nov 2026, 15:09:08 · record 210 in the ledger"
  recordHeader: (who: string, what: string, when: string, auditId: number) =>
    `${who} · ${what} · ${when} · record ${auditId} in the ledger`,
  showAll: 'Show all',
  showLess: 'Show less',
  keys: (count: number) => (count === 1 ? '1 key' : `${count} keys`),
  items: (count: number) => (count === 1 ? '1 item' : `${count} items`),
  empty: 'empty',

  // --- the sentences the run page has none for
  started: (variant: string) => `Run started: ${variantLabel(variant)}`,
  noRuleFired: 'No rule fired; the claim settles',
  sentToPerson: (ruleLines: string[]) => `Sent to a person: ${ruleLines.join('; ')}`,
  decided: (decisionWord: string, decidedBy: string) => `${decisionWord} by ${decidedBy}`,
  who: { orchestrator: 'Orchestrator', human: 'A person' } as Record<string, string>,
  // The step in plain words, for the record's header line.
  stepNames: {
    pipeline_started: 'run started',
    doc_extract: 'narrative summary',
    coverage_check: 'coverage check',
    settlement_estimate: 'settlement estimate',
    output_check: 'output check',
    escalation_decision: 'escalation decision',
    pipeline_settled: 'settled',
    pipeline_awaiting_human: 'sent to a person',
    pipeline_aborted: 'run aborted',
    human_approval: 'approval',
    human_rejection: 'rejection',
  } as Record<string, string>,
} as const

// The verifier's two break kinds (backend/app/audit/verify.py) in words; an
// unknown kind is shown as itself so a new kind is never hidden.
const BREAK_REASONS: Record<string, string> = {
  row_hash_mismatch: 'the record’s own hash does not match its contents.',
  chain_hash_mismatch: 'the link to the record before it does not match.',
}

function breakReason(kind: string): string {
  return BREAK_REASONS[kind] ?? `(${kind}).`
}
