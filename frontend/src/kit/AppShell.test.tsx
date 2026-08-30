import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AppShell from './AppShell'

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches, media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

afterEach(() => { vi.unstubAllGlobals() })

describe('AppShell', () => {
  it('lists exactly the six hubs', () => {
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    for (const label of ['This Week', 'Planning', 'Players', 'League', 'Live',
      'Model']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(screen.getAllByRole('link')).toHaveLength(6)
  })

  it('renders its children as the page body', () => {
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    expect(screen.getByText('page')).toBeInTheDocument()
  })

  it('is a sidebar on desktop', () => {
    stubMatchMedia(false)
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    expect(screen.getByTestId('nav')).toHaveAttribute('data-mode', 'sidebar')
  })

  it('is a bottom tab bar on mobile', () => {
    stubMatchMedia(true)
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    expect(screen.getByTestId('nav')).toHaveAttribute('data-mode', 'tabbar')
  })

  it('marks the active hub', () => {
    render(
      <MemoryRouter initialEntries={['/planning']}>
        <AppShell><p>page</p></AppShell>
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'Planning' }))
      .toHaveAttribute('aria-current', 'page')
  })

  it('puts the theme control in the sidebar footer on desktop', () => {
    stubMatchMedia(false)
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    const nav = screen.getByTestId('nav')
    expect(within(nav).getByRole('group', { name: 'Theme' }))
      .toBeInTheDocument()
  })

  it('gives the tab bar a seventh, icon-only slot on mobile', () => {
    stubMatchMedia(true)
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    const nav = screen.getByTestId('nav')
    expect(within(nav).getByRole('button', { name: /^Theme: / }))
      .toBeInTheDocument()
    // Still six hubs: the toggle is a button, never a seventh destination.
    expect(within(nav).getAllByRole('link')).toHaveLength(6)
  })
})
