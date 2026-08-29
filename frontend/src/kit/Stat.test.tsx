import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Stat from './Stat'

describe('Stat', () => {
  it('renders label and value, with the value in the mono face', () => {
    render(<Stat label="Expected XI" value="61.5" />)
    expect(screen.getByText('Expected XI')).toBeInTheDocument()
    expect(screen.getByText('61.5')).toHaveClass('num')
  })

  it('colours a positive delta sage and a negative delta rust', () => {
    const { rerender } = render(
      <Stat label="Gap" value="12" delta={2.4} deltaLabel="vs last run" />,
    )
    expect(screen.getByTestId('stat-delta')).toHaveClass('text-sage')
    expect(screen.getByTestId('stat-delta')).toHaveTextContent('+2.4')
    rerender(<Stat label="Gap" value="12" delta={-2.4} deltaLabel="vs last run" />)
    expect(screen.getByTestId('stat-delta')).toHaveClass('text-rust')
    expect(screen.getByTestId('stat-delta')).toHaveTextContent('-2.4')
  })

  it('omits the delta line when there is no delta', () => {
    render(<Stat label="Gap" value="12" />)
    expect(screen.queryByTestId('stat-delta')).toBeNull()
  })

  it('renders a missing value as an em dash rather than NaN', () => {
    render(<Stat label="Gap" value={NaN} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
