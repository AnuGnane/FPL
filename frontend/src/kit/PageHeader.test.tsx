import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PageHeader from './PageHeader'

describe('PageHeader', () => {
  it('renders the title as the page heading', () => {
    render(<PageHeader title="This Week" />)
    expect(screen.getByRole('heading', { level: 1, name: 'This Week' }))
      .toBeInTheDocument()
  })

  it('renders the context line and the action slot', () => {
    render(
      <PageHeader
        title="This Week"
        context="GW5 · deadline in 2 days"
        action={<button type="button">Run advise</button>}
      />,
    )
    expect(screen.getByText('GW5 · deadline in 2 days')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run advise' }))
      .toBeInTheDocument()
  })

  it('renders without a context line', () => {
    const { container } = render(<PageHeader title="Model" />)
    expect(container.querySelector('[data-testid="page-context"]')).toBeNull()
  })
})
