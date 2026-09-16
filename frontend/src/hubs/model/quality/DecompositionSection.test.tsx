import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { DecompositionData } from '../../../types'
import DecompositionSection from './DecompositionSection'

// Moved beside the section in v19h §2.1.

const decomposition = {
  run_at: '2026-08-25T02:00:00+00:00', git_sha: 'abc1234',
  season: '2025-26', start_gw: 5,
  cells: {
    model_h1: { total: 1800, per_gw: 52.94, hits: 4 },
    model_h3: { total: 1850, per_gw: 54.41, hits: 3 },
    oracle_h1: { total: 2600, per_gw: 76.47, hits: 0 },
    oracle_h3: { total: 2700, per_gw: 79.41, hits: 0 },
  },
  forecast_gap_h3: 850, planning_ceiling: 100,
} as DecompositionData

describe('DecompositionSection', () => {
  it('spells out the two derived decomposition numbers', () => {
    render(<DecompositionSection decomposition={decomposition} />)
    expect(screen.getByText('850')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText(/better forecasting/i)).toBeInTheDocument()
    expect(screen.getByText(/multi-week planning/i)).toBeInTheDocument()
    expect(screen.getByText('2700')).toBeInTheDocument()
  })
})
