import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SeasonTab from './SeasonTab'

const { apiGet, ApiError } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
}))

vi.mock('../../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
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

const LANES = ['transfers', 'captaincy', 'bench', 'chip']

function lane(over: Record<string, number> = {}) {
  return { pts: 0, pwin: 0, graded: 0, wins: 0, losses: 0, ...over }
}

function summary(over: Record<string, unknown> = {}) {
  return {
    gws: [1], lanes: Object.fromEntries(LANES.map((n) => [n, lane()])),
    accuracy: [], points_on_bench: 2, points_on_bench_gws: 1,
    hindsight_gap: 0, hindsight_gap_gws: 0, reconciled_gws: 1,
    unreconciled_gws: 0, best: null, worst: null, ...over,
  }
}

function gw(over: Record<string, unknown> = {}) {
  return {
    gw: 1, reviewed_at: null, no_advice: false, post_deadline: false,
    my_points: 61, official_points: 61, official_gross: 61, hits: 0,
    reconciled: true, chip: null, model_chip: null, points_on_bench: 2,
    overall_rank: null, our_bench_points: 0, model_points: null,
    accuracy: null, pwin_n: null, pwin_seed: null,
    pwin_granularity_pp: null,
    lanes: LANES.map((n) => ({ lane: n, delta_pts: null, delta_pwin: null,
                               label: null, aligned: false, mine: null,
                               model: null, note: null })),
    misses: [], hindsight: { points: null, xi: [], captain: null, gap: null },
    notices: [], ...over,
  }
}

function head(brier: number | null, status = 'scored') {
  return { status, brier, n: 400, bins: [] }
}

const CALIBRATION = {
  available: true, run_at: '2026-09-01T09:00:00Z', git_sha: 'abc',
  season: '2026-27',
  gameweeks: [
    { gw: 1, n: 400, heads: { p_play: head(0.11), p60: head(0.19),
                              p_haul: head(0.08) } },
    { gw: 2, n: 400, heads: { p_play: head(0.10), p60: head(null, 'thin'),
                              p_haul: head(0.07) } },
    { gw: 3, n: 400, heads: { p_play: head(0.09), p60: head(0.17),
                              p_haul: head(0.06) } },
  ],
  cumulative: {},
  omitted: {},
  per_gw_omitted: { p_cs: 'about twenty clean sheets a gameweek, under the '
    + 'sample floor' },
  excluded: [], missing: [], note: null,
}

/** `/api/review` and `/api/model/calibration` are two fetches now; every test
 *  states both, so a failure names which artifact it meant. */
function wire(review: unknown, calibration: unknown = CALIBRATION) {
  apiGet.mockImplementation((path: string) => (
    path.startsWith('/api/model/calibration')
      ? Promise.resolve(calibration)
      : Promise.resolve(review)))
}

beforeEach(() => {
  apiGet.mockReset()
  wire({ gws: [], summary: null })
})

describe('SeasonTab, empty — which is the state it is in today', () => {
  it('names the gate: GW2 data_checked, banked by the Tuesday job',
    async () => {
      render(<SeasonTab />)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
      expect(screen.getByText(/GW2 data_checked/)).toBeInTheDocument()
      expect(screen.getByText(/automatically/)).toBeInTheDocument()
    })

  it('is still empty on the real one-row ledger, where every lane is ungraded',
    async () => {
      // Plan A14, measured off reports/decision_ledger.json: one row, four
      // null lanes, no accuracy, two points on the bench.
      wire({ gws: [gw()], summary: summary() })
      render(<SeasonTab />)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    })

  it('renders an empty state on a cold clone with no console error',
    async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      apiGet.mockRejectedValue(new ApiError('nothing on disk'))
      render(<SeasonTab />)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })
})

