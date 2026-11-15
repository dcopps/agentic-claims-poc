import { Link } from 'react-router-dom'
import { runCopy } from '../copy/run'
import { useClaim } from '../hooks/queries'

// The claimant's name as the way back to the claim page, then the type, amount
// and claim number in plain words (Prompt 29's run page line; shared with the
// Audit page since Prompt 32, so a run is named the same way wherever it is
// shown). Nothing is fetched until the caller knows which claim the run
// recorded (`claimId` is empty until then).
export function ClaimLine({ claimId }: { claimId: string }) {
  const claim = useClaim(claimId, claimId !== '')
  if (claim.isError) {
    return (
      <p className="text-slate-500" data-testid="run-claim">
        {runCopy.claimUnavailable}
      </p>
    )
  }
  if (!claim.data) return null
  const { claim_id, claimant_name, claim_type, reported_amount, claim_number } = claim.data
  return (
    <p className="text-slate-700" data-testid="run-claim">
      <Link to={`/claims/${claim_id}`} className="font-medium text-blue-700 hover:underline">
        {claimant_name}
      </Link>
      {' · '}
      {runCopy.claimDetails(claim_type, reported_amount, claim_number)}
    </p>
  )
}
