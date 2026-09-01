import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import QualityTab from './QualityTab'

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

vi.mock('../../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    // The chart itself needs the measured box: cloning it with a fixed one is
    // what the real container does once it has measured.
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 200 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 200 })
          : children}
      </div>
    ),
  }
})

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
    baselines: { last5: table, last38_ppg: table },
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
  news_shadow: {
    run_at: '2026-09-12T00:00:00+00:00', git_sha: 'abc1234', rows: 1400,
    overall: { brier_news: 0.091, brier_flags: 0.102, mae_news: 12.4,
               mae_flags: 14.1, rows: 1400 },
    by_gw: [
      { gw: 3, brier_news: 0.095, brier_flags: 0.11, mae_news: 12.9,
        mae_flags: 14.8, rows: 700, cum_brier_news: 0.095,
        cum_brier_flags: 0.11, cum_mae_news: 12.9, cum_mae_flags: 14.8 },
      { gw: 4, brier_news: 0.087, brier_flags: 0.094, mae_news: 11.9,
        mae_flags: 13.4, rows: 700, cum_brier_news: 0.091,
        cum_brier_flags: 0.102, cum_mae_news: 12.4, cum_mae_flags: 14.1 },
    ],
  },
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(payload)
})

describe('QualityTab', () => {
  it('shows the holdout table beside the baselines', async () => {
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /holdout/i }))
      .toBeInTheDocument()
    expect(screen.getByText(/last-10-slot holdout/i)).toBeInTheDocument()
    expect(screen.getAllByText('Haulers').length).toBeGreaterThan(0)
    expect(screen.getByText(/last-5 mean/i)).toBeInTheDocument()
    expect(screen.getByText(/last-38 mean/i)).toBeInTheDocument()
  })

  it('puts the published numbers next to ours in the benchmark', async () => {
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText('OpenFPL')).toBeInTheDocument()
    expect(screen.getByText('FPL Review')).toBeInTheDocument()
    expect(screen.getByText('5.142')).toBeInTheDocument()
    expect(screen.getByText(/yardstick/i)).toBeInTheDocument()
  })

  it('draws a reliability curve per probability head', async () => {
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByLabelText('P(plays) reliability'))
      .toBeInTheDocument()
    expect(screen.getByLabelText('P(60+ minutes) reliability'))
      .toBeInTheDocument()
    expect(screen.getByLabelText('P(clean sheet) reliability'))
      .toBeInTheDocument()
  })

  it('spells out the two derived decomposition numbers', async () => {
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText('850')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText(/better forecasting/i)).toBeInTheDocument()
    expect(screen.getByText(/multi-week planning/i)).toBeInTheDocument()
    expect(screen.getByText('2700')).toBeInTheDocument()
  })

  it('shows an empty state when nothing has been evaluated yet', async () => {
    apiGet.mockRejectedValue(new FakeApiError(
      422, 'no evaluation on disk — run `gaffer evaluate` first'))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText(/run `gaffer evaluate` first/))
      .toBeInTheDocument()
  })

  it('scores the news layer against the flags per gameweek', async () => {
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /news layer/i }))
      .toBeInTheDocument()
    expect(screen.getByText('GW3')).toBeInTheDocument()
    expect(screen.getByText('GW4')).toBeInTheDocument()
    expect(screen.getByText('0.095')).toBeInTheDocument()
    expect(screen.getByText('0.11')).toBeInTheDocument()
  })

  it('states the verdict in a sentence', async () => {
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText(/news is ahead on both/i))
      .toBeInTheDocument()
  })

  it('hides the section until a gameweek has been scored', async () => {
    apiGet.mockResolvedValue({
      ...payload,
      news_shadow: { run_at: 'x', git_sha: 'y', rows: 0, overall: {},
                     by_gw: [] },
    })
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    await screen.findByRole('heading', { name: /holdout/i })
    expect(screen.queryByRole('heading', { name: /news layer/i }))
      .not.toBeInTheDocument()
  })
})

// Gameweeks 11-13, deliberately clear of the news-shadow fixture's GW3/GW4:
// both sections render "GW{n}" cells into the same document.
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

function routed(penResponse: unknown, reject = false) {
  return (path: string) => {
    if (path !== '/api/pens') return Promise.resolve(payload)
    return reject ? Promise.reject(penResponse) : Promise.resolve(penResponse)
  }
}

