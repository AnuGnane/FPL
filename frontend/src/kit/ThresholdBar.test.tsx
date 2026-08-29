import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ThresholdBar from './ThresholdBar'

describe('ThresholdBar', () => {
  it('reports the value and the threshold', () => {
    render(<ThresholdBar value={8.2} threshold={6} label="Bench boost" />)
    expect(screen.getByText('Bench boost')).toBeInTheDocument()
    expect(screen.getByText('8.2')).toBeInTheDocument()
    expect(screen.getByText(/θ 6.0/)).toBeInTheDocument()
  })

  it('fills sage above the threshold and rust below it', () => {
    const { rerender } = render(<ThresholdBar value={8.2} threshold={6}
                                              label="BB" />)
    expect(screen.getByTestId('threshold-fill')).toHaveClass('bg-sage')
    rerender(<ThresholdBar value={2.0} threshold={6} label="BB" />)
    expect(screen.getByTestId('threshold-fill')).toHaveClass('bg-rust')
  })

  it('clamps the fill width to the bar', () => {
    render(<ThresholdBar value={99} threshold={6} label="BB" />)
    expect(screen.getByTestId('threshold-fill')).toHaveStyle({ width: '100%' })
  })

  it('renders an em dash for a missing value', () => {
    render(<ThresholdBar value={null} threshold={6} label="BB" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
