// The Policy page's text, reviewed as prose (Prompt 27). The page shows the
// policy as it is indexed — the passages the Validator's similarity search runs
// over — so the opening says which representation the reader is looking at.
// Counts, the model and the source come from the endpoint, never from here.

export const policyCopy = {
  title: 'Policy',
  opening:
    'This is the commercial property policy excerpt the system checks claims against. It is ' +
    'a sample written for the demonstration, not a real policy. It is shown here split into ' +
    'the passages the Validator searches: when a claim is processed, the three passages ' +
    'closest in meaning to the claim’s description are retrieved and given to the Validator, ' +
    'and nothing else.',
  // The count line, from the endpoint's own figures.
  countLine: (count: number, source: string, model: string): string =>
    `${count} ${count === 1 ? 'passage' : 'passages'} from ${source}, embedded with ${model}.`,
  // The small label on each passage (D5: no token count).
  passageLabel: (section: string, position: number, size: number): string =>
    `${section}, passage ${position} of ${size}`,
  empty:
    'No policy is indexed on this deployment, so there is nothing to show here, and the ' +
    'Validator cannot run until one has been indexed.',
  loadFailed: 'Could not load the policy.',
} as const
