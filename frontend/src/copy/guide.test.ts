import { describe, expect, it } from 'vitest'
import { demoClaims } from '../fixtures/demoClaims'
import { guideCopy, guideLinks, type GuideSegment } from './guide'

// Flattens a "Try it" sentence to the text a reader sees.
const segmentText = (s: GuideSegment): string =>
  typeof s === 'string' ? s : 'link' in s ? s.link : s.label
const sentenceText = (segments: readonly GuideSegment[]): string =>
  segments.map(segmentText).join('')

// The labels a sentence names, in order.
const sentenceLabels = (segments: readonly GuideSegment[]): string[] =>
  segments.flatMap((s) => (typeof s !== 'string' && 'label' in s ? [s.label] : []))

// One sentence: exactly one full stop, question or exclamation mark followed by
// a space or the end. A decimal point ("$1.4M") is not a terminator.
const sentenceCount = (text: string): number => (text.match(/[.!?](?=\s|$)/g) ?? []).length

describe('guide copy', () => {
  it('links to the five public documents with absolute https URLs', () => {
    expect(guideLinks).toHaveLength(5)
    for (const link of guideLinks) expect(link.href).toMatch(/^https:\/\//)
    expect(guideLinks[0].href).toBe(
      'https://dcopps.github.io/agentic-claims-poc/diagrams/Architecture_Diagram.html',
    )
    expect(guideLinks[0].detail).toBe(
      'the production design in four views, the last marking what is built and what stands in',
    )
    expect(guideLinks[1].href).toMatch(/\/docs\/test-evidence\.md$/)
    expect(guideLinks.map((l) => l.label)).toEqual([
      'Interactive architecture diagram',
      'How the system was tested',
      'The build story, phase by phase',
      'The decision register',
      'The repository',
    ])
  })

  it('opens with what the system is and names the four agents in order', () => {
    expect(guideCopy.whatIntro).toContain('agentic insurance claims processor')
    expect(guideCopy.agents.map((a) => a.name)).toEqual([
      'Doc-Parser',
      'Validator',
      'Adjuster',
      'Guardrail',
    ])
    // The Validator names its passages; it does not quote them (plan F4).
    expect(guideCopy.agents[1].detail).toContain('naming the passages it relied on')
    expect(guideCopy.whatScope).toContain('its scope is a prototype’s')
    expect(guideCopy.whatScope).toContain('built and run to production standards')
  })

  it('explains how it works in five parts with the verified numbers', () => {
    expect(guideCopy.how.map((p) => p.lead)).toEqual([
      'Preparing the policy.',
      'Finding the relevant wording.',
      'Deciding.',
      'Recording.',
      'Asking it questions.',
    ])
    const bodies = guideCopy.how.map((p) => sentenceText(p.body))
    expect(bodies[0]).toContain('the policy wording is split into twelve short passages')
    expect(bodies[1]).toContain('three passages closest in meaning')
    expect(bodies[2]).toContain('$250,000')
    expect(bodies[2]).toContain('watchlist')
    expect(bodies[3]).toContain('SHA-256')
    // Prompt 27: "the policy wording" is the one in-app link in How it works.
    expect(guideCopy.how[0].body).toContainEqual({ link: 'the policy wording', to: '/policy' })
  })

  it('gives five one-sentence steps that use the interface’s own labels', () => {
    expect(guideCopy.trySteps).toHaveLength(5)
    for (const step of guideCopy.trySteps) expect(sentenceCount(sentenceText(step))).toBe(1)
    for (const sentence of guideCopy.tryMore) expect(sentenceCount(sentenceText(sentence))).toBe(1)

    // The three demo buttons are named exactly as the form renders them.
    expect(sentenceLabels(guideCopy.trySteps[0])).toEqual(demoClaims.map((d) => d.label))
    expect(sentenceLabels(guideCopy.trySteps[1])).toEqual(['Submit Claim'])
    expect(sentenceLabels(guideCopy.trySteps[2])).toEqual(['Process'])
    expect(sentenceLabels(guideCopy.trySteps[3])).toEqual([])
    expect(sentenceLabels(guideCopy.trySteps[4])).toEqual([
      'View audit log',
      'Verify chain (whole ledger)',
    ])
    expect(sentenceLabels(guideCopy.tryMore[0])).toEqual(['Approve', 'Reject'])
    expect(sentenceLabels(guideCopy.tryMore[1])).toEqual(['Re-process with v2', 'Compare selected'])
  })

  it('names the three scenarios and their expected outcomes', () => {
    expect(guideCopy.scenarios.map((s) => s.name)).toEqual(['Harborline', 'Northwood', 'Coral Bay'])
    expect(guideCopy.scenarios[0].detail).toContain('a little below the claimed amount')
    expect(guideCopy.scenarios[1].detail).toContain('$250,000 ceiling')
    expect(guideCopy.scenarios[2].detail).toContain('Coastal Surge Rider')
    expect(guideCopy.scenarios[2].detail).toContain('demo_fixture: true')
  })

  it('points readers to the Guardrail card for refused objections', () => {
    expect(guideCopy.runPage).toContain('The Guardrail card lists any refused objections')
    expect(guideCopy.runPage).not.toContain('refused claims')
  })

  it('links to the Policy page in the app', () => {
    expect(guideCopy.policyLink).toEqual({
      label: 'The policy',
      detail:
        'the wording every claim is checked against, split into the passages the Validator searches',
      to: '/policy',
    })
  })

  it('warns against real personal details', () => {
    expect(guideCopy.dataNotice).toContain('do not enter real personal details')
    expect(sentenceCount(guideCopy.dataNotice)).toBe(1)
  })
})