describe('QualityTab penalty card', () => {
  it('states the season line', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByRole('heading',
                                   { name: /penalty term — 2026-27/i }))
      .toBeInTheDocument()
    expect(screen.getByText('67%')).toBeInTheDocument()
    expect(screen.getByText('0.150 vs 0.13 served')).toBeInTheDocument()
    expect(screen.getByText('6.1 / 9.6')).toBeInTheDocument()
  })

  it('flags a missed-only week as a floor', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText('floor')).toBeInTheDocument()
    expect(screen.getByText('xg_gap')).toBeInTheDocument()
  })

  it('renders a broken week as an unreadable row', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    const cell = await screen.findByTitle('the week would not read')
    expect(cell).toHaveTextContent('unreadable')
    expect(screen.getByText('GW13')).toBeInTheDocument()
  })

  it('prints the report notes as a footer', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText(/counted from pens_missed only/))
      .toBeInTheDocument()
  })

  it('names the command when no tracker has been written', async () => {
    apiGet.mockImplementation(routed(
      new FakeApiError(422,
                       'no pen tracker report — run `gaffer track-pens` first'),
      true))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText(/no pen tracker report/))
      .toBeInTheDocument()
    expect(screen.getByText('gaffer track-pens')).toBeInTheDocument()
  })

  // A server that cannot answer is not the same as one with nothing to say.
  // The card used to vanish on a 500, which reads as "no penalties tracked"
  // — so the one thing it must do is stay visible and admit the failure,
  // without taking the rest of the tab's numbers down with it.
  it('shows the failure but keeps the rest of the tab on a 500', async () => {
    apiGet.mockImplementation(routed(
      new FakeApiError(500, 'pen tracker blew up'), true))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText('pen tracker blew up')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Holdout' })).toBeInTheDocument()
  })
})

// The v8g cards each have their own fetch, so the mock has to route by path
// rather than answer everything with the quality payload: the whole point of
// the split is that one missing artifact cannot blank another's card.
const RELIABILITY = [{ n: 100, pred: 0.2, obs: 0.25 },
                     { n: 200, pred: 0.9, obs: 0.88 }]

function currentWithHeads(keys: string[]) {
  return {
    ...payload.current,
    heads: Object.fromEntries(keys.map(
      (key) => [key, { log_loss: 0.2732, reliability: RELIABILITY }])),
  }
}

let history: unknown = { runs: [] }
let misses: unknown = { gw: null, rows: [] }
let review: unknown = { gws: [] }

function mockMisses(body: unknown) { misses = body }
function mockReview(body: unknown) { review = body }

function renderQuality(over: { current?: unknown }) {
  apiGet.mockImplementation((path: string) => {
    if (path === '/api/history') return Promise.resolve(history)
    if (path === '/api/review') return Promise.resolve(review)
    if (path === '/api/misses') return Promise.resolve(misses)
    if (path === '/api/pens') {
      return Promise.reject(new FakeApiError(422, 'no pen tracker report'))
    }
    return Promise.resolve(
      over.current === undefined ? payload : { ...payload, current: over.current })
  })
  render(<MemoryRouter><QualityTab /></MemoryRouter>)
}

