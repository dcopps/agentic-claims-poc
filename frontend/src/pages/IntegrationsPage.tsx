import { Link } from 'react-router-dom'
import { mcpEndpointUrl } from '../api/client'
import type { McpCatalogue, McpTool, ToolCallRecord } from '../api/types'
import { Badge, Card, CopyButton, ErrorBanner, Spinner } from '../components/ui'
import { WakingNotice } from '../components/WakingNotice'
import { integrationsCopy } from '../copy/integrations'
import { useMcpCatalogue } from '../hooks/queries'
import { useMcpActivity } from '../hooks/useMcpActivity'
import { typography } from '../styles/tokens'

// The Integrations page: what an AI client may call (from the server's own
// definitions), how to connect one (never showing a token), and the tool calls
// as they happen. The catalogue and the feed both answer whether or not the
// endpoint is mounted; `mounted` only changes the connection card's opening line.
export function IntegrationsPage() {
  const catalogue = useMcpCatalogue()
  const records = useMcpActivity()

  return (
    <div className="space-y-4">
      <h1 className={typography.pageTitle}>{integrationsCopy.title}</h1>
      <p className="text-sm text-slate-600">{integrationsCopy.intro}</p>

      {catalogue.isLoading && <Spinner label="Loading the tool catalogue…" />}
      <WakingNotice waiting={catalogue.isLoading} />
      {catalogue.error && (
        <ErrorBanner message={`Could not load the tool catalogue: ${catalogue.error.message}`} />
      )}
      {catalogue.data && (
        <>
          <Card title="Tool catalogue">
            <CatalogueTables catalogue={catalogue.data} />
          </Card>
          <Card title="Connection">
            <ConnectionPanel catalogue={catalogue.data} />
          </Card>
        </>
      )}

      <Card title={integrationsCopy.feedHeading}>
        <p className="mb-2 text-sm text-slate-500">{integrationsCopy.feedIntro}</p>
        <ActivityFeed records={records} />
      </Card>

      <p className="text-sm text-slate-600">
        <Link to="/guide" className="text-blue-700 hover:underline">
          {integrationsCopy.guideLink}
        </Link>
      </p>
    </div>
  )
}

function CatalogueTables({ catalogue }: { catalogue: McpCatalogue }) {
  return (
    <div className="space-y-4">
      <table className="w-full text-left text-sm" aria-label="MCP tools">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1 pr-3">Tool</th>
            <th className="py-1 pr-3">What it does</th>
            <th className="py-1">Kind</th>
          </tr>
        </thead>
        <tbody>
          {catalogue.tools.map((tool) => (
            <ToolRow key={tool.name} tool={tool} />
          ))}
        </tbody>
      </table>
      <p className={typography.caption}>{integrationsCopy.catalogueCaption}</p>

      <table className="w-full text-left text-sm" aria-label="MCP prompts and resources">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1 pr-3">Prompt or resource</th>
            <th className="py-1">What it is for</th>
          </tr>
        </thead>
        <tbody>
          {catalogue.prompts.map((prompt) => (
            <tr key={prompt.name} className="border-t border-slate-200">
              <td className="py-1 pr-3 font-mono text-xs">{prompt.name}</td>
              <td className="py-1">{prompt.description}</td>
            </tr>
          ))}
          {catalogue.resources.map((resource) => (
            <tr key={resource.uri} className="border-t border-slate-200">
              <td className="py-1 pr-3 font-mono text-xs">{resource.uri}</td>
              <td className="py-1">{resource.description}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={typography.caption}>
        {integrationsCopy.promptsCaptionBefore}
        <Link to="/policy" className="text-blue-700 hover:underline">
          {integrationsCopy.promptsCaptionLink}
        </Link>
        {integrationsCopy.promptsCaptionAfter}
      </p>
    </div>
  )
}

function ToolRow({ tool }: { tool: McpTool }) {
  return (
    <tr className="border-t border-slate-200 align-top">
      <td className="py-1 pr-3 font-mono text-xs">{tool.name}</td>
      <td className="py-1 pr-3">{tool.description}</td>
      <td className="py-1">
        {tool.kind === 'read' ? <Badge>read-only</Badge> : <Badge tone="warning">action</Badge>}
      </td>
    </tr>
  )
}

function ConnectionPanel({ catalogue }: { catalogue: McpCatalogue }) {
  const endpointUrl = mcpEndpointUrl()
  const command = integrationsCopy.claudeCodeCommand(endpointUrl)
  return (
    <div className="space-y-3 text-sm">
      {!catalogue.mounted && (
        <p className="rounded bg-amber-50 px-2 py-1 text-amber-800" data-testid="not-configured">
          {integrationsCopy.notConfigured}
        </p>
      )}
      <p className="text-slate-600">{integrationsCopy.permits}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-slate-500">Endpoint</span>
        <span className="break-all font-mono text-xs text-slate-700">{endpointUrl}</span>
        <CopyButton value={endpointUrl} label="Copy URL" />
      </div>
      <div>
        <p className="font-medium">{integrationsCopy.connectorHeading}</p>
        <ol className="list-decimal space-y-0.5 pl-5 text-slate-600">
          {integrationsCopy.connectorSteps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
      <div>
        <p className="font-medium">{integrationsCopy.claudeCodeHeading}</p>
        <div className="mt-1 flex items-start gap-2">
          <pre className="flex-1 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono text-xs text-slate-700">
            {command}
          </pre>
          <CopyButton value={command} label="Copy command" />
        </div>
      </div>
    </div>
  )
}

function ActivityFeed({ records }: { records: ToolCallRecord[] }) {
  if (records.length === 0) {
    return <p className="text-sm text-slate-500">{integrationsCopy.feedEmpty}</p>
  }
  return (
    <table className="w-full text-left text-sm" aria-label="MCP activity">
      <thead className="text-slate-500">
        <tr>
          <th className="py-1 pr-3">When</th>
          <th className="py-1 pr-3">Tool</th>
          <th className="py-1 pr-3">Caller</th>
          <th className="py-1 pr-3">Outcome</th>
          <th className="py-1 pr-3">Latency</th>
          <th className="py-1">Target</th>
        </tr>
      </thead>
      <tbody>
        {records.map((record) => (
          <tr key={record.call_id} className="border-t border-slate-200">
            <td className="py-1 pr-3 font-mono text-xs">{formatTime(record.called_at)}</td>
            <td className="py-1 pr-3 font-mono text-xs">{record.tool}</td>
            <td className="py-1 pr-3">{record.caller}</td>
            <td className="py-1 pr-3">
              {record.outcome === 'ok' ? (
                <Badge tone="success">ok</Badge>
              ) : (
                <Badge tone="danger">{record.error_class ?? 'error'}</Badge>
              )}
            </td>
            <td className="py-1 pr-3 font-mono text-xs">{record.latency_ms}ms</td>
            <td className="py-1">
              <TargetLink record={record} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// A run target links to the audit view of that run (the record carries no claim
// id, so the run page's route cannot be built); a claim target links to the claim.
function TargetLink({ record }: { record: ToolCallRecord }) {
  const target = record.target
  if (!target) return <span className="text-slate-400">—</span>
  const href = target.kind === 'run' ? `/audit?correlation_id=${target.id}` : `/claims/${target.id}`
  return (
    <Link to={href} className="font-mono text-xs text-blue-700 hover:underline">
      {target.kind} {target.id.slice(0, 8)}
    </Link>
  )
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString()
}
