import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { BenchmarkEvaluation } from '../../../types'
import BenchmarkSection from './BenchmarkSection'

// Moved beside the section in v19h §2.1: the card takes its benchmark by
// props, so the case needs no fetch and no tab around it.

const table = {
  zeros: { rmse: 0.9, mae: 0.4, n: 900 },
  blanks: { rmse: 1.4, mae: 0.8, n: 400 },
  tickers: { rmse: 1.6, mae: 1.2, n: 200 },
  haulers: { rmse: 5.3, mae: 4.4, n: 100 },
  all: { rmse: 2.1, mae: 1.0, n: 1600 },
}

const benchmark = {
  run_at: '2026-08-25T01:00:00+00:00', git_sha: 'abc1234',
  test_season: '2024-25',
  stratified: { all: table },
  references: {
    openfpl: {
      zeros: { rmse: 0.818, mae: 0.427 },
      blanks: { rmse: 1.291, mae: 0.749 },
      tickers: { rmse: 1.517, mae: 1.127 },
      haulers: { rmse: 5.142, mae: 4.317 },
    },
    fplreview: {
      zeros: { rmse: 0.689, mae: 0.237 },
      blanks: { rmse: 1.189, mae: 0.597 },
      tickers: { rmse: 1.594, mae: 1.227 },
      haulers: { rmse: 5.172, mae: 4.381 },
    },
  },
  caveat: 'Treat these as a yardstick, not a controlled comparison.',
} as BenchmarkEvaluation

describe('BenchmarkSection', () => {
  it('puts the published numbers next to ours in the benchmark', () => {
    render(<BenchmarkSection benchmark={benchmark} />)
    expect(screen.getByText('OpenFPL')).toBeInTheDocument()
    expect(screen.getByText('FPL Review')).toBeInTheDocument()
    expect(screen.getByText('5.142')).toBeInTheDocument()
    expect(screen.getByText(/yardstick/i)).toBeInTheDocument()
  })
})