describe('v8g calibration', () => {
  beforeEach(() => {
    history = { runs: [] }
    misses = { gw: null, rows: [] }
    review = { gws: [] }
  })

  it('draws a reliability curve for p_start, which nothing rendered before',
    async () => {
      renderQuality({ current: currentWithHeads(['p_play', 'p60', 'cs',
                                                 'p_start']) })
      expect(await screen.findByLabelText('P(starts) reliability'))
        .toBeInTheDocument()
    })

  it('omits a head the evaluation does not carry', async () => {
    renderQuality({ current: currentWithHeads(['p_play']) })
    await screen.findByLabelText('P(plays) reliability')
    expect(screen.queryByLabelText('P(starts) reliability')).toBeNull()
  })

  it('says how many observations each curve rests on', async () => {
    renderQuality({ current: currentWithHeads(['p_play']) })
    // The bins carry n; a curve over forty rows and one over forty thousand
    // look identical without it.
    expect(await screen.findByText(/over 300 observations/)).toBeInTheDocument()
  })

  it('plots both axes off the ledger, in the same unit', async () => {
    // B3. Both series are squads hand-scored off the same actuals frame:
    // mine net of hits, and mine with every comparable lane taken from the
    // model. The old card put `advise.raw_xi_pts` — an untilted EP sum over
    // the model's chosen eleven, before captaincy — on one axis and the
    // entry's official net score on the other, and drew a y = x line through
    // them.
    mockReview({ gws: [
      { gw: 1, my_points: 61, model_points: 58, no_advice: false,
        lanes: [], misses: [], notices: [] },
      { gw: 2, my_points: 44, model_points: 52, no_advice: false,
        lanes: [], misses: [], notices: [] },
      { gw: 3, my_points: 39, model_points: null, no_advice: true,
        lanes: [], misses: [], notices: [] },
    ] })
    renderQuality({})
    const chart = await screen.findByLabelText('your points against the '
                                               + 'model’s')
    expect(chart).toBeInTheDocument()
    // GW3's advice was pruned, so there is no model squad to score it
    // against — two graded weeks, not three.
    expect(screen.getByText(/2 graded gameweeks/)).toBeInTheDocument()
  })

  it('keeps the card and states the reason when nothing is graded yet',
     async () => {
    mockReview({ gws: [
      { gw: 1, my_points: 39, model_points: null, no_advice: true,
        lanes: [], misses: [], notices: [] }] })
    renderQuality({})
    expect(await screen.findByText(/No graded gameweek yet/))
      .toBeInTheDocument()
    expect(screen.queryByLabelText('your points against the model’s'))
      .toBeNull()
  })

  it('will not draw a trend through a single point', async () => {
    mockReview({ gws: [
      { gw: 1, my_points: 61, model_points: 58, no_advice: false,
        lanes: [], misses: [], notices: [] }] })
    renderQuality({})
    expect(await screen.findByText(/1 graded gameweek so far/))
      .toBeInTheDocument()
    expect(screen.queryByLabelText('your points against the model’s'))
      .toBeNull()
  })

  it('lists the biggest misses with their sign', async () => {
    mockMisses({ gw: 5, rows: [
      { code: 11, name: 'Saka', position: 'MID', price: 10.0, ep: 5.5,
        actual: 16, minutes: 90, miss: 10.5 },
      { code: 22, name: 'Sub', position: 'FWD', price: 6.0, ep: 7.0,
        actual: 1, minutes: 12, miss: -6.0 },
    ] })
    renderQuality({})
    expect(await screen.findByText('Saka')).toBeInTheDocument()
    expect(screen.getByText('+10.5')).toBeInTheDocument()
    expect(screen.getByText('-6.0')).toBeInTheDocument()
  })

  it('renders no misses card when no week has been scored', async () => {
    mockMisses({ gw: null, rows: [] })
    renderQuality({})
    await screen.findByText(/Nothing evaluated yet|Holdout/)
    expect(screen.queryByText(/Biggest misses/)).toBeNull()
  })

  it('names the command that grades a gameweek in the scatter empty state',
    async () => {
      mockReview({ gws: [] })
      renderQuality({})
      expect(await screen.findByText(/No graded gameweek yet/))
        .toBeInTheDocument()
      expect(screen.getAllByText('gaffer review').length).toBeGreaterThan(0)
    })

  it('keeps the two states that were already right', async () => {
    // Audited 2026-08-31 and left alone (plan A12): title, detail and an
    // action that is a real command. Pinned so a later pass does not "fix"
    // them into prose.
    mockMisses({ gw: null, rows: [] })
    renderQuality({})
    expect((await screen.findAllByTestId('empty-state')).length)
      .toBeGreaterThan(0)
  })
})

// The v9d card. Its own fetch, its own empty state, and a footer that is as
// much the point as the table: a calibration report whose omissions and
// exclusions are hidden is a plausible-looking grade of hindsight.
const CAL_HEAD = {
  status: 'scored', n: 400, brier: 0.1234, log_loss: 0.4,
  reliability: [{ n: 200, pred: 0.2, obs: 0.25 },
                { n: 200, pred: 0.9, obs: 0.88 }],
}
const CAL_INSUFFICIENT = {
  status: 'insufficient', n: 12, brier: null, log_loss: null, reliability: [],
}

function calibrationPayload(over: Record<string, unknown> = {}) {
  return {
    available: true, run_at: '2026-09-01T00:00:00Z', git_sha: 'abc1234',
    season: '2025-26',
    // p_cs has no per-gameweek entry: one clean sheet per club-fixture is
    // about twenty rows a week, under the report's sample floor.
    gameweeks: [{ gw: 1, n: 400,
                  heads: { p_play: CAL_HEAD, p60: CAL_HEAD,
                           p_haul: CAL_INSUFFICIENT } }],
    cumulative: { p_play: CAL_HEAD, p60: CAL_HEAD, p_cs: CAL_HEAD,
                  p_haul: CAL_INSUFFICIENT },
    omitted: { p_start: 'not banked' },
    per_gw_omitted: { p_cs: 'graded per club-fixture — scored in the '
                            + 'cumulative row only' },
    excluded: [{ gw: 2, reason: 'written after kickoff' }],
    missing: [3],
    note: null,
    ...over,
  }
}

