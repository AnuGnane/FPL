import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PensSection from './PensSection'

// Moved beside the section in v18f §2.1, with the fixture the tab's own file
// used to hold for it. The one case that is really about the *tab* — that a
// 500 here leaves the holdout card standing — stays in `QualityTab.test.tsx`,
// because that claim cannot be made from here.

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

vi.mock('../../../api/client', () => ({
  ApiError: FakeApiError,
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const pens = {
  season: '2026-27',
  gws: [
    { gw: 11, instrument: 'xg_gap', rows: 520, covered_rows: 498,
      team_games: 10, component_rows: 520, predicted_ep_pen_taker: 3.2,
      predicted_takers: 12, pens_taken: 2, pens_by_first_choice: 2,
      taker_hit_rate: 1, pens_per_team_game: 0.2, realized_pen_points: 6.4 },
    { gw: 12, instrument: 'pens_missed_only', rows: 515, covered_rows: 0,
      team_games: 10, component_rows: 515, predicted_ep_pen_taker: 2.9,
      predicted_takers: 12, pens_taken: 1, pens_by_first_choice: 0,
      taker_hit_rate: 0, pens_per_team_game: 0.1, realized_pen_points: 3.2 },
    { gw: 13, error: 'the week would not read' },
  ],
  season_totals: {
    gws: 2, instruments: ['pens_missed_only', 'xg_gap'], team_games: 20,
    predicted_ep_pen_taker: 6.1, pens_taken: 3, pens_by_first_choice: 2,
    taker_hit_rate: 0.667, pens_per_team_game: 0.15,
    league_pens_pg_served: 0.13, realized_pen_points: 9.6,
  },
  notes: ['penalties counted from pens_missed only'],
}

function serve(penResponse: unknown, reject = false) {
  apiGet.mockImplementation(() => (
    reject ? Promise.reject(penResponse) : Promise.resolve(penResponse)))
}

beforeEach(() => {
  apiGet.mockReset()
  serve(pens)
})

describe('the penalty card', () => {
  it('states the season line', async () => {
    render(<PensSection />)
    expect(await screen.findByRole('heading',
                                   { name: /penalty term — 2026-27/i }))
      .toBeInTheDocument()
    expect(screen.getByText('67%')).toBeInTheDocument()
    expect(screen.getByText('0.150 vs 0.13 served')).toBeInTheDocument()
    expect(screen.getByText('6.1 / 9.6')).toBeInTheDocument()
  })

  it('flags a missed-only week as a floor', async () => {
    render(<PensSection />)
    expect(await screen.findByText('floor')).toBeInTheDocument()
    expect(screen.getByText('xg_gap')).toBeInTheDocument()
  })

  it('renders a broken week as an unreadable row', async () => {
    render(<PensSection />)
    const cell = await screen.findByTitle('the week would not read')
    expect(cell).toHaveTextContent('unreadable')
    expect(screen.getByText('GW13')).toBeInTheDocument()
  })

  it('prints the report notes as a footer', async () => {
    render(<PensSection />)
    expect(await screen.findByText(/counted from pens_missed only/))
      .toBeInTheDocument()
  })

  it('names the command when no tracker has been written', async () => {
    serve(new FakeApiError(
      422, 'no pen tracker report — run `gaffer track-pens` first'), true)
    render(<PensSection />)
    expect(await screen.findByText(/no pen tracker report/))
      .toBeInTheDocument()
    expect(screen.getByText('gaffer track-pens')).toBeInTheDocument()
  })
})
