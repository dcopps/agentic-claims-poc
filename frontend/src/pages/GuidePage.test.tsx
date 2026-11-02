import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from '../App'
import { guideLinks } from '../copy/guide'
import { renderWithProviders } from '../test/utils'

describe('GuidePage', () => {
  it('renders the four blocks and the public links with their exact URLs', () => {
    renderWithProviders(<App />, { route: '/guide' })
    expect(screen.getByRole('heading', { name: 'Guide' })).toBeInTheDocument()
    expect(screen.getByText(/It is a prototype in scope/)).toBeInTheDocument()
    expect(screen.getByText('Harborline')).toBeInTheDocument()
    expect(screen.getByText(/The four cards are the four agents/)).toBeInTheDocument()

    const links = within(screen.getByLabelText('Guide links'))
    for (const link of guideLinks) {
      expect(links.getByRole('link', { name: link.label })).toHaveAttribute('href', link.href)
    }
    expect(links.getByRole('link', { name: /see Integrations/ })).toHaveAttribute(
      'href',
      '/integrations',
    )
  })
})