function renderWithCalibration(calibration: unknown, reject = false) {
  apiGet.mockImplementation((path: string) => {
    if (path === '/api/model/calibration') {
      return reject ? Promise.reject(calibration as Error)
        : Promise.resolve(calibration)
    }
    if (path === '/api/history') return Promise.resolve({ runs: [] })
    if (path === '/api/review') return Promise.resolve({ gws: [] })
    if (path === '/api/misses') return Promise.resolve({ gw: null, rows: [] })
    if (path === '/api/pens') {
      return Promise.reject(new FakeApiError(422, 'no pen tracker report'))
    }
    return Promise.resolve(payload)
  })
  render(<MemoryRouter><QualityTab /></MemoryRouter>)
}

describe('v9d calibration by gameweek', () => {
  it('prints the server’s own sentence when nothing has been graded',
    async () => {
      renderWithCalibration({
        available: false, run_at: null, git_sha: null, season: null,
        gameweeks: [], cumulative: {}, omitted: {}, per_gw_omitted: {},
        excluded: [], missing: [],
        note: 'Run `gaffer evaluate --calibration` after a graded gameweek.',
      })
      expect(await screen.findByText(/after a graded gameweek/))
        .toBeInTheDocument()
      // CLI-only: JOB_KINDS maps a kind to a zero-argument callable, so there
      // is no flag a button could pass.
      expect(screen.getByText('gaffer evaluate --calibration'))
        .toBeInTheDocument()
    })

  it('renders one row per graded gameweek with each head’s Brier',
    async () => {
      renderWithCalibration(calibrationPayload())
      expect(await screen.findByRole('heading',
                                     { name: 'Calibration by gameweek' }))
        .toBeInTheDocument()
      expect(screen.getByRole('rowheader', { name: 'GW1' })).toBeInTheDocument()
      expect(screen.getAllByText('0.1234').length).toBeGreaterThan(0)
    })

  it('says "not enough data" rather than leaving a blank cell', async () => {
    // A blank reads as "perfect" at a glance, which is the worst possible
    // default for a calibration table.
    renderWithCalibration(calibrationPayload())
    expect((await screen.findAllByText(/not enough data \(12\)/)).length)
      .toBeGreaterThan(0)
  })

  it('shows p_cs cumulatively rather than a column of refusals', async () => {
    // Twenty club-fixtures a gameweek against a thirty-row floor: a per-week
    // p_cs column could only ever read "not enough data", which looks like a
    // fault in the model rather than arithmetic about the grain.
    renderWithCalibration(calibrationPayload())
    expect(await screen.findByText('cumulative only')).toBeInTheDocument()
    expect(screen.getByText(/Per gameweek: p_cs/)).toBeInTheDocument()
  })

  it('names the omitted head and why it is omitted', async () => {
    renderWithCalibration(calibrationPayload())
    expect(await screen.findByText(/Omitted: p_start — not banked/))
      .toBeInTheDocument()
  })

  it('shows an excluded gameweek with its reason', async () => {
    renderWithCalibration(calibrationPayload())
    expect(await screen.findByText(/Excluded: GW2 — written after kickoff/))
      .toBeInTheDocument()
    expect(screen.getByText(/No banked components: GW3/)).toBeInTheDocument()
  })

  it('does not take the tab down when its own fetch fails', async () => {
    renderWithCalibration(new FakeApiError(500, 'calibration blew up'), true)
    expect(await screen.findByText('calibration blew up')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Holdout' })).toBeInTheDocument()
  })

  it('keeps the two calibration cards distinctly titled', async () => {
    // The tab already had a card titled "Calibration" — the holdout curves.
    // Two cards with one name showing different things is worse than either.
    renderWithCalibration(calibrationPayload())
    // Awaited on the *new* card's heading. "Calibration" resolves off the
    // /api/quality payload, which is already in hand when this test starts:
    // awaiting it would let both counts run before /api/model/calibration
    // had resolved, and the pass would say nothing about the second card.
    expect(await screen.findByRole('heading',
                                   { name: 'Calibration by gameweek' }))
      .toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: 'Calibration' }))
      .toHaveLength(1)
    expect(screen.getAllByRole('heading',
                               { name: 'Calibration by gameweek' }))
      .toHaveLength(1)
  })
})
