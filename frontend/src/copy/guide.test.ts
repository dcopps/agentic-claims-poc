import { describe, expect, it } from 'vitest'
import { guideCopy, guideLinks } from './guide'

// The Guide is one screen by design; the budget keeps a later edit honest.
const ONE_SCREEN_BUDGET_CHARS = 2200

describe('guide copy', () => {
  it('links to the four public documents with absolute https URLs', () => {
    expect(guideLinks).toHaveLength(4)
    for (const link of guideLinks) expect(link.href).toMatch(/^https:\/\//)
    expect(guideLinks[0].href).toBe(
      'https://dcopps.github.io/agentic-claims-poc/diagrams/Architecture_Diagram.html',
    )
    expect(guideLinks.map((l) => l.label)).toEqual([
      'Interactive architecture diagram',
      'The build story, phase by phase',
      'The decision register',
      'The repository',
    ])
  })

  it('opens with the glossary definition of the system', () => {
    expect(guideCopy.what).toContain('It is a prototype in scope')
    expect(guideCopy.what).toContain('built and operated to production standards')
  })

  it('names the three scenarios and their expected outcomes', () => {
    expect(guideCopy.scenarios.map((s) => s.name)).toEqual(['Harborline', 'Northwood', 'Coral Bay'])
    expect(guideCopy.scenarios[0].detail).toContain('a little below the claimed amount')
    expect(guideCopy.scenarios[1].detail).toContain('$250,000 ceiling')
    expect(guideCopy.scenarios[2].detail).toContain('Coastal Surge Rider')
  })

  it('points readers to the Guardrail card for refused claims', () => {
    expect(guideCopy.runPage).toContain('The Guardrail card lists any refused claims')
  })

  it('stays within one screen', () => {
    const total =
      guideCopy.what.length +
      guideCopy.runPage.length +
      guideCopy.scenarios.reduce((n, s) => n + s.name.length + s.detail.length, 0)
    expect(total).toBeLessThan(ONE_SCREEN_BUDGET_CHARS)
  })
})
