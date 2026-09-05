import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Bar from './Bar'
import Stat from './Stat'

describe('Stat', () => {
  it('renders label and value, the value tabular at 22px', () => {
    render(<Stat label="Expected XI" value="61.5" />)
    expect(screen.getByText('Expected XI')).toHaveClass('label')
    expect(screen.getByText('61.5')).toHaveClass('tn')
    expect(screen.getByText('61.5').parentElement).toHaveClass('text-[22px]')
  })

  it('prints the unit beside the value and one context line under it', () => {
    render(<Stat label="Expected XI" value="61.5" unit="pts"
                 context="raw model points" />)
    expect(screen.getByText('pts')).toHaveClass('text-text-muted')
    expect(screen.getByText('raw model points')).toHaveClass('text-xs')
  })

  it('takes a name as a value like any other', () => {
    render(<Stat label="Captain" value="Guéhi" context="55% of sims · vice Semenyo" />)
    expect(screen.getByText('Guéhi')).toHaveClass('tn')
  })

  it('mounts a meter under the context line', () => {
    render(<Stat label="Next chip" value="BB" unit="GW5"
                 meter={<Bar fraction={0.9} mark={0.5} testId="threshold" />} />)
    expect(screen.getByTestId('threshold-fill')).toBeInTheDocument()
  })

  it('colours a positive delta up and a negative delta down', () => {
    const { rerender } = render(
      <Stat label="Gap" value="12" delta={2.4} deltaLabel="vs last run" />,
    )
    expect(screen.getByTestId('stat-delta')).toHaveClass('text-up')
    expect(screen.getByTestId('stat-delta')).toHaveTextContent('+2.4')
    rerender(<Stat label="Gap" value="12" delta={-2.4} deltaLabel="vs last run" />)
    expect(screen.getByTestId('stat-delta')).toHaveClass('text-down')
  })

  it('omits the delta line when there is no delta', () => {
    render(<Stat label="Gap" value="12" />)
    expect(screen.queryByTestId('stat-delta')).toBeNull()
  })

  it('renders a missing value as an em dash rather than NaN', () => {
    render(<Stat label="Gap" value={NaN} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('draws no card box of its own', () => {
    const { container } = render(<Stat label="Gap" value="12" />)
    expect((container.firstChild as HTMLElement).className)
      .not.toMatch(/border|rounded|bg-card/)
  })
})
