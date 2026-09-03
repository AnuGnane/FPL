import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FieldPanel from './FieldPanel'
import type { FieldRank } from '../../types'

const base: FieldRank = {
  gw: 6, n: 2000, seed: 20260831, managers: 300, eo_source: 'last-sample',
  eo_gw: 5, field_draws: 8, unsampled_picks: 0,
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

  it('reads a negative slope as better and a positive one as worse', () => {
    // The sign is the whole meaning: overall rank counts *down*, so a
    // negative slope is points buying places. Rendering Math.abs() alone
    // turned a squad that was sliding into one that was climbing.
    const { unmount } = render(
      <FieldPanel field={{ ...base, p_green: 0.5, rank_slope: -18400,
                           rank_slope_rows: 6 }} />)
    expect(screen.getByText(/18,400 places per point better/)).toBeInTheDocument()
    unmount()
    render(<FieldPanel field={{ ...base, p_green: 0.5, rank_slope: 18400,
                                rank_slope_rows: 6 }} />)
    expect(screen.getByText(/18,400 places per point worse/)).toBeInTheDocument()
  })

  it('names the gameweek the EO was drawn from, which is not this one', () => {
    render(<FieldPanel field={{ ...base, gw: 6, eo_gw: 5, p_green: 0.5 }} />)
    expect(screen.getByText(/EO drawn from GW 5/)).toBeInTheDocument()
  })

  it('counts the field draws in the provenance line', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5 }} />)
    expect(screen.getByText(/n=2000 × 8 field draws/)).toBeInTheDocument()
  })

  it('says when the sample never saw some of my players', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5, unsampled_picks: 3 }} />)
    expect(screen.getByText(/3 of your players/)).toBeInTheDocument()
  })

  it('says nothing about unsampled players when there are none', () => {
    render(<FieldPanel field={{ ...base, p_green: 0.5 }} />)
    expect(screen.queryByText(/of your players/)).toBeNull()
  })

  it('falls back to "not computed" when there is no reason either', () => {
    render(<FieldPanel field={{ ...base, p_green: null, waiting_for: null }} />)
    expect(screen.getByText('not computed')).toBeInTheDocument()
    expect(screen.queryByText('0%')).toBeNull()
  })

  it('renders nothing at all when the simulation could not be built', () => {
    const { container } = render(<FieldPanel field={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
