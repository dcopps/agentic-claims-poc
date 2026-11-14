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
  strictRerun:
    'Runs the claim again with the Validator under a stricter instruction, so the two runs ' +
    'can be compared on the claim’s page. In production a model-promotion event from the ' +
    'deployment pipeline would trigger it.',
  // Prefixed to strictRerun while the button is disabled.
  disabledNoFinishedRun: 'Not yet available: this claim has no finished run. ',
  // The claim page's Compare selected button (Prompt 30).
  compareSelected:
    'Opens the two runs side by side: the settlement, whether each went to a person, the ' +
    'Guardrail’s verdict and the rules that differed. In production the same comparison would ' +
    'be run before a model is promoted.',
  // Prefixed to compareSelected while fewer or more than two runs are ticked.
  disabledCompareNeedsTwo: 'Not yet available: tick exactly two runs. ',
  verifyChain:
    'In production, the audit ledger is SQL Server with Ledger Tables; chain ' +
    'verification is a single `sys.sp_verify_database_ledger` call.',
  // Beside "Refused objections" on the Guardrail card (Dermot's wording, 12
  // November 2026): what the line is and why the objections did not count.
  refusedObjections:
    'The Guardrail’s model said these words cite policy wording that is not in the policy. ' +
    'The code checked each one and found it does not name a policy provision, so the ' +
    'objection did not count and is recorded here.',
} as const

export type TooltipKey = keyof typeof tooltips
