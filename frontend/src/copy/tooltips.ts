// Production-equivalent tooltip copy. Every action button names what its
// production counterpart would be, so a reviewer understands the prototype maps
// onto a real event-driven architecture. Kept in one file so Phase 6 polish can
// revise wording in one place. Locked at end of Phase 5.

export const tooltips = {
  submitClaim:
    'In production, the FNOL form posts to the Claims of Record system, which ' +
    'emits a `ClaimReceived` event on Azure Service Bus.',
  processClaim:
    'In production, this is triggered automatically by the `ClaimReceived` ' +
    'event handled by Azure Durable Functions.',
  reprocessV2:
    'In production, this is triggered by a model-promotion event raised by the ' +
    'Azure DevOps deployment pipeline.',
  verifyChain:
    'In production, the audit ledger is SQL Server with Ledger Tables; chain ' +
    'verification is a single `sys.sp_verify_database_ledger` call.',
} as const

export type TooltipKey = keyof typeof tooltips
