import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from '../App'
import { guideCopy, guideLinks } from '../copy/guide'
import { renderWithProviders } from '../test/utils'

describe('GuidePage', () => {
  it('renders the six sections, the five steps and the public links with their exact URLs', () => {
    renderWithProviders(<App />, { route: '/guide' })
    expect(screen.getByRole('heading', { name: 'Guide' })).toBeInTheDocument()
    for (const heading of [
      guideCopy.whatHeading,
      guideCopy.howHeading,
      guideCopy.tryHeading,
      guideCopy.scenariosHeading,
      guideCopy.runPageHeading,
      guideCopy.linksHeading,
    ]) {
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
    }

    expect(screen.getByText(/An agentic insurance claims processor/)).toBeInTheDocument()
    expect(within(screen.getByLabelText('The four agents')).getAllByRole('listitem')).toHaveLength(
      4,
    )
    expect(screen.getByText('Preparing the policy.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'the policy wording' })).toHaveAttribute(
      'href',
      '/policy',
    )

    // Five numbered steps; the interface's labels are emphasised, not quoted.
    const steps = within(screen.getByLabelText('Try it steps')).getAllByRole('listitem')
    expect(steps).toHaveLength(5)
    expect(within(steps[1]).getByText('Submit Claim').tagName).toBe('EM')
    expect(screen.getByText('Compare selected').tagName).toBe('EM')

    expect(screen.getByText('Harborline')).toBeInTheDocument()
    expect(screen.getByText(/The four cards are the four agents/)).toBeInTheDocument()

    const links = within(screen.getByLabelText('Guide links'))
    for (const link of guideLinks) {
      expect(links.getByRole('link', { name: link.label })).toHaveAttribute('href', link.href)
    }
    expect(links.getByRole('link', { name: 'The policy' })).toHaveAttribute('href', '/policy')
    expect(links.getByRole('link', { name: /see Integrations/ })).toHaveAttribute(
      'href',
      '/integrations',
    )
  })
})
