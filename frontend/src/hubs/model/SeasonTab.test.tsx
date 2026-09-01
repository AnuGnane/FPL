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

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue({ gws: [], summary: null })
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
      apiGet.mockResolvedValue({ gws: [gw()], summary: summary() })
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

  beforeEach(() => { apiGet.mockResolvedValue(GRADED) })

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

  it('prints the bench total with the gameweeks it covers', async () => {
    render(<SeasonTab />)
    const card = await screen.findByTestId('season-lane-transfers')
    expect(within(card.closest('div[class*="rounded-card"]')!.parentElement!
      .parentElement!).getByText(/Bench points this season: 7 over 3 GW/))
      .toBeInTheDocument()
  })
})
