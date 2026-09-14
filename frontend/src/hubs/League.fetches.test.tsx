import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../api/pageData'
import League from './League'

/**
 * What League asks the server for, on one render (v18e §1 part 1).
 *
 * The rail counts *paths*, not a total, for the reason `Planning.fetches`
 * gives: a total that held could still hide one artifact quietly dropping
 * out. League's four own reads (`leagues`, `race`, `rivals`, `sim`) are
 * hub-level effects, not gated by which of the four tabs is open — Leagues,
 * Race, Rivals and What if all read the same overview and race data the hub
 * already fetched — so one render covers every tab's request set and one
 * `it` pins it. Committed first against the counts as they stand before the
 * refactor, so this file's own history is the control arm (CONVENTIONS §3,
 * §4) — and the v18e §2.3 conversion of all four reads onto `usePageData`
 * left every count where it was, which is the whole of what this rail had to
 * say about it: no path is asked more often and none is new.
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

const ADVICE = {
  gw: 5,
  mode: 'weekly',
  deadline: '2099-09-18T17:30:00Z',
  advice: {
    gw: 5, deadline: '2099-09-18T17:30:00Z', expected_pts: 61.5, hits: 1,
    xi: [], bench: [], captain: null, vice: null, buys: [], sells: [],
  },
}

const OVERVIEW = {
  focus_league_id: 1234, focus_name: 'Focus FC League', stance: 'auto',
  focus_stance: 'chase', focus_lam: 0.31, focus_warning: null, gw: 5,
  private: [
    { league_id: 1234, name: 'Focus FC League', rank: 15, last_rank: 80,
      entries: 138, started: true, gap: 12, gap_kind: 'behind',
      would: 'chase', is_focus: true },
  ],
  public: [
    { league_id: 314, name: 'Overall', rank: 430473, last_rank: 2562053,
      entries: 10409391 },
  ],
}

const RACE = {
  league_id: 1234,
  entry_id: 1,
  standings: [
    { entry: 1, name: 'Mine', player_name: 'Me', rank: 1, total: 300,
      event_total: 60, is_you: true },
  ],
  trajectory: [
    { entry: 1, name: 'Mine',
      points: [{ gw: 5, points: 60, total: 300 }] },
  ],
  gap: [{ gw: 5, gap: 10 }],
  win_probability: [{ name: 'Rival', total: 290, p_win: 0.41 }],
  lam: 1.0,
  stance: 'balanced',
  lam_explained: 'second place, chasing',
  league_name: 'Focus FC League',
  focus: true,
  stance_source: 'auto',
}

const RIVALS = [
  { entry: 2, name: 'Rival', player_name: 'Them', rank: 2, total: 290,
    event_total: 55, overlap: 11, differentials: 4 },
]

const SIM = {
  gw: 5, entries: 2, weeks_left: 31, n: 2000, seed: 20260831,
  rival_drift: 0.5, p_win: 0.42, p_top3: 1.0, exp_finish: 1.6,
  per_rival: [{ entry: 2, name: 'Rival', p_beat: 0.58 }],
  margin_quantiles: { p05: -60, p25: -12, p50: 18, p75: 50, p95: 120 },
  history: [], field_rate: 54.2, notice: null, legacy_win_probability: [],
}

const BODIES: Record<string, unknown> = {
  '/api/advice/latest': ADVICE,
  '/api/league/leagues': OVERVIEW,
  '/api/league/race': RACE,
  '/api/league/rivals': RIVALS,
  '/api/league/sim': SIM,
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

describe("League's first render", () => {
  it('asks for exactly these paths, exactly this many times', async () => {
    render(<MemoryRouter initialEntries={['/league']}><League /></MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/league/sim'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/league/leagues': 1,
      '/api/league/race': 1,
      '/api/league/rivals': 1,
      '/api/league/sim': 1,
    })
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiDelete).not.toHaveBeenCalled()
  })
})
