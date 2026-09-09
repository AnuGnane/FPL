import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ThisWeek from './ThisWeek'

/**
 * What This Week asks the server for, on one render (v17h §1 part 2).
 *
 * The rail counts *paths*, not requests: the claim the cycle gates on is
 * "each endpoint once", and a total that merely falls would also be satisfied
 * by a card quietly losing its data. Committed first against the counts as
 * they stood before the conversion, so this file's own history is the control
 * arm (CONVENTIONS §3, §4).
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
  staleness: {
    advice_gw: 5, current_gw: 5, generated_at: '2026-08-29T09:00:00Z',
    deadline: '2099-09-18T17:30:00Z', deadline_passed: false, stale: false,
    reason: 'current for GW5', data_through_gw: 4, data_warning: null,
  },
}

const BODIES: Record<string, unknown> = {
  '/api/advice/latest': ADVICE,
  '/api/players': [],
  '/api/components/5': { gw: 5, players: [] },
  '/api/components/5?codes=1,2': { gw: 5, players: [] },
  '/api/league/leagues': {
    gw: 5, focus_league_id: null, focus_name: null, focus_stance: 'auto',
    focus_lam: 0, focus_warning: null, stance: 'auto', private: [], public: [],
  },
  '/api/jobs/current': null,
  '/api/decisions/5': {
    gw: 5, reason: null, text: '', at: null, state: 'before_deadline',
    deadline: '2099-09-18T17:30:00Z', grade: null,
  },
  '/api/ladder': { gw: 5, gws: [5], free_transfers: 1,
                   cap: { max_hits: 2, max_transfers: null },
                   cap_rung: null, cap_rung_requested: null, rungs: [] },
  '/api/settings': { rows: [], unavailable: [], overlay_error: null,
                     apply_note: '' },
  // Prose, so BriefCard renders itself and its two digest buttons rather than
  // handing over to DigestCard — four JobButtons on the page, which is the
  // shape the duplicate probe shows up in.
  '/api/brief': { gw: 5, prose: 'The week.', note: null, checked_at: null,
                  model_command: 'llm', fallback: null },
  '/api/advice/diff?gw=5': {
    gw: 5, available: false, changed: false, current_at: null,
    previous_at: null, buys_added: [], buys_dropped: [], sells_added: [],
    sells_dropped: [], captain_from: null, captain_to: null, chip_from: null,
    chip_to: null, expected_pts_delta: 0, ep_movers: [], ep_movers_count: null,
  },
  '/api/overrides': { rows: [] },
  '/api/news/5': { gw: 5, moved: 0, rows: [] },
  '/api/confidence': { captain: null },
}

/** Every path asked for, in the order asked, one entry per request. */
function asked(): string[] {
  return apiGet.mock.calls.map((c) => c[0] as string)
}

/** path -> how many times it was requested. */
function counted(): Record<string, number> {
  const out: Record<string, number> = {}
  for (const path of asked()) out[path] = (out[path] ?? 0) + 1
  return out
}

beforeEach(() => {
  apiGet.mockReset()
  // Its own spy, not the GET one. Nothing on This Week deletes today, and a
  // delete that arrived on the render path sharing a spy would land silently
  // in the multiset below as though it were a read.
  apiDelete.mockReset()
  apiDelete.mockResolvedValue(null)
  apiGet.mockImplementation((path: string) => (path in BODIES
    ? Promise.resolve(BODIES[path])
    : Promise.reject(new Error(`unexpected path ${path}`))))
  apiPost.mockReset()
  apiPost.mockRejectedValue(new Error('no sim'))
})

describe("This Week's first render", () => {
  it('asks for exactly these paths, exactly this many times', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await waitFor(() =>
      expect(asked()).toContain('/api/confidence'))
    await waitFor(() => expect(asked()).toContain('/api/news/5'))
    expect(counted()).toEqual({
      '/api/advice/latest': 1,
      '/api/players': 1,
      '/api/components/5': 1,
      '/api/components/5?codes=1,2': 1,
      '/api/league/leagues': 1,
      '/api/jobs/current': 4,
      '/api/decisions/5': 1,
      '/api/ladder': 1,
      '/api/settings': 1,
      '/api/brief': 1,
      '/api/advice/diff?gw=5': 1,
      '/api/overrides': 1,
      '/api/news/5': 1,
      '/api/confidence': 1,
    })
    expect(apiDelete).not.toHaveBeenCalled()
  })

  it('makes seventeen GETs in all', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await waitFor(() => expect(asked()).toContain('/api/confidence'))
    await waitFor(() => expect(asked()).toContain('/api/news/5'))
    expect(asked()).toHaveLength(17)
  })
})
