// Prose for the Integrations page and the Run Detail "copy question" button,
// kept here so it can be reviewed as text. The token never appears in any of
// it: every snippet carries the placeholder below, and the page never fetches
// the real value. Phase 10.

export const TOKEN_PLACEHOLDER = '<MCP shared token>'

export const integrationsCopy = {
  title: 'Integrations',
  intro:
    'An AI client such as Claude can ask this system questions through the Model Context ' +
    'Protocol (MCP) and receive answers taken from the audit trail. Every answer comes ' +
    'from recorded data; nothing here asks a model to judge a claim again.',
  permits:
    'The server reads claims, runs, the audit trail and the chain check, and can run the ' +
    'three scripted scenarios. It cannot approve or reject a claim, touch the agent test ' +
    'bench, or reach the database any other way. In production this endpoint would sit ' +
    'behind API Management with Entra sign-in; the shared token is the prototype’s stand-in.',
  notConfigured:
    'The MCP endpoint is not configured on this deployment (no shared token is set), so ' +
    'nothing can connect to it; the catalogue below shows what it would offer.',
  catalogueCaption: 'Generated from the server’s own definitions.',
  // The caption's "the policy excerpt" is a link to the Policy page (Prompt 27).
  promptsCaptionBefore:
    'Prompts are ready-made questions the client offers its user; the resource is ',
  promptsCaptionLink: 'the policy excerpt',
  promptsCaptionAfter: ' the Validator searches.',
  connectorHeading: 'Connect Claude (custom connector)',
  connectorSteps: [
    'In Claude, open Customize › Connectors and choose Add custom connector.',
    'Name it, paste the endpoint URL below, and choose No sign-in.',
    `Under Request headers add authorization with the value Bearer ${TOKEN_PLACEHOLDER}.`,
    'Save, then enable the connector in a chat and ask it to list the claims.',
  ],
  claudeCodeHeading: 'Or connect Claude Code',
  claudeCodeCommand: (endpointUrl: string): string =>
    `claude mcp add-json agentic-claims '{"type":"http","url":"${endpointUrl}",` +
    `"headers":{"Authorization":"Bearer ${TOKEN_PLACEHOLDER}"}}'`,
  feedHeading: 'Live activity',
  feedIntro:
    'Every tool call an AI client makes is recorded with its tool, arguments, target, caller, ' +
    'outcome and latency. The newest appears first.',
  feedEmpty: 'No tool calls yet.',
  guideLink: 'New here? Read the Guide.',
  copyQuestion: (correlationId: string): string =>
    `Using the claims MCP server, explain run ${correlationId} and tell me whether its ` +
    'audit chain verifies.',
} as const
