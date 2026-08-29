import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Sparkline from './Sparkline'

describe('Sparkline', () => {
  it('draws one polyline point per value', () => {
    const { container } = render(<Sparkline values={[2, 5, 1, 9]} />)
    const points = container.querySelector('polyline')?.getAttribute('points')
    expect(points?.trim().split(/\s+/)).toHaveLength(4)
  })

  it('is sage when the trend rises and rust when it falls', () => {
    const { container, rerender } = render(<Sparkline values={[1, 2, 3, 8]} />)
    expect(container.querySelector('polyline')).toHaveAttribute(
      'stroke', 'var(--color-sage)')
    rerender(<Sparkline values={[8, 3, 2, 1]} />)
    expect(container.querySelector('polyline')).toHaveAttribute(
      'stroke', 'var(--color-rust)')
  })

  it('renders an em dash rather than an empty chart with no data', () => {
    render(<Sparkline values={[]} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('survives a flat series without dividing by zero', () => {
    const { container } = render(<Sparkline values={[4, 4, 4]} />)
    expect(container.querySelector('polyline')?.getAttribute('points'))
      .not.toContain('NaN')
  })
})
