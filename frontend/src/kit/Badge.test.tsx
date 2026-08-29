import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Badge from './Badge'

describe('Badge', () => {
  it('maps each variant to its meaning colour', () => {
    const { rerender } = render(<Badge variant="positive">C</Badge>)
    expect(screen.getByText('C')).toHaveClass('text-sage')
    rerender(<Badge variant="negative">Doubt</Badge>)
    expect(screen.getByText('Doubt')).toHaveClass('text-rust')
    rerender(<Badge variant="info">Pens</Badge>)
    expect(screen.getByText('Pens')).toHaveClass('text-info')
    rerender(<Badge variant="neutral">WC</Badge>)
    expect(screen.getByText('WC')).toHaveClass('text-text-muted')
  })

  it('defaults to the neutral variant', () => {
    render(<Badge>BB</Badge>)
    expect(screen.getByText('BB')).toHaveClass('text-text-muted')
  })

  it('exposes a title for hover context', () => {
    render(<Badge variant="negative" title="Knock - 75% chance">75%</Badge>)
    expect(screen.getByTitle('Knock - 75% chance')).toBeInTheDocument()
  })
})
