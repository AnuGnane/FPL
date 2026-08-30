import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Loading from './Loading'

describe('Loading', () => {
  it('says Loading inside a card, not on the bare page', () => {
    const { container } = render(<Loading />)
    const text = screen.getByText('Loading…')
    expect(text).toHaveClass('text-text-muted')
    expect(container.querySelector('section.bg-card')).toBeInTheDocument()
  })

  it('names what is being waited on when the page knows', () => {
    render(<Loading label="Solving…" />)
    expect(screen.getByText('Solving…')).toBeInTheDocument()
  })
})
