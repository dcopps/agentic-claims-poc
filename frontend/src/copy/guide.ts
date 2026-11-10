// The Guide page's text, reviewed as prose: what the system is, how it works,
// how to try it, the three scenarios, how to read a run page, and the links.
// `whatIntro` followed by `whatScope` is the glossary's definition of the
// system in docs/decision-register.md and docs/prompts/README.md, so the page
// and the plain-language documents say the same thing; the agent list is the
// Guide's alone. Phase 10; rewritten by Prompt 26; Policy links added by Prompt 27.
//
// "Try it" names buttons and links exactly as the components render them. The
// three demo-button labels are asserted against fixtures/demoClaims.ts by the
// copy test, so a renamed button fails the suite rather than dating the Guide.

/** A piece of a Guide sentence: plain text, a label the interface shows, or an in-app link. */
export type GuideSegment =
  | string
  | { readonly label: string }
  | { readonly link: string; readonly to: string }

export const REPOSITORY_URL = 'https://github.com/dcopps/agentic-claims-poc'

export const guideLinks = [
  {
    label: 'Interactive architecture diagram',
    detail:
      'the production design in four views, the last marking what is built and what stands in',
    href: 'https://dcopps.github.io/agentic-claims-poc/diagrams/Architecture_Diagram.html',
  },
  {
    label: 'How the system was tested',
    detail: 'the plan, the tests and the result for every phase',
    href: `${REPOSITORY_URL}/blob/main/docs/test-evidence.md`,
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
  whatIntro: 'An agentic insurance claims processor. Four AI agents handle a claim in turn:',
  agents: [
    {
      name: 'Doc-Parser',
      detail: 'reads the claim and writes a short summary of what happened.',
    },
    {
      name: 'Validator',
      detail:
        'finds the relevant passages of the policy and decides whether the loss is covered, ' +
        'naming the passages it relied on.',
    },
    {
      name: 'Adjuster',
      detail:
        'proposes a settlement figure within the market range for that type of loss, and gives ' +
        'its reasoning.',
    },
    {
      name: 'Guardrail',
      detail:
        'checks the Adjuster’s output for personal data, biased language and references to ' +
        'policy wording that does not exist.',
    },
  ],
  whatRules:
    'A set of rules then decides the outcome: the claim settles, or it goes to a person for ' +
    'review. Every step is recorded in an audit trail that shows if anything has been altered.',
  whatScope:
    'The claims are synthetic and the policy is a short excerpt, so its scope is a prototype’s. ' +
    'It is built and run to production standards: deployed on Azure, tested, audited and ' +
    'change-controlled.',

  howHeading: 'How it works',
  how: [
    {
      lead: 'Preparing the policy.',
      body: [
        'Before any claim arrives, ',
        { link: 'the policy wording', to: '/policy' },
        ' is split into twelve short passages. An ' +
          'embedding model turns each passage into a vector, a list of numbers that represents ' +
          'its meaning. The passages and their vectors are stored in the database.',
      ],
    },
    {
      lead: 'Finding the relevant wording.',
      body: [
        'When a claim is processed, the same embedding model turns the claim’s description into ' +
          'a vector. The database compares it with the stored vectors and returns the three ' +
          'passages closest in meaning. The Validator is given those three passages and nothing ' +
          'else, so its decision can only cite wording it was actually shown. The same model must ' +
          'be used for both steps, or the comparison would be meaningless.',
      ],
    },
    {
      lead: 'Deciding.',
      body: [
        'The Adjuster’s figure and the Guardrail’s findings are tested against the escalation ' +
          'policy, a configuration file kept apart from the program code. A settlement over ' +
          '$250,000, low confidence from the Validator or Adjuster, or a Guardrail failure sends ' +
          'the claim to a person. Otherwise it settles. Three further rules in the same file, for ' +
          'a claimant or claim type on a watchlist and for a claim that spans more than one ' +
          'jurisdiction, also send a claim to a person; the watchlists are empty here.',
      ],
    },
    {
      lead: 'Recording.',
      body: [
        'Each step writes a row to the audit trail: what the agent was asked, what it answered, ' +
          'and which rules fired. Each row carries a SHA-256 hash, a short code calculated from ' +
          'the row’s contents and the hash of the row before it. Changing or removing any row ' +
          'breaks every hash after it. One click checks the whole trail.',
      ],
    },
    {
      lead: 'Asking it questions.',
      body: [
        'An AI assistant such as Claude can connect to the system and ask why a claim settled or ' +
          'escalated. The answer is read from the audit trail, never worked out afresh.',
      ],
    },
  ],

  tryHeading: 'Try it',
  // Each step is one sentence, written as segments: plain text, and the
  // interface's own labels, which the page renders in `<em>`.
  trySteps: [
    [
      'On the Claims page, press one of the three buttons above the form, ',
      { label: 'Auto-approve ($85k water damage)' },
      ', ',
      { label: 'Threshold escalation ($850k fire)' },
      ' or ',
      { label: 'Guardrail escalation ($1.4M storm)' },
      ', and the form fills in with that scenario.',
    ],
    ['Press ', { label: 'Submit Claim' }, ', and the claim appears in the list below.'],
    [
      'Press ',
      { label: 'Process' },
      ' on its row: the run page opens and the four agent cards fill in as each agent finishes.',
    ],
    [
      'Read the run page: the status badge is the outcome, and each card opens to show what ' +
        'the agent was asked and what it answered.',
    ],
    [
      'Press ',
      { label: 'View audit log' },
      ', then ',
      { label: 'Verify chain (whole ledger)' },
      ', to check every recorded step against its hash.',
    ],
  ],
  tryMore: [
    [
      'To decide an escalated claim, open it from the Claims list by the claimant’s name and use ',
      { label: 'Approve' },
      ' or ',
      { label: 'Reject' },
      ' in the Human review panel.',
    ],
    [
      'To see the same claim handled a second way, press ',
      { label: 'Re-process with v2' },
      ' on its row, which runs the Validator under a stricter instruction, then open the ' +
        'claim, tick the two runs and press ',
      { label: 'Compare selected' },
      '.',
    ],
  ],

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
        'the ceiling too. That citation is planted: for this scenario the Adjuster’s answer ' +
        'comes from a fixed file rather than the model, so the run behaves the same every time, ' +
        'and the audit trail records it as demo_fixture: true.',
    },
  ],

  runPageHeading: 'Reading a run page',
  runPage:
    'The four cards are the four agents in order: Doc-Parser, Validator, Adjuster, Guardrail. ' +
    'Each shows what it produced and how long it took, and opens to show the recorded request ' +
    'and response. The status badge is the run’s outcome: settled, awaiting human, or aborted. ' +
    '“View audit log” opens every recorded step of the run with its hash. The Guardrail card ' +
    'lists any refused objections: things the model said were policy citations that the code ' +
    'could not find in the Adjuster’s text, each with the reason it did not count.',

  linksHeading: 'Links',
  // An in-app link, rendered with <Link> like the Integrations line (Prompt 27).
  policyLink: {
    label: 'The policy',
    detail:
      'the wording every claim is checked against, split into the passages the Validator searches',
    to: '/policy',
  },
  integrationsLink: 'Connect an AI client: see Integrations.',

  // Shown on the Claims page above the form, the first line a visitor reads.
  dataNotice:
    'The claims here are synthetic and this site is open to anyone with the address, so do not ' +
    'enter real personal details.',
} as const
