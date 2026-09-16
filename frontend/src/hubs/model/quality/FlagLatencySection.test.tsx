import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FlagLatencyData } from '../../../types'
import FlagLatencySection from './FlagLatencySection'

// Moved beside the section in v19h §2.1. Whether the card around it is drawn
// at all is the tab's decision and is tested there.

const FLAG_LATENCY = {
  run_at: 'now', git_sha: 'abc1234', available: true, rows: 2, note: null,
  snap_dates: 15, min_snap_dates: 14, covered_gws: [3],
  checked_covered_gws: [3],
  histogram: [{ bucket: '1-2d', started: 1, missed: 1 },
              { bucket: '3-5d', started: 3, missed: 0 }],
  // Both directions of disagreement, because both are late flags: the log
  // said 'i' and he started, and the log said 'a' and he did not.
  late_flags: [{ gw: 3, code: 7, first_change: '2026-09-03',
                 lead_days: 1, from_status: 'a', final_status: 'i',
                 chance_of_playing: 0, started: true },
               { gw: 3, code: 9, first_change: '2026-09-02',
                 lead_days: 2, from_status: 'i', final_status: 'a',
                 chance_of_playing: 100, started: false }],
} as FlagLatencyData

describe('FlagLatencySection', () => {
  it('draws the lead-time histogram and the worst late flags', () => {
    render(<FlagLatencySection data={FLAG_LATENCY} />)
    expect(screen.getByTestId('lead-bucket-1-2d')).toHaveTextContent('1')
    expect(screen.getByTestId('late-flag-3-7')).toHaveTextContent('started')
    expect(screen.getByTestId('late-flag-3-9'))
      .toHaveTextContent('did not start')
  })

  it('says what it is waiting for instead of drawing zeros', () => {
    // Spec §1. The bar chart of an empty histogram is a row of zeroes that
    // reads as "nothing ever changed", which is a measurement nobody made.
    render(<FlagLatencySection data={{
      ...FLAG_LATENCY, available: false, rows: 0, snap_dates: 3,
      checked_covered_gws: [], histogram: [], late_flags: [],
      note: '3 of 14 snapshot days banked, and 0 covered gameweek(s) graded.',
    }} />)
    expect(screen.getByTestId('flag-latency-empty'))
      .toHaveTextContent('3 of 14 snapshot days')
    expect(screen.queryByTestId('lead-bucket-1-2d')).toBeNull()
  })

  it('withholds the tables on an open gate with nothing in them', () => {
    // available && rows === 0 is a real state — fourteen days banked, a
    // gameweek graded, and not one status moved in it. Three empty tables
    // under a headline of "0 status changes" is the same row of zeroes as
    // above, so the sentence stands in for them here too.
    render(<FlagLatencySection data={{
      ...FLAG_LATENCY, rows: 0, histogram: [], late_flags: [],
    }} />)
    expect(screen.getByTestId('flag-latency-empty'))
      .toHaveTextContent(/no status change/i)
    expect(screen.queryByTestId('lead-bucket-1-2d')).toBeNull()
  })
})
