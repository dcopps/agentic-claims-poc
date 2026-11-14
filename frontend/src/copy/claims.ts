// Every label and sentence the Claims page's list can show (Prompt 31). The two
// action labels moved here from the component unchanged; the rest is new.
export const claimsCopy = {
  // The primary action: Process for a claim never run, Run again once it has had
  // a run (the claim's status is no longer `received`).
  process: 'Process',
  runAgain: 'Run again',
  strictRerun: 'Strict re-run',
  // Asked once, in the row, before a settled claim is run again. No browser
  // dialog: the question is a small panel anchored to the actions cell.
  confirmRerun: 'This claim has already settled. Run it again?',
  confirm: 'Run again',
  cancel: 'Cancel',
  loadFailed: 'Failed to load claims.',
  noClaims: 'No claims yet — submit one above.',
} as const
