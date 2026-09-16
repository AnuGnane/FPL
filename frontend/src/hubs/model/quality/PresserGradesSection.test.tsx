import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PresserGradesData } from '../../../types'
import PresserGradesSection from './PresserGradesSection'

// Moved beside the section in v19h §2.1.

const PRESSER = {
  run_at: 'now', git_sha: 'abc1234', available: true, rows: 4, note: null,
  verdicts_banked: 9, graded_gws: [3], absent_rows: 3,
  confusion: [{ verdict: 'ruled_out', n: 4, started: 1, not_started: 3 }],
  per_class: [{ verdict: 'ruled_out', n: 4, precision: 0.75, recall: 1 }],
  by_source: [{ source: 'premierinjuries', rows: 4 }],
  recall_population: 'verdict-carrying rows',
} as PresserGradesData

describe('PresserGradesSection', () => {
  it('prints precision per verdict class with its denominator', () => {
    render(<PresserGradesSection data={PRESSER} />)
    const row = screen.getByTestId('verdict-ruled_out')
    expect(row).toHaveTextContent('0.75')
    expect(row).toHaveTextContent('4')
    expect(screen.getByTestId('presser-recall-note'))
      .toHaveTextContent('verdict-carrying rows')
  })

  it('dashes the recall of a gameweek with no absences among the graded', () => {
    // 0.00 beside a class that found none of nothing reads as a class that
    // missed everything.
    render(<PresserGradesSection data={{ ...PRESSER, absent_rows: 0 }} />)
    expect(screen.getByTestId('verdict-ruled_out')).toHaveTextContent('—')
  })
})
