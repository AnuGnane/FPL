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
})
