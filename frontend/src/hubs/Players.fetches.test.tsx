import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../api/pageData'
import Players from './Players'

/**
 * What Players asks the server for, on one render of each tab (v18e §1
 * part 1).
 *
 * The rail counts *paths*, not totals, for the reason `Planning.fetches`
 * gives: a total can hold steady while one artifact quietly stops being
 * asked for. Four hub-level effects (the shared advice read, the explorer's
 * own filtered read, the star column and the pin list) run regardless of
 * which tab is open, so every `it` below carries them; only the panel each
 * tab mounts differs. Committed first against the counts as they stand
 * before the refactor, so this file's own history is the control arm
 * (CONVENTIONS §3, §4).
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
    xi: [], bench: [], captain: null, vice: null, buys: [], sells: [],
  },
}

const ROWS = [
  { code: 1, element: 7, name: 'Salah', position: 'MID', team_code: 300,
    team_name: 'Liverpool', price: 13.0, ep_next: 6.4, ep_horizon: 12.0,
    ownership: 42.1, league_eo: 61.5, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: 1, free_kicks_order: 1,
    corners_order: null, in_squad: true, last4: [2, 9, 5, 12],
    field_eo: 78.0, field_class: 'shield', ep_lo: 5.1, ep_hi: 7.6,
    p_haul: 0.22, p_blank: 0.14 },
  { code: 2, element: 8, name: 'Saka', position: 'MID', team_code: 301,
    team_name: 'Arsenal', price: 10.0, ep_next: 5.5, ep_horizon: 10.5,
    ownership: 30.0, league_eo: 22.0, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: null, free_kicks_order: null,
    corners_order: 1, in_squad: false, last4: [6, 1, 8, 3],
    field_eo: null, field_class: null, ep_lo: 4.4, ep_hi: 6.5,
    p_haul: 0.18, p_blank: 0.16 },
]

const OVERRIDES = { rows: [] }
const WATCHLIST = { rows: [{ code: 1, name: 'Salah', note: '', set_at: '' }] }

const COMPONENTS = { gw: 5, players: [] }
const MATRIX = {
  gws: [5, 6], source: 'dixon_coles',
  teams: [
    { code: 300, name: 'Liverpool', short_name: 'LIV', mean_attack: 0.2,
      mean_defence: 0.3,
      cells: [{ gw: 5, opponent: 'EVE', home: true, attack: 0.1,
                defence: 0.2 },
              { gw: 6, opponent: 'ARS', home: false, attack: 0.8,
                defence: 0.9 }] },
  ],
}

const BODIES: Record<string, unknown> = {
  '/api/advice/latest': ADVICE,
  '/api/players?': ROWS,
  '/api/overrides': OVERRIDES,
  '/api/watchlist': WATCHLIST,
  '/api/components/5': COMPONENTS,
  '/api/fixtures/matrix?from=5&n=6': MATRIX,
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

/** Every hub-level request, made regardless of which tab is open. */
const BASE = {
  '/api/advice/latest': 1,
  '/api/players?': 1,
  '/api/overrides': 1,
  '/api/watchlist': 1,
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

describe('Players, one tab at a time', () => {
  it('asks for these paths on the default (Explorer) tab', async () => {
    render(<MemoryRouter initialEntries={['/players']}><Players /></MemoryRouter>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/watchlist'))
    expect(counted()).toEqual({ ...BASE })
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiDelete).not.toHaveBeenCalled()
  })

  it('asks for these paths on the Compare tab', async () => {
    render(<MemoryRouter initialEntries={['/players?tab=compare']}>
      <Players />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/fixtures/matrix?from=5&n=6'))
    expect(counted()).toEqual({
      ...BASE,
      // ComparePanel's own decomposition and fixture reads fire regardless
      // of how many players are ticked — nothing is ticked on a first
      // render, and the panel shows its own "pick two" empty state, but the
      // effect above that empty state has already asked for both.
      '/api/components/5': 1,
      '/api/fixtures/matrix?from=5&n=6': 1,
    })
  })

  it('asks for these paths on the Fixture matrix tab', async () => {
    render(<MemoryRouter initialEntries={['/players?tab=matrix']}>
      <Players />
    </MemoryRouter>)
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/fixtures/matrix?from=5&n=6'))
    // One, where the control arm recorded two. FixtureMatrix used to mount
    // with `from={gw ?? 1}` before `/api/advice/latest` had resolved and ask
    // for gameweek 1's matrix — an answer nothing ever rendered — then ask
    // again once `gw` became 5. Since v19b §2.6 it is passed `null` until the
    // gameweek is known and the first request never fires. This is the only
    // count this cycle moves on Players, and it moved down.
    expect(counted()).toEqual({
      ...BASE,
      '/api/fixtures/matrix?from=5&n=6': 1,
    })
  })

  it('asks for these paths on the Watchlist tab', async () => {
    render(<MemoryRouter initialEntries={['/players?tab=watchlist']}>
      <Players />
    </MemoryRouter>)
    // One, where the control arm recorded two: the hub's own star column and
    // WatchlistTab's list are the same URL, and since v18e both read it
    // through the one cache entry instead of each asking for itself. This is
    // the only count the conversion moved, and it moved down.
    await waitFor(() => expect(
      apiGet.mock.calls.filter((c) => c[0] === '/api/watchlist').length,
    ).toBe(1))
    expect(counted()).toEqual({
      ...BASE,
      // was 2: the star column and the watchlist tab each asked; one cache now.
      '/api/watchlist': 1,
    })
  })
})