describe('SeasonTab, filled', () => {
  const GRADED = {
    gws: [gw({ gw: 1, accuracy: 7, overall_rank: 412233 }),
          gw({ gw: 2, accuracy: 6, overall_rank: null,
               points_on_bench: 4 }),
          gw({ gw: 3, accuracy: 8, overall_rank: 300100,
               points_on_bench: 1 })],
    summary: summary({
      gws: [1, 2, 3],
      lanes: { ...Object.fromEntries(LANES.map((n) => [n, lane()])),
               transfers: lane({ pts: 4, graded: 3, wins: 1, losses: 1 }) },
      accuracy: [{ gw: 1, accuracy: 7 }, { gw: 2, accuracy: 6 },
                 { gw: 3, accuracy: 8 }],
      points_on_bench: 7, points_on_bench_gws: 3,
    }),
  }

  beforeEach(() => { wire(GRADED) })

  it('renders a lane record over graded, never over wins plus losses',
    async () => {
      render(<SeasonTab />)
      const tile = await screen.findByTestId('season-lane-transfers')
      // 1 win, 1 loss, 3 graded: the third week is one I did what the model
      // did, and 50% would silently drop it.
      expect(tile).toHaveTextContent('1/3 won')
      expect(tile).not.toHaveTextContent('50%')
    })

  it('says "never graded" for a lane nothing has measured', async () => {
    render(<SeasonTab />)
    const tile = await screen.findByTestId('season-lane-chip')
    expect(tile).toHaveTextContent('never graded')
    expect(tile).not.toHaveTextContent('0/0')
  })

  it('draws the accuracy series nothing has ever rendered', async () => {
    const { container } = render(<SeasonTab />)
    await screen.findByTestId('season-lane-transfers')
    expect(screen.queryByTestId('accuracy-empty')).toBeNull()
    expect(container.querySelectorAll('.recharts-line-curve').length)
      .toBeGreaterThan(0)
  })

  it('draws a null rank as a gap, not a line through it', async () => {
    const { container } = render(<SeasonTab />)
    await screen.findByTestId('season-lane-transfers')
    const chart = container.querySelector(
      '[aria-label="Overall rank by gameweek"]')
    expect(chart).not.toBeNull()
    // Two real ranks either side of a null: recharts splits the path rather
    // than interpolating, which is the whole point — a straight line through
    // a missing rank is the most confident lie this view could tell.
    const curves = chart!.querySelectorAll('.recharts-line-curve')
    const segments = [...curves].reduce(
      (n, path) => n + (path.getAttribute('d') ?? '').split('M').length - 1, 0)
    expect(segments).toBe(2)
  })

  it('says how many graded gameweeks carry a rank at all', async () => {
    render(<SeasonTab />)
    await screen.findByTestId('season-lane-transfers')
    expect(screen.getByText(/2 of 3 graded gameweek/)).toBeInTheDocument()
  })

  // `season-lane-transfers` is the *review* fetch landing; the trend is a
  // second fetch in a child component, so waiting on the first says nothing
  // about the second. Every assertion below waits on the caption the trend
  // itself renders — the one thing on the page that cannot exist until that
  // fetch has resolved.
  const trendDrawn = () => screen.findByText(/Brier score per head/)

  it('draws one calibration line per head with a per-gameweek column',
    async () => {
      const { container } = render(<SeasonTab />)
      await trendDrawn()
      const chart = container.querySelector(
        '[aria-label="Calibration trend by gameweek"]')
      expect(chart).not.toBeNull()
      // p_play, p60 and p_haul are drawn; p_cs has no per-gameweek column, so
      // it has no line — drawing it at zero would read as perfect
      // calibration.
      expect(chart!.querySelectorAll('.recharts-line')).toHaveLength(3)
    })

  it('names the omitted head in the caption rather than drawing it at zero',
    async () => {
      render(<SeasonTab />)
      await trendDrawn()
      expect(screen.getByText(/No per-gameweek column for p_cs/))
        .toBeInTheDocument()
      expect(screen.getByText(/under the sample floor/)).toBeInTheDocument()
    })

  it('draws a null Brier as a gap, same rule as the rank', async () => {
    const { container } = render(<SeasonTab />)
    await trendDrawn()
    const chart = container.querySelector(
      '[aria-label="Calibration trend by gameweek"]')
    const segments = [...chart!.querySelectorAll('.recharts-line-curve')]
      .map((path) => (path.getAttribute('d') ?? '').split('M').length - 1)
    // p60 is null in GW2, so exactly one of the three lines is split.
    expect(segments.filter((n) => n === 2)).toHaveLength(1)
  })

  it('prints the server’s own note when there is no report', async () => {
    wire(GRADED, { ...CALIBRATION, available: false, gameweeks: [],
      note: 'Run `gaffer evaluate --calibration` after a graded gameweek' })
    render(<SeasonTab />)
    expect(await screen.findByTestId('calibration-note'))
      .toHaveTextContent('Run `gaffer evaluate --calibration` after a '
        + 'graded gameweek')
  })

  it('leaves the rest of the dashboard drawn when calibration fails',
    async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      apiGet.mockImplementation((path: string) => (
        path.startsWith('/api/model/calibration')
          ? Promise.reject(new ApiError('no evaluation artifact'))
          : Promise.resolve(GRADED)))
      render(<SeasonTab />)
      expect(await screen.findByTestId('season-lane-transfers'))
        .toBeInTheDocument()
      expect(screen.queryByTestId('calibration-note')).toBeNull()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })

  it('says no gameweek carries a bench total when every history is unbanked',
    async () => {
      // A graded season whose histories were never banked: four rows, four
      // null bench totals. `bench.length` is 4 and the series is four gaps,
      // so the chart drew an empty axis where the sentence belongs.
      wire({ ...GRADED,
             gws: GRADED.gws.map((row) => ({ ...row,
                                             points_on_bench: null })) })
      render(<SeasonTab />)
      expect(await screen.findByTestId('bench-empty'))
        .toHaveTextContent('No gameweek carries a bench total.')
    })

  it('draws the bench series when even one gameweek carries a total',
    async () => {
      render(<SeasonTab />)
      await screen.findByTestId('season-lane-transfers')
      expect(screen.queryByTestId('bench-empty')).toBeNull()
    })

  it('renders at 390px with no console error', async () => {
    // v11 §Gates' 390px claim, asserted for this view rather than inherited
    // from the hub sweep: Model's cold-clone rail renders only its default
    // tab, which is not this one.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {},
      dispatchEvent: () => false,
    }))
    const { container } = render(<SeasonTab />)
    await screen.findByTestId('season-lane-transfers')
    // The dashboard draws no table, so the no-bare-tables sweep has nothing
    // to say about it; what it must not do is put a fixed width on the page.
    expect(container.querySelectorAll('table')).toHaveLength(0)
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
    vi.unstubAllGlobals()
  })

  it('prints the bench total with the gameweeks it covers', async () => {
    render(<SeasonTab />)
    const card = await screen.findByTestId('season-lane-transfers')
    expect(within(card.closest('div[class*="rounded-card"]')!.parentElement!
      .parentElement!).getByText(/Bench points this season: 7 over 3 GW/))
      .toBeInTheDocument()
  })
})
