import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReviewData } from '../../types'
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
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
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

// `/api/review` is answered separately from the quality payload because the
// two are different models. `ReviewData.gws` is required on the wire — the
// route returns `{gws: [], summary: null}` on an empty ledger — so the scatter
// section reads it unguarded, and a blanket `mockResolvedValue(payload)` hands
// it a body with no such key.
const EMPTY_REVIEW: ReviewData = { gws: [], summary: null }

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation((path: string) => Promise.resolve(
    path === '/api/review' ? EMPTY_REVIEW : payload))
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
    apiGet.mockImplementation((path: string) => Promise.resolve(
      path === '/api/review' ? EMPTY_REVIEW : {
        ...payload,
        news_shadow: { run_at: 'x', git_sha: 'y', rows: 0, overall: {},
                       by_gw: [] },
      }))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    await screen.findByRole('heading', { name: /holdout/i })
    expect(screen.queryByRole('heading', { name: /news layer/i }))
      .not.toBeInTheDocument()
  })

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
  }

  const PRESSER = {
    run_at: 'now', git_sha: 'abc1234', available: true, rows: 4, note: null,
    verdicts_banked: 9, graded_gws: [3], absent_rows: 3,
    confusion: [{ verdict: 'ruled_out', n: 4, started: 1, not_started: 3 }],
    per_class: [{ verdict: 'ruled_out', n: 4, precision: 0.75, recall: 1 }],
    by_source: [{ source: 'premierinjuries', rows: 4 }],
    recall_population: 'verdict-carrying rows',
  }

  it('draws the lead-time histogram and the worst late flags', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/quality'
        ? Promise.resolve({ flag_latency: FLAG_LATENCY })
        : Promise.reject(new FakeApiError(422, 'nothing'))))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /availability signal/i }))
      .toBeInTheDocument()
    expect(screen.getByTestId('lead-bucket-1-2d')).toHaveTextContent('1')
    expect(screen.getByTestId('late-flag-3-7')).toHaveTextContent('started')
    expect(screen.getByTestId('late-flag-3-9'))
      .toHaveTextContent('did not start')
  })

  it('says what it is waiting for instead of drawing zeros', async () => {
    // Spec §1. The bar chart of an empty histogram is a row of zeroes that
    // reads as "nothing ever changed", which is a measurement nobody made.
    apiGet.mockImplementation((path: string) => (
      path === '/api/quality'
        ? Promise.resolve({
          flag_latency: {
            ...FLAG_LATENCY, available: false, rows: 0, snap_dates: 3,
            checked_covered_gws: [], histogram: [], late_flags: [],
            note: '3 of 14 snapshot days banked, and 0 covered gameweek(s) '
              + 'graded.',
          },
        })
        : Promise.reject(new FakeApiError(422, 'nothing'))))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByTestId('flag-latency-empty'))
      .toHaveTextContent('3 of 14 snapshot days')
    expect(screen.queryByTestId('lead-bucket-1-2d')).toBeNull()
  })

  it('withholds the tables on an open gate with nothing in them', async () => {
    // available && rows === 0 is a real state — fourteen days banked, a
    // gameweek graded, and not one status moved in it. Three empty tables
    // under a headline of "0 status changes" is the same row of zeroes as
    // above, so the sentence stands in for them here too.
    apiGet.mockImplementation((path: string) => (
      path === '/api/quality'
        ? Promise.resolve({
          flag_latency: {
            ...FLAG_LATENCY, rows: 0, histogram: [], late_flags: [],
          },
        })
        : Promise.reject(new FakeApiError(422, 'nothing'))))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /availability signal/i }))
      .toBeInTheDocument()
    expect(screen.getByTestId('flag-latency-empty'))
      .toHaveTextContent(/no status change/i)
    expect(screen.queryByTestId('lead-bucket-1-2d')).toBeNull()
  })

  it('prints precision per verdict class with its denominator', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/quality'
        ? Promise.resolve({ presser_grades: PRESSER })
        : Promise.reject(new FakeApiError(422, 'nothing'))))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    const row = await screen.findByTestId('verdict-ruled_out')
    expect(row).toHaveTextContent('0.75')
    expect(row).toHaveTextContent('4')
    expect(screen.getByTestId('presser-recall-note'))
      .toHaveTextContent('verdict-carrying rows')
  })

  it('draws no availability card at all on an artifact without the keys',
     async () => {
       // The default fixture is every other quality key and neither of these
       // two, which is what every artifact banked before this cycle looks
       // like. Awaited on a heading that fixture definitely renders, so the
       // absence below is checked after the payload has landed.
       render(<MemoryRouter><QualityTab /></MemoryRouter>)
       await screen.findByRole('heading', { name: /holdout/i })
       expect(screen.queryByText('Availability signal')).toBeNull()
     })
})

// The card's own cases moved to `quality/PensSection.test.tsx` in v18f §2.1;
// what is left here is the one claim about the *tab* — a section that fails
// takes nothing else down with it.
function routed(penResponse: unknown, reject = false) {
  return (path: string) => {
    if (path === '/api/review') return Promise.resolve(EMPTY_REVIEW)
    if (path !== '/api/pens') return Promise.resolve(payload)
    return reject ? Promise.reject(penResponse) : Promise.resolve(penResponse)
  }
}

describe('QualityTab penalty card', () => {
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

  // The scatter's four cases and the misses card's two moved beside their
  // sections in v18f §2.1 (`quality/ScatterSection.test.tsx`,
  // `quality/MissesSection.test.tsx`); the reliability cases above belong to
  // `CurrentSection`, which still lives in the tab.

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
  // The card's own six cases moved to `quality/CalibrationSection.test.tsx`
  // in v18f §2.1. The two below are claims about the tab around it and can
  // only be made from here.

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
