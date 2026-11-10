// Tooltip copy for the action buttons (Phase 5; rewritten by Prompt 28). Each
// text says first what the button does here, then, in one clause, what would
// trigger it in production, so a reviewer sees the prototype mapped onto a real
// event-driven architecture. Shown on hover and on keyboard focus by Tooltip.tsx.

export const tooltips = {
  submitClaim:
    'Saves the claim; nothing is processed until you press Process. In production the form ' +
    'would post to the claims system, which raises a ClaimReceived event on Azure Service Bus.',
  processClaim:
    'Runs the four agents on this claim now and opens the run page to watch them. In ' +
    'production the ClaimReceived event would start this automatically through Azure ' +
    'Durable Functions.',
  rerunStrictValidator:
    'Runs the claim again with the Validator under a stricter instruction, so the two runs ' +
    'can be compared on the claim’s page. In production a model-promotion event from the ' +
    'deployment pipeline would trigger it.',
  // Prefixed to rerunStrictValidator while the button is disabled.
  disabledNoFinishedRun: 'Not yet available: this claim has no finished run. ',
  verifyChain:
    'In production, the audit ledger is SQL Server with Ledger Tables; chain ' +
    'verification is a single `sys.sp_verify_database_ledger` call.',
} as const

export type TooltipKey = keyof typeof tooltips
