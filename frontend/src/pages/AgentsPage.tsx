import { AgentTestPanel } from '../components/AgentTestPanel'

const DOC_SAMPLE = JSON.stringify(
  { narrative: 'Burst supply line flooded the warehouse floor; loss ~USD 85,000.' },
  null,
  2,
)

const VALIDATOR_SAMPLE = JSON.stringify(
  {
    narrative: 'Burst supply line flooded the warehouse floor.',
    claim_type: 'water_damage',
  },
  null,
  2,
)

const ADJUSTER_SAMPLE = JSON.stringify(
  {
    doc_parser_output: {
      loss_date: '2026-04-18',
      jurisdiction: 'United Kingdom',
      claim_type: 'water_damage',
      claimed_amount: '85000.00',
      claimant_identifier: 'Acme Ltd',
      narrative_summary: 'Burst supply line flooded the floor.',
    },
    validator_verdict: {
      covered: true,
      confidence: 0.9,
      reasoning: 'Covered peril.',
      policy_basis: 'Section 4',
      cited_chunks: [{ chunk_id: '00000000-0000-0000-0000-000000000001', section: 'Section 4' }],
    },
  },
  null,
  2,
)

const GUARDRAIL_SAMPLE = JSON.stringify(
  {
    adjuster_output: {
      recommended_settlement: '85000.00',
      confidence: 0.9,
      reasoning: 'Within the market range.',
    },
    retrieved_chunks: [
      {
        chunk_id: '00000000-0000-0000-0000-000000000001',
        section: 'Section 4',
        content: 'Water damage that is sudden and accidental is covered.',
        similarity: 0.9,
      },
    ],
  },
  null,
  2,
)

export function AgentsPage() {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        The agent test bench invokes one agent on arbitrary input. Calls are
        out-of-band: no claim is touched and <strong>no audit entry is written</strong>{' '}
        — only an API-logger record. Edit the JSON request and run.
      </p>
      <AgentTestPanel
        agent="doc-parser"
        label="Doc-Parser"
        sample={DOC_SAMPLE}
        note="Generates a narrative summary. Structured fields are populated from sentinel values in the test bench (the live pipeline uses the claim record's structured columns)."
      />
      <AgentTestPanel agent="validator" label="Validator" sample={VALIDATOR_SAMPLE} />
      <AgentTestPanel agent="adjuster" label="Adjuster" sample={ADJUSTER_SAMPLE} />
      <AgentTestPanel agent="guardrail" label="Guardrail" sample={GUARDRAIL_SAMPLE} />
    </div>
  )
}
