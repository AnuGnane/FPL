import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../api/pageData'
import Planning from './Planning'

/**
 * What Planning asks the server for, on one render of each tab (v18e §1 part
 * 1).
 *
 * The rail counts *paths*, not totals: the claim a refactor must not break is
 * "this tab still reads the same wires", and a total that merely held would
 * also be satisfied by one tab losing a read while another gained one. Each
 * tab gets its own `it` because Radix mounts only the active `Tabs.Content`,
 * so a tab's requests are invisible to every other tab's assertion. Committed
 * first against the counts as they stand before the refactor, so this file's
 * own history is the control arm (CONVENTIONS §3, §4).
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

const ADVICE = {
  gw: 5,
  mode: 'weekly',
  deadline: '2099-09-18T17:30:00Z',
  advice: {
    gw: 5, deadline: '2099-09-18T17:30:00Z', expected_pts: 61.5, hits: 1,
    xi: [{ code: 1, name: 'Salah', position: 'MID', ep: 6.4 }],
    bench: [{ code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6 }],
    captain: { code: 1, name: 'Salah', ep: 6.4 },
    vice: { code: 2, name: 'Gabriel', ep: 4.6 },
    buys: [], sells: [],
  },
}

const TIMELINE = {
  gw: 5,
  generated_at: '2026-08-29T09:00:00Z',
  weeks: [
    {
      gw: 5,
      buys: [{ code: 1, name: 'Wirtz', position: 'MID', ep: 6.1, price: 8.5 }],
      sells: [{ code: 2, name: 'Isak', position: 'FWD', ep: 3.2, price: 9.1 }],
      hits: 1, hit_cost: 4, chip: null,
      captain: { code: 3, name: 'Salah', position: 'MID', ep: 6.4, price: 13 },
      vice: { code: 4, name: 'Saka', position: 'MID', ep: 5.5, price: 10 },
      expected_pts: 61.5,
    },
    {
      gw: 6, buys: [], sells: [], hits: 0, hit_cost: 0, chip: 'bboost',
      captain: null, vice: null, expected_pts: 58.0,
    },
  ],
  bank: 1.5,
  alternatives: [],
}

const TICKER_2 = {
  gws: [5, 6], source: 'elo',
  teams: [{ code: 300, name: 'Liverpool', short_name: 'LIV',
            mean_difficulty: 0.2,
            cells: [{ gw: 5, opponent: 'EVE', home: true, difficulty: 0.2 },
                    { gw: 6, opponent: 'ARS', home: false,
                      difficulty: 0.8 }] }],
}

const TICKER_6 = {
  gws: [5, 6, 7, 8, 9, 10], source: 'elo',
  teams: [{ code: 300, name: 'Liverpool', short_name: 'LIV',
            mean_difficulty: 0.3,
            cells: [{ gw: 5, opponent: 'EVE', home: true, difficulty: 0.2 }] }],
}

const TICKER_8 = {
  gws: [5, 6, 7, 8, 9, 10, 11, 12], source: 'elo',
  teams: [{ code: 300, name: 'Liverpool', short_name: 'LIV',
            mean_difficulty: 0.3,
            cells: [{ gw: 5, opponent: 'EVE', home: true, difficulty: 0.2 }] }],
}

const MOVERS = { available: true, as_of: null, rows: [] }

const SENSITIVITY = {
  available: true, gw: 5, k: 20, completed: 20, failures: 0, seed: 20260831,
  horizon: 5, wall_s: 41.2, generated_at: '2026-08-31T09:00:00+00:00',
  notice: null,
  frequencies: [
    { kind: 'buy', code: 100, gw: 5, label: 'buy', name: 'Salah',
      count: 18, frequency: 0.9 },
  ],
  modal: null, runner_up: null, margin: 1.24,
  verdict: 'nine of ten re-solves bought Salah',
}

const OVERRIDES = {
  active: true,
  rows: [
    { code: 100, name: 'Salah', p_play: 1.0, e_min: 88, note: 'saw training',
      set_at: '2026-08-31T09:00:00+00:00', model_p_play: 0.82,
      model_e_min: 71.0 },
  ],
}

const LADDER = { gw: 5, gws: [5], free_transfers: 1,
                  cap: { max_hits: 2, max_transfers: null },
                  cap_rung: null, cap_rung_requested: null, rungs: [] }

const SETTINGS = { rows: [], unavailable: [], overlay_error: null,
                    apply_note: '' }

const CHIPS = {
  gw: 5,
  chips: [
    { chip: 'wildcard', gw: 5, gain: 9.4, per_week: 3.1, threshold: 8.0,
      play_now: true, note: null },
  ],
  wildcard: {
    gain_over_horizon: 9.4, recommend: true, threshold: 8.0,
    threshold_source: 'theta',
    kept: [{ code: 100, name: 'Salah', position: 'MID', price: 13, ep: 6.4 }],
    dropped: [{ code: 101, name: 'Watkins', position: 'FWD', price: 9,
                ep: 4.1 }],
    added: [{ code: 102, name: 'Wirtz', position: 'MID', price: 8.5,
              ep: 5.2 }],
  },
}

const DRAFTS = {
  drafts: [
    { name: 'keep Salah', created_at: '2026-08-31T09:00:00+00:00',
      constraints: { lock: [], ban: [], force_in: [], force_out: [],
                     max_hits: 0, max_transfers: null, chip: 'none',
                     horizon: null } },
  ],
}

const HEALTH = {
  data: [], models: [], odds_key_present: false,
  launchd: { log: '', present: false, modified_at: null, last_line: null },
  model_health: null, artifacts: [],
}

const BODIES: Record<string, unknown> = {
  '/api/advice/latest': ADVICE,
  '/api/plan/5': TIMELINE,
  '/api/fixtures/ticker?weeks=2': TICKER_2,
  '/api/fixtures/ticker?weeks=6': TICKER_6,
  '/api/fixtures/ticker?weeks=8': TICKER_8,
  '/api/prices/movers': MOVERS,
  '/api/sensitivity': SENSITIVITY,
  '/api/overrides': OVERRIDES,
  '/api/ladder': LADDER,
  '/api/settings': SETTINGS,
  '/api/chips': CHIPS,
  '/api/drafts': DRAFTS,
  '/api/health': HEALTH,
  '/api/jobs/current': null,
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

describe('Planning, one tab at a time', () => {
  it('asks for these paths on the default (Timeline) tab', async () => {
    render(<MemoryRouter initialEntries={['/planning']}>
      <Planning />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/fixtures/ticker?weeks=2'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/plan/5': 1,
      '/api/fixtures/ticker?weeks=2': 1,
    })
  })

  it('asks for these paths on the Board tab', async () => {
    render(<MemoryRouter initialEntries={['/planning?tab=board']}>
      <Planning />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/prices/movers'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/plan/5': 1,
      '/api/prices/movers': 1,
    })
  })

  it('asks for these paths on the What-If tab', async () => {
    render(<MemoryRouter initialEntries={['/planning?tab=whatif']}>
      <Planning />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/fixtures/ticker?weeks=6'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/ladder': 1,
      '/api/settings': 1,
      '/api/sensitivity': 1,
      '/api/overrides': 1,
      '/api/fixtures/ticker?weeks=6': 1,
      // SensitivityCard's action is a JobButton (kind="sensitivity"), and a
      // kind-keyed job probes /api/jobs/current once on mount to recover a
      // run already in flight (v17h §6).
      '/api/jobs/current': 1,
    })
  })

  it('asks for these paths on the Chips tab', async () => {
    render(<MemoryRouter initialEntries={['/planning?tab=chips']}>
      <Planning />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/chips'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/chips': 1,
    })
  })

  it('asks for these paths on the Drafts tab', async () => {
    render(<MemoryRouter initialEntries={['/planning?tab=drafts']}>
      <Planning />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/drafts'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/drafts': 1,
    })
  })

  it('asks for these paths on the Ticker tab', async () => {
    render(<MemoryRouter initialEntries={['/planning?tab=ticker']}>
      <Planning />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/fixtures/ticker?weeks=8'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/health': 1,
      '/api/fixtures/ticker?weeks=8': 1,
    })
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiDelete).not.toHaveBeenCalled()
  })
})
