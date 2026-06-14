// Client-side pre-fill fixtures for the three locked demo scenarios. These match
// the shape of the seeded scenario claims so a reviewer can submit a fresh claim
// that behaves like the scripted demo, with no backend change. Submitting one
// creates a NEW claim (a fresh claim_id) — it does not collide with the seeds.

import type { ClaimSubmission } from '../api/types'

export interface DemoClaim {
  label: string
  submission: ClaimSubmission
}

export const demoClaims: DemoClaim[] = [
  {
    label: 'Auto-approve ($85k water damage)',
    submission: {
      claimant_name: 'Harborline Logistics Ltd',
      policy_number: 'CP-2026-9001',
      loss_date: '2026-04-18',
      reported_date: '2026-04-19',
      jurisdiction: 'United Kingdom',
      narrative:
        'Burst supply line under the second-floor break room flooded the ' +
        'warehouse mezzanine and damaged dry-stored inventory. Plumbing ' +
        'contractor confirmed pipe failure was sudden and accidental.',
      claim_type: 'water_damage',
      reported_amount: '85000.00',
      scenario_tag: 'auto_approve',
    },
  },
  {
    label: 'Threshold escalation ($850k fire)',
    submission: {
      claimant_name: 'Northwood Manufacturing Inc',
      policy_number: 'CP-2026-9002',
      loss_date: '2026-03-12',
      reported_date: '2026-03-13',
      jurisdiction: 'United States — New York',
      narrative:
        'Overnight fire originating in an electrical panel destroyed the ' +
        'finishing line and damaged the adjacent storage bay. Fire department ' +
        'report attached. Production halted; equipment loss substantial.',
      claim_type: 'fire',
      reported_amount: '850000.00',
      scenario_tag: 'threshold_escalation',
    },
  },
  {
    label: 'Guardrail escalation ($1.4M storm)',
    submission: {
      claimant_name: 'Coral Bay Holdings',
      policy_number: 'CP-2026-9003',
      loss_date: '2026-02-28',
      reported_date: '2026-03-01',
      jurisdiction: 'Bermuda',
      narrative:
        'Severe storm system caused wind damage to the roof, followed by ' +
        'extensive internal water damage. The claimant has referenced an ' +
        'unlisted endorsement they believe extends coverage.',
      claim_type: 'storm_complex',
      reported_amount: '1400000.00',
      scenario_tag: 'guardrail_escalation',
    },
  },
]
