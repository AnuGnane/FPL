import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Quality from './Quality'

const { FakeApiError, apiGet } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown

    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn() }
})

vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const table = {
  zeros: { rmse: 0.9, mae: 0.4, n: 900 },
  blanks: { rmse: 1.4, mae: 0.8, n: 400 },
  tickers: { rmse: 1.6, mae: 1.2, n: 200 },
  haulers: { rmse: 5.3, mae: 4.4, n: 100 },
  all: { rmse: 2.1, mae: 1.0, n: 1600 },
}

const payload = {
  current: {
    run_at: '2026-08-25T00:00:00+00:00', git_sha: 'abc1234',
    holdout_slots: 10,
    stratified: { all: table, starters: table },
    heads: {
      p_play: {
        log_loss: 0.2732,
        reliability: [{ n: 40, pred: 0.9, obs: 0.88 },
                      { n: 60, pred: 0.2, obs: 0.25 }],
      },
      p60: { log_loss: 0.2563, reliability: [{ n: 10, pred: 0.5, obs: 0.5 }] },
      cs: { log_loss: 0.5511, reliability: [{ n: 10, pred: 0.3, obs: 0.28 }] },
    },
    baselines: { last5: table, season_ppg: table },
  },
  benchmark: {
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
  },
  decomposition: {
    run_at: '2026-08-25T02:00:00+00:00', git_sha: 'abc1234',
    season: '2025-26', start_gw: 5,
    cells: {
      model_h1: { total: 1800, per_gw: 52.94, hits: 4 },
      model_h3: { total: 1850, per_gw: 54.41, hits: 3 },
      oracle_h1: { total: 2600, per_gw: 76.47, hits: 0 },
      oracle_h3: { total: 2700, per_gw: 79.41, hits: 0 },
    },
    forecast_gap_h3: 850, planning_ceiling: 100,
  },
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(payload)
})

describe('Quality', () => {
  it('shows the holdout table beside the baselines', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /model quality/i }))
      .toBeInTheDocument()
    expect(screen.getByText(/last-10-slot holdout/i)).toBeInTheDocument()
    expect(screen.getAllByText('Haulers').length).toBeGreaterThan(0)
    expect(screen.getByText(/last-5 mean/i)).toBeInTheDocument()
    expect(screen.getByText(/season ppg/i)).toBeInTheDocument()
  })

  it('puts the published numbers next to ours in the benchmark', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByText('OpenFPL')).toBeInTheDocument()
    expect(screen.getByText('FPL Review')).toBeInTheDocument()
    expect(screen.getByText('5.142')).toBeInTheDocument()
    expect(screen.getByText(/yardstick/i)).toBeInTheDocument()
  })

  it('draws a reliability curve per probability head', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByLabelText('P(plays) reliability'))
      .toBeInTheDocument()
    expect(screen.getByLabelText('P(60+ minutes) reliability'))
      .toBeInTheDocument()
    expect(screen.getByLabelText('P(clean sheet) reliability'))
      .toBeInTheDocument()
  })

  it('spells out the two derived decomposition numbers', async () => {
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByText('850')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText(/better forecasting/i)).toBeInTheDocument()
    expect(screen.getByText(/multi-week planning/i)).toBeInTheDocument()
    expect(screen.getByText('2700')).toBeInTheDocument()
  })

  it('shows an empty state when nothing has been evaluated yet', async () => {
    apiGet.mockRejectedValue(new FakeApiError(
      422, 'no evaluation on disk — run `gaffer evaluate` first'))
    render(<MemoryRouter><Quality /></MemoryRouter>)
    expect(await screen.findByText(/run `gaffer evaluate` first/))
      .toBeInTheDocument()
  })
})
