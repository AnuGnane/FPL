import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { FlagLatencyData } from '../../../types'
import AvailabilitySection from './AvailabilitySection'

// Holiday F-154: the card cut from `QualityTab.tsx` in v19h §2.1 draws its
// heading always and each section only when its payload arrived.

const FLAG_LATENCY = {
  run_at: 'now', git_sha: 'abc1234', available: true, rows: 1, note: null,
  snap_dates: 15, min_snap_dates: 14, covered_gws: [3],
  checked_covered_gws: [3],
  histogram: [{ bucket: '1-2d', started: 1, missed: 1 }],
  late_flags: [],
} as FlagLatencyData

describe('AvailabilitySection', () => {
  it('draws its heading with neither section when both payloads are null', () => {
    render(<AvailabilitySection flag={null} presser={null} />)
    expect(screen.getByText('Availability signal')).toBeInTheDocument()
    expect(screen.queryByTestId('lead-bucket-1-2d')).toBeNull()
  })

  it('draws the flag-latency section when its payload arrived', () => {
    render(<AvailabilitySection flag={FLAG_LATENCY} presser={null} />)
    expect(screen.getByText('Availability signal')).toBeInTheDocument()
    expect(screen.getByTestId('lead-bucket-1-2d')).toBeInTheDocument()
  })
})
