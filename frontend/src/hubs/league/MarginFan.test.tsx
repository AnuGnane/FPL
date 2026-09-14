import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarginFan from './MarginFan'

// The fan the sim card draws, moved beside it in v18f §2.1 out of
// `League.test.tsx`, which keeps every case about the card around it. The
// quantiles are the ones that hub's `SIM` fixture carries, so the moved case
// asserts on the same five numbers it always did.

const QUANTILES = { p05: -60, p25: -12, p50: 18, p75: 50, p95: 120 }

describe('the margin fan', () => {
  it('renders the margin fan the engine has always published', () => {
    render(<MarginFan quantiles={QUANTILES} />)
    expect(screen.getByTestId('sim-margin-fan')).toBeInTheDocument()
    expect(screen.getByTestId('margin-p05')).toHaveTextContent('-60')
    expect(screen.getByTestId('margin-p50')).toHaveTextContent('18')
    expect(screen.getByTestId('margin-p95')).toHaveTextContent('120')
    // The fan straddles zero here, so the reader is shown where it is.
    expect(screen.getByTestId('sim-margin-zero')).toBeInTheDocument()
  })

  it('leaves zero off a fan that does not straddle it', () => {
    render(<MarginFan quantiles={{ p05: 4, p25: 9, p50: 18, p75: 50,
                                   p95: 120 }} />)
    expect(screen.getByTestId('sim-margin-fan')).toBeInTheDocument()
    expect(screen.queryByTestId('sim-margin-zero')).toBeNull()
  })

  it('draws nothing at all when a centile is missing or not finite', () => {
    // Five numbers or none: a strip drawn from four of them is a range whose
    // ends are a guess.
    const { container } = render(<MarginFan quantiles={{ p05: -60, p25: -12,
                                                         p50: 18, p75: 50 }} />)
    expect(container).toBeEmptyDOMElement()
  })
})
