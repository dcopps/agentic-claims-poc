import { useQuery } from '@tanstack/react-query'
import { Link, useLocation, useParams } from 'react-router-dom'
import type { AuditEntry, FiredRule } from '../api/types'
import { AgentCard, type CardState } from '../components/AgentCard'
import { Card, CopyButton, ErrorBanner, StatusBadge } from '../components/ui'
import { WakingNotice } from '../components/WakingNotice'
import { integrationsCopy } from '../copy/integrations'
import { statusLabel, variantLabel } from '../copy/labels'
import { failureReason, ruleLine, runCopy } from '../copy/run'
import { useAuditEntries, useClaim, useRun } from '../hooks/queries'
import { useRunStream } from '../hooks/useRunStream'
import {
  AGENTS,
  type AbortInfo,
  agentLabel,
  deriveAbort,
  deriveCards,
  deriveClaimId,
  deriveFiredRules,
  deriveStatus,
  deriveVariant,
} from './runDerivation'

// The run page reads the audit rows first and the live stream second
// (runDerivation.ts), so a run reads the same while it happens and afterwards.
export function RunDetailPage() {
  const { claimId: addressClaimId = '', correlationId = '' } = useParams()
  // The Claims page's trigger navigates here with `started`; a page opened any
  // other way with nothing recorded for the id is a run that does not exist.
  const startedHere = (useLocation().state as { started?: boolean } | null)?.started === true
  const events = useRunStream(correlationId, addressClaimId)
  const run = useRun(correlationId)
  const audit = useAuditEntries(correlationId)
  const runError = useRunError(correlationId)

  const rows = audit.data ?? []
  const variant = deriveVariant(rows, events)
  // Until both queries have answered (with data or a 404) and the stream is
  // silent, nothing is known about the run: say so rather than show four
  // "Waiting" cards, which read as a run that has not begun.
  const loading = (run.isPending || audit.isPending) && events.length === 0
  // Before the first event or row the runs/audit queries 404: expected in-flight
  // state for a run started here, "not found" for one that was not.
  const silent = events.length === 0 && rows.length === 0 && !runError
  // The run's own record names its claim; the address is consulted only once the
  // record has been read and names none, so no claim the run did not record is fetched.
  const claimId = deriveClaimId(rows, events, run.data) ?? (audit.isPending ? '' : addressClaimId)

  return (
    <div className="space-y-4">
      <RunHeader
        correlationId={correlationId}
        claimId={claimId}
        variant={variant}
        status={deriveStatus(rows, events, run.data)}
        rules={deriveFiredRules(rows, run.data)}
      />
      <RunNotices
        runError={runError}
        abort={deriveAbort(rows, events)}
        awaiting={silent && startedHere && !loading}
        notFound={silent && !startedHere && run.isError && audit.isError}
      />
      {loading ? (
        <div className="space-y-1">
          <p className="text-sm text-slate-500" role="status" data-testid="run-loading">
            {runCopy.loading}
          </p>
          <WakingNotice waiting />
        </div>
      ) : (
        <AgentCards cards={deriveCards(rows, events)} rows={rows} variant={variant} />
      )}
    </div>
  )
}

// Subscribe to the run-scoped error the ClaimsPage trigger writes on a POST
// failure (fix #6). enabled:false — nothing fetches; this only re-renders when
// setQueryData(['runError', cid], …) fires.
function useRunError(correlationId: string): string | null | undefined {
  return useQuery<string | null>({
    queryKey: ['runError', correlationId],
    queryFn: async () => null,
    enabled: false,
  }).data
}

interface AgentCardsProps {
  cards: Record<string, CardState>
  rows: AuditEntry[]
  variant: string
}

// The four agents in pipeline order, each with its derived state and its own
// audit row (for the expanded request and response).
function AgentCards({ cards, rows, variant }: AgentCardsProps) {
  return (
    <div className="space-y-2" aria-label="Pipeline agents">
      {AGENTS.map((agent) => (
        <AgentCard
          key={agent.key}
          agent={agent.key}
          label={agent.label}
          variant={variant}
          state={cards[agent.key]}
          auditEntry={rows.find((e) => e.step === agent.step)}
        />
      ))}
    </div>
  )
}

interface RunNoticesProps {
  runError?: string | null
  abort: AbortInfo | null
  awaiting: boolean
  notFound: boolean
}

// The banners and hints between the header and the cards: a POST that failed,
// an abort (from the audit row or the live event, in the same words as the
// failed card), the awaiting hint for a run started here, "Run not found" for
// an id nothing has recorded.
function RunNotices({ runError, abort, awaiting, notFound }: RunNoticesProps) {
  return (
    <>
      {runError && <ErrorBanner message={`Could not start the run: ${runError}`} />}
      {abort && (
        <ErrorBanner
          message={runCopy.aborted(
            failureReason(agentLabel(abort.failingAgent), abort.errorType, abort.message),
          )}
        />
      )}
      {awaiting && (
        <p className="text-sm text-slate-500" data-testid="awaiting-hint">
          Awaiting pipeline_started…
        </p>
      )}
      {notFound && (
        <p className="text-sm text-slate-500" data-testid="run-not-found">
          {runCopy.notFound}
        </p>
      )}
    </>
  )
}

interface RunHeaderProps {
  correlationId: string
  claimId: string
  variant: string
  status?: string
  rules: FiredRule[]
}

// Whose claim this is, the outcome badge in plain words, the variant as a
// sentence (the stored name is in the audit trail, not here), the copyable id
// with its links, and the fired escalation rules when the run went to a person.
function RunHeader({ correlationId, claimId, variant, status, rules }: RunHeaderProps) {
  return (
    <Card title="Pipeline run">
      <div className="space-y-2 text-sm text-slate-500">
        <ClaimLine claimId={claimId} />
        <p>
          <span data-testid="run-variant">{variantLabel(variant)}</span>
          {status && (
            <>
              {' · '}
              <StatusBadge status={status} label={statusLabel(status)} />
            </>
          )}
        </p>
        <RunIdLine correlationId={correlationId} />
        {rules.length > 0 && (
          <div data-testid="fired-rules">
            <p className="font-medium text-slate-700">{runCopy.rulesHeading}</p>
            <ul className="list-disc pl-5 text-slate-700">
              {rules.map((rule) => (
                <li key={rule.name}>{ruleLine(rule)}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}

// The claimant's name as the way back to the claim page, then the type, amount
// and claim number in plain words. Nothing is fetched until the page knows
// which claim the run recorded (`claimId` is empty until then).
function ClaimLine({ claimId }: { claimId: string }) {
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

// Full correlation id, copyable, with a one-click jump to the audit view of
// this same run (filter pre-populated via the query param) and a ready-made
// question for an MCP client, so the id is never read aloud in a demonstration
// (Phase 10).
function RunIdLine({ correlationId }: { correlationId: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span>run</span>
      <span className="break-all font-mono text-xs text-slate-700">{correlationId}</span>
      <CopyButton value={correlationId} />
      <Link
        to={`/audit?correlation_id=${correlationId}`}
        className="text-xs text-blue-600 hover:underline"
      >
        View audit log
      </Link>
      <CopyButton
        value={integrationsCopy.copyQuestion(correlationId)}
        label="Copy question for Claude"
      />
    </div>
  )
}
