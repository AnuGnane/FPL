import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Bar from './Bar'

describe('Bar', () => {
  it('fills the fraction and prints the number beside it', () => {
    render(<Bar fraction={0.74} text="74%" />)
    expect(screen.getByTestId('bar-fill')).toHaveStyle({ width: '74%' })
    expect(screen.getByText('74%')).toHaveClass('tn')
  })

  it('is grey unless a direction is meant', () => {
    const { rerender } = render(<Bar fraction={0.5} />)
    expect(screen.getByTestId('bar-fill')).toHaveClass('bg-text-muted')
    rerender(<Bar fraction={0.5} tone="up" />)
    expect(screen.getByTestId('bar-fill')).toHaveClass('bg-up')
    rerender(<Bar fraction={0.5} tone="down" />)
    expect(screen.getByTestId('bar-fill')).toHaveClass('bg-down')
  })

  it('clamps to the track and draws nothing for a missing value', () => {
    const { rerender } = render(<Bar fraction={3} />)
    expect(screen.getByTestId('bar-fill')).toHaveStyle({ width: '100%' })
    rerender(<Bar fraction={null} text="—" />)
    expect(screen.getByTestId('bar-fill')).toHaveStyle({ width: '0%' })
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('places a mark at a fraction of the ceiling', () => {
    render(<Bar fraction={0.9} mark={0.6} testId="threshold" />)
    expect(screen.getByTestId('threshold-mark')).toHaveStyle({ left: '60%' })
    expect(screen.getByTestId('threshold-fill')).toBeInTheDocument()
  })

  it('has no rounded-full and no gradient', () => {
    const { container } = render(<Bar fraction={0.2} />)
    expect(container.innerHTML).not.toContain('rounded-full')
    expect(container.innerHTML).not.toContain('gradient')
  })
})
