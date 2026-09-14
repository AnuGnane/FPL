import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../api/pageData'
import Model from './Model'

/**
 * What Model asks the server for, on one render of each tab, and across a
 * tab walk (v18e §1 part 1).
 *
 * The rail counts *paths*, not totals, for the reason `Planning.fetches`
 * gives: a total that held could still hide one artifact quietly dropping
 * out. The header's six JobButtons share one `/api/jobs/current` probe
 * (v17h §6) regardless of which tab is open, so every `it` below carries it.
 * The three-tab walk exists because Quality, Review and Season all read
 * `/api/review`: before v18e §2.3 they read it independently and a manager
 * who opened all three in one visit asked for it three times, which is the
 * number this file was committed against as the control arm (CONVENTIONS §3,
 * §4). It is now one, and the walk below is where that shows — the per-tab
 * counts above it did not move, because no tab asks for anything new and none
 * asked twice on its own.
 */

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn(),
}))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiDelete: (path: string) => apiDelete(path),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
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

const QUALITY = {
  benchmark: null, current: null, decomposition: null, flag_latency: null,
  news_shadow: null, presser_grades: null,
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
  ],
  cumulative: {}, omitted: {}, per_gw_omitted: {}, excluded: [],
  missing: [], note: null,
}

const PENS = {
  gws: [], notes: [], season: '2026-27',
  season_totals: { players: 0, penalties: 0 },
}

// A graded lane, not an empty ledger: SeasonTab only mounts its own
// `CalibrationTrend` (a second read of `/api/model/calibration`) once
// `summary` shows a graded lane, and the three-tab walk below needs that
// second read to happen to state the true count.
const LANES = [
  { lane: 'transfers', delta_pts: -7, delta_pwin: -0.3, label: 'Blunder',
    aligned: false, mine: 'no move', model: 'Blank->Guehi', note: null },
  { lane: 'captaincy', delta_pts: 4, delta_pwin: 0.2, label: 'Brilliant',
    aligned: false, mine: 'Salah', model: 'Haaland', note: null },
  { lane: 'bench', delta_pts: 0, delta_pwin: 0, label: 'Aligned',
    aligned: true, mine: 'A, B', model: 'A, B', note: null },
  { lane: 'chip', delta_pts: null, delta_pwin: 0, label: null,
    aligned: false, mine: 'none', model: 'wildcard', note: null },
]
const REVIEW = {
  gws: [{
    gw: 2, reviewed_at: '2026-09-01T09:00:00+00:00', no_advice: false,
    post_deadline: false, my_points: 61, official_points: 61,
    official_gross: 65, hits: 1, reconciled: true, chip: null,
    model_chip: 'bboost', points_on_bench: 5, overall_rank: 412233,
    projection_snapshot: null, projection_post_deadline: false,
    our_bench_points: 5, model_points: 68, accuracy: 89, pwin_n: 2000,
    pwin_seed: 20260831, pwin_granularity_pp: 0.05, lanes: LANES,
    misses: [], hindsight: { points: 74, xi: [], captain: 3, gap: 13 },
    notices: [], decision: null,
  }],
  summary: {
    gws: [2], lanes: {
      transfers: { pts: -7, pwin: -0.3, graded: 1, wins: 0, losses: 1 },
      captaincy: { pts: 4, pwin: 0.2, graded: 1, wins: 1, losses: 0 },
      bench: { pts: 0, pwin: 0, graded: 1, wins: 0, losses: 0 },
      chip: { pts: 0, pwin: 0, graded: 0, wins: 0, losses: 0 },
    },
    accuracy: [{ gw: 2, accuracy: 89 }], points_on_bench: 5,
    points_on_bench_gws: 1, hindsight_gap: 13, hindsight_gap_gws: 1,
    reconciled_gws: 1, unreconciled_gws: 0,
    best: { ...LANES[1], gw: 2 }, worst: { ...LANES[0], gw: 2 },
    by_reason: [],
  },
}

const MISSES = { gw: null, rows: [] }

const JOURNAL = { built_at: null, cumulative: [], rows: [] }

const HISTORY = { runs: [], prices: [], backtests: [] }

const HEALTH = {
  data: [], models: [], odds_key_present: false,
  launchd: { log: '', present: false, modified_at: null, last_line: null },
  model_health: null, artifacts: [],
}

const SETTINGS = { rows: [], unavailable: [], overlay_error: null,
                    apply_note: '' }

