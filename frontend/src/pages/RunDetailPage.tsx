import { useQuery } from '@tanstack/react-query'
import { Link, useLocation, useParams } from 'react-router-dom'
import type { FiredRule } from '../api/types'
import { AgentCard } from '../components/AgentCard'
import { Card, CopyButton, ErrorBanner, StatusBadge } from '../components/ui'
import { integrationsCopy } from '../copy/integrations'
import { statusLabel, variantLabel } from '../copy/labels'
import { failureReason, ruleLine, runCopy } from '../copy/run'
import { useAuditEntries, useRun } from '../hooks/queries'
import { useRunStream } from '../hooks/useRunStream'
import {
  AGENTS,
  type AbortInfo,
  agentLabel,
  deriveAbort,
  deriveCards,
  deriveFiredRules,
  deriveStatus,
  deriveVariant,
} from './runDerivation'

// The run page reads the audit rows first and the live stream second
// (runDerivation.ts), so a run reads the same while it happens and afterwards.
export function RunDetailPage() {
  const { claimId = '', correlationId = '' } = useParams()
  // The Claims page's trigger navigates here with `started`; a page opened any
  // other way with nothing recorded for the id is a run that does not exist.
  const startedHere = (useLocation().state as { started?: boolean } | null)?.started === true
  const events = useRunStream(correlationId, claimId)
  const run = useRun(correlationId)
  const audit = useAuditEntries(correlationId)
  const runError = useRunError(correlationId)

  const rows = audit.data ?? []
  const variant = deriveVariant(rows, events)
  const cards = deriveCards(rows, events)
  // Before the first event or row the runs/audit queries 404: expected in-flight
  // state for a run started here, "not found" for one that was not.
  const silent = events.length === 0 && rows.length === 0 && !runError

  return (
    <div className="space-y-4">
      <RunHeader
        correlationId={correlationId}
        variant={variant}
        status={deriveStatus(rows, events, run.data)}
        rules={deriveFiredRules(rows, run.data)}
      />
      <RunNotices
        runError={runError}
        abort={deriveAbort(rows, events)}
        awaiting={silent && startedHere}
        notFound={silent && !startedHere && run.isError && audit.isError}
      />
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
  variant: string
  status?: string
  rules: FiredRule[]
}

// The outcome badge in plain words, the variant as a sentence with its stored
// name beside it, the copyable id with its links, and the fired escalation
// rules when the run went to a person.
function RunHeader({ correlationId, variant, status, rules }: RunHeaderProps) {
  return (
    <Card title="Pipeline run">
      <div className="space-y-2 text-sm text-slate-500">
        <p>
          <span data-testid="run-variant">{variantLabel(variant)}</span>{' '}
          <span className="font-mono text-xs text-slate-400">{variant}</span>
          {status && (
            <>
              {' · '}
              <StatusBadge status={status} label={statusLabel(status)} />
            </>
          )}
        </p>
        {/* Full correlation id, copyable, with a one-click jump to the audit
            view of this same run (filter pre-populated via the query param). */}
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
          {/* A ready-made question for an MCP client, so the id is never read
              aloud in a demonstration (Phase 10). */}
          <CopyButton
            value={integrationsCopy.copyQuestion(correlationId)}
            label="Copy question for Claude"
          />
        </div>
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
