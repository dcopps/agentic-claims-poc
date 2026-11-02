// The Guide page's text: one screen for a first-time visitor, reviewed as prose.
// The opening paragraph is the glossary's definition of the system, so the page
// and the plain-language documents say the same thing. Phase 10.

export const REPOSITORY_URL = 'https://github.com/dcopps/agentic-claims-poc'

export const guideLinks = [
  {
    label: 'Interactive architecture diagram',
    detail: 'the production target, with a clickable claim journey',
    href: 'https://dcopps.github.io/agentic-claims-poc/diagrams/Architecture_Diagram.html',
  },
  {
    label: 'The build story, phase by phase',
    detail: 'what each phase set out to do and delivered',
    href: `${REPOSITORY_URL}/blob/main/docs/prompts/README.md`,
  },
  {
    label: 'The decision register',
    detail: 'every incident and every decision taken at a gate',
    href: `${REPOSITORY_URL}/blob/main/docs/decision-register.md`,
  },
  { label: 'The repository', detail: 'the code, the tests and the archive', href: REPOSITORY_URL },
] as const

export const guideCopy = {
  title: 'Guide',
  whatHeading: 'What this is',
  what:
    'The working claims-handling system this project built. It is a prototype in scope, ' +
    'with synthetic claims and a short policy excerpt, and it is built and operated to ' +
    'production standards: deployed on two clouds, audited, verified and change-controlled. ' +
    'It reads a claim, checks it against the policy, proposes a settlement, checks that ' +
    'proposal, and either settles the claim or hands it to a person, with every step ' +
    'recorded in a tamper-evident audit trail.',
  scenariosHeading: 'The three scenarios',
  scenarios: [
    {
      name: 'Harborline',
      detail:
        'water damage, $85,000. Should settle on its own, at a figure a little below the ' +
        'claimed amount: covered, inside the market range, nothing for the Guardrail to object to.',
    },
    {
      name: 'Northwood',
      detail:
        'fire, $850,000. Should go to a person because the proposed settlement is above the ' +
        '$250,000 ceiling.',
    },
    {
      name: 'Coral Bay',
      detail:
        'storm, $1.4M. Should go to a person because the Guardrail finds the Adjuster citing a ' +
        '“Coastal Surge Rider” endorsement the policy does not contain, and the amount is over ' +
        'the ceiling too.',
    },
  ],
  runPageHeading: 'Reading a run page',
  runPage:
    'The four cards are the four agents in order: Doc-Parser, Validator, Adjuster, Guardrail. ' +
    'Each shows what it produced and how long it took, and opens to show the recorded request ' +
    'and response. The status badge is the run’s outcome: settled, awaiting human, or aborted. ' +
    '“View audit log” opens every recorded step of the run with its hash. The Guardrail card ' +
    'lists any refused claims: things the model said were policy citations that the code could ' +
    'not find in the Adjuster’s text, each with the reason it did not count.',
  linksHeading: 'Links',
  integrationsLink: 'Connect an AI client: see Integrations.',
} as const
