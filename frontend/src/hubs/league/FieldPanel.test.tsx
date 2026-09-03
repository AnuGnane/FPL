import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FieldPanel from './FieldPanel'
import type { FieldRank } from '../../types'

const base: FieldRank = {
  gw: 6, n: 2000, seed: 20260831, managers: 300, eo_source: 'last-sample',
  p_green: null, waiting_for: null,
  p_top10k: null, top10k_waiting_for: null,
  rank_slope: null, rank_slope_rows: 0, rank_waiting_for: null,
  my_ep: null, field_median_ep: null,
}

describe('FieldPanel', () => {
  it('renders the green-arrow probability when there is one', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.62, my_ep: 54.1,
                                field_median_ep: 51.3 }} />)
    expect(screen.getByText('62%')).toBeInTheDocument()
    expect(screen.getByText(/300 simulated managers/)).toBeInTheDocument()
    expect(screen.getByText(/last-sample/)).toBeInTheDocument()
  })

  it('says what it is waiting for instead of rendering a zero', () => {
    render(<FieldPanel field={{ ...base, waiting_for: 'a banked field EO sample for this gameweek — run `gaffer field-scrape`' }} />)
    expect(screen.queryByText('0%')).toBeNull()
    expect(screen.getByText(/gaffer field-scrape/)).toBeInTheDocument()
  })

  it('says why P(top-10k) is absent rather than omitting the row', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5,
                                top10k_waiting_for: 'a top-10k weekly score threshold' }} />)
    expect(screen.getByText(/top-10k weekly score threshold/)).toBeInTheDocument()
  })

  it('says how many graded gameweeks the rank slope still needs', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5, rank_slope_rows: 2,
                                rank_waiting_for: '2 of 5 graded gameweeks' }} />)
    expect(screen.getByText(/2 of 5 graded gameweeks/)).toBeInTheDocument()
  })

  it('renders the rank slope once it exists', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5, rank_slope: -18400,
                                rank_slope_rows: 6 }} />)
    expect(screen.getByText(/18,400 places per point/)).toBeInTheDocument()
  })

  it('renders nothing at all when the simulation could not be built', () => {
    const { container } = render(<FieldPanel field={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
