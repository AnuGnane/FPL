import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import StalenessBanner from './StalenessBanner'
import type { Staleness } from '../types'

const FRESH: Staleness = {
  advice_gw: 2,
  current_gw: 2,
  generated_at: '2026-08-24T20:00:00Z',
  deadline: '2099-08-28T17:30:00Z',
  deadline_passed: false,
  stale: false,
  reason: 'current for GW2',
  data_through_gw: null,
  data_warning: null,
}

const WARNING = 'model has no data for GW1 — FPL usually finalizes it the '
  + 'morning after the last match; re-run gaffer advise after that'

describe('StalenessBanner', () => {
  it('warns when the advice is fresh but built without last GW results', () => {
    const { container } = render(
      <StalenessBanner
        staleness={{ ...FRESH, data_warning: WARNING }}
        onRerun={vi.fn()}
        busy={false}
      />,
    )
    expect(screen.getByText(/no data for GW1/)).toBeInTheDocument()
    // Visually distinct from the stale-advice banner: this one means the
    // advice is current but underinformed.
    expect(container.querySelector('.banner-data')).toBeInTheDocument()
    expect(container.querySelector('.banner-stale')).toBeNull()
  })

  it('renders nothing when the advice is fresh and fully informed', () => {
    const { container } = render(
      <StalenessBanner staleness={FRESH} onRerun={vi.fn()} busy={false} />,
    )
    expect(container.querySelector('.banner-data')).toBeNull()
    expect(container).toBeEmptyDOMElement()
  })

  it('still shows the stale-advice banner, separately', () => {
    const { container } = render(
      <StalenessBanner
        staleness={{
          ...FRESH,
          stale: true,
          current_gw: 3,
          reason: 'this advice is for GW2; GW3 is the next deadline',
          data_warning: WARNING,
        }}
        onRerun={vi.fn()}
        busy={false}
      />,
    )
    expect(container.querySelector('.banner-stale')).toBeInTheDocument()
    expect(container.querySelector('.banner-data')).toBeInTheDocument()
    expect(screen.getByRole('button')).toHaveTextContent('Re-run advice')
  })
})