const BODIES: Record<string, unknown> = {
  '/api/jobs/current': null,
  '/api/quality': QUALITY,
  '/api/model/calibration': CALIBRATION,
  '/api/pens': PENS,
  '/api/review': REVIEW,
  '/api/misses': MISSES,
  '/api/journal': JOURNAL,
  '/api/history': HISTORY,
  '/api/health': HEALTH,
  '/api/settings': SETTINGS,
}

/** path -> how many times it was requested. */
function counted(): Record<string, number> {
  const out: Record<string, number> = {}
  for (const call of apiGet.mock.calls) {
    const path = call[0] as string
    out[path] = (out[path] ?? 0) + 1
  }
  return out
}

beforeEach(() => {
  resetPageData()
  apiGet.mockReset()
  apiDelete.mockReset()
  apiDelete.mockRejectedValue(new Error('no write on render'))
  apiGet.mockImplementation((path: string) => (path in BODIES
    ? Promise.resolve(BODIES[path])
    : Promise.reject(new Error(`unexpected path ${path}`))))
  apiPost.mockReset()
  apiPost.mockRejectedValue(new Error('no write on render'))
})

describe('Model, one tab at a time', () => {
  it('asks for these paths on the default (Quality) tab', async () => {
    render(<MemoryRouter initialEntries={['/model']}><Model /></MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/misses'))
    expect(counted()).toEqual({
      '/api/jobs/current': 1,
      '/api/quality': 1,
      '/api/model/calibration': 1,
      '/api/pens': 1,
      '/api/review': 1,
      '/api/misses': 1,
    })
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiDelete).not.toHaveBeenCalled()
  })

  it('asks for these paths on the Journal tab', async () => {
    render(<MemoryRouter initialEntries={['/model?tab=journal']}>
      <Model />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/journal'))
    expect(counted()).toEqual({
      '/api/jobs/current': 1,
      '/api/journal': 1,
    })
  })

  it('asks for these paths on the Review tab', async () => {
    render(<MemoryRouter initialEntries={['/model?tab=review']}>
      <Model />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/review'))
    expect(counted()).toEqual({
      '/api/jobs/current': 1,
      '/api/review': 1,
    })
  })

  it('asks for these paths on the Season tab', async () => {
    render(<MemoryRouter initialEntries={['/model?tab=season']}>
      <Model />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/model/calibration'))
    expect(counted()).toEqual({
      '/api/jobs/current': 1,
      '/api/model/calibration': 1,
      '/api/review': 1,
    })
  })

  it('asks for these paths on the History tab', async () => {
    render(<MemoryRouter initialEntries={['/model?tab=history']}>
      <Model />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/history'))
    expect(counted()).toEqual({
      '/api/jobs/current': 1,
      '/api/history': 1,
    })
  })

  it('asks for these paths on the Health tab', async () => {
    render(<MemoryRouter initialEntries={['/model?tab=health']}>
      <Model />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/health'))
    expect(counted()).toEqual({
      '/api/jobs/current': 1,
      '/api/health': 1,
    })
  })

  it('asks for these paths on the Settings tab', async () => {
    render(<MemoryRouter initialEntries={['/model?tab=settings']}>
      <Model />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/settings'))
    expect(counted()).toEqual({
      '/api/jobs/current': 1,
      '/api/settings': 1,
    })
  })
})

describe('Model, walking three tabs in one visit', () => {
  it('asks for /api/review once crossing Quality, Review and Season',
    async () => {
      render(<MemoryRouter initialEntries={['/model']}><Model /></MemoryRouter>)
      // Quality (the default tab) reads /api/review through ScatterSection.
      await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/misses'))

      await userEvent.click(screen.getByRole('tab', { name: 'Review' }))
      // The Review tab's own cards, painted from the entry Quality's scatter
      // already holds — which is the whole claim: the tab renders without
      // asking. Waited for, not merely asserted, so the case would fail if
      // the tab were still pending rather than served.
      await screen.findByTestId('season-transfers')

      await userEvent.click(screen.getByRole('tab', { name: 'Season' }))
      await screen.findByTestId('season-lane-transfers')

      // One request for the ledger and one for the calibration report, both
      // shared: Radix still remounts a tab's content fresh every time it
      // becomes active, and since v18e §2.3 a remount is served from the
      // cache instead of asking again.
      expect(counted()).toEqual({
        '/api/jobs/current': 1,
        '/api/quality': 1,
        '/api/model/calibration': 1,
        '/api/pens': 1,
        '/api/review': 1,
        '/api/misses': 1,
      })
    })
})
