import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Card from './Card'

describe('Card', () => {
  it('renders its children inside a bordered surface', () => {
    const { container } = render(<Card><p>inside</p></Card>)
    expect(screen.getByText('inside')).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('border-border')
    expect(container.firstChild).toHaveClass('bg-card')
  })

  it('renders a header row with a title and an action slot', () => {
    render(
      <Card title="Squad" action={<button type="button">Refresh</button>}>
        <p>inside</p>
      </Card>,
    )
    expect(screen.getByRole('heading', { name: 'Squad' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })

  it('omits the header row entirely when there is no title or action', () => {
    render(<Card><p>inside</p></Card>)
    expect(screen.queryByRole('heading')).toBeNull()
  })

  it('renders the title as a small uppercase label by default', () => {
    render(<Card title="Squad"><p>inside</p></Card>)
    expect(screen.getByRole('heading', { name: 'Squad' }))
      .toHaveClass('label')
  })

  it('renders the title at primary text size when asked', () => {
    render(<Card title="Saka" titleSize="lg"><p>inside</p></Card>)
    const heading = screen.getByRole('heading', { name: 'Saka' })
    expect(heading).toHaveClass('text-lg')
    expect(heading).toHaveClass('text-text')
    expect(heading).not.toHaveClass('label')
  })

  it('keeps the action slot beside a large title', () => {
    render(
      <Card title="Saka" titleSize="lg" action={<span>MID</span>}>
        <p>inside</p>
      </Card>,
    )
    expect(screen.getByText('MID')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Saka' })).toBeInTheDocument()
  })
})
