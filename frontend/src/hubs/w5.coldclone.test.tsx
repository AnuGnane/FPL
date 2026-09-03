/**
 * The cold-clone rail for W5's three new views (v12 W5, plan Task 13).
 *
 * `coldclone.test.tsx` renders each hub's *default* tab only, so a tab added
 * behind a `Tabs.Trigger` is never mounted there and its empty state is never
 * checked — v11 A18's finding, unchanged. These are written per view for that
 * reason.
 *
 * Two shapes of "cold", because the server has two. The Settings and Watchlist
 * endpoints answer a tree with nothing in it with a **200** — an empty panel
 * carrying the server's own sentence about what to do next — so a rail that
 * only rejected every request would test the transport failing and never the
 * cold clone at all. Both are asserted: the served-empty case names the action,
 * and the rejected case still reaches an EmptyState rather than a blank screen.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsTab from './model/SettingsTab'
import WatchlistTab from './players/WatchlistTab'
import PlannerBoard from './planning/PlannerBoard'

const { apiGet, apiPost, apiDelete, ApiError } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  // The real client throws this, and views branch on it to tell "nothing
  // built yet" from "something broke". The cold clone must be rejected with
  // the same shape or the branch under test never runs.
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
}))

vi.mock('../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiDelete: (path: string) => apiDelete(path),
  errorText: (e: unknown) => String(
    (e as { detail?: { error?: unknown } })?.detail?.error ?? e,
  ),
}))

/** What `GET /api/settings` really returns on a tree with no config.toml —
 *  copied from the endpoint's own answer, not invented here. */
const COLD_SETTINGS = {
  rows: [],
  unavailable: ['horizon', 'decay', 'itb_value', 'bench_curve', 'lambda_cap',
    'decision_priors', 'top_n', 'price_timing', 'draw_availability'],
  overlay_error: 'no config.toml — copy config.example.toml to config.toml '
    + 'and set fpl.entry_id and fpl.league_id',
  apply_note: 'Saved to config.local.toml.',
}

/** A plan with no trace on any week — every artifact written before W5, and
 *  every one written since by a build whose solve state could not be read. */
const UNTRACED = {
  gw: 5,
  generated_at: '2026-09-01T09:00:00Z',
  bank: 1.5,
  alternatives: [],
  weeks: [{ gw: 5, buys: [], sells: [], hits: 0, hit_cost: 0, chip: null,
            captain: null, vice: null, expected_pts: 61.5, bank: 1.5 }],
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiDelete.mockReset()
})

function reject() {
  apiGet.mockRejectedValue(
    new ApiError('no advice on disk yet — run `gaffer advise` first'))
}

describe('a cold clone, view by view', () => {
  it('Settings names the file to copy, from the server\'s own sentence',
    async () => {
      apiGet.mockResolvedValue(COLD_SETTINGS)
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<SettingsTab />)
      const empty = await screen.findByTestId('empty-state')
      expect(empty).toHaveTextContent('config.example.toml')
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })

  it('Settings still reaches an EmptyState when the request itself fails',
    async () => {
      reject()
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<SettingsTab />)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })

  it('the Watchlist points at the Explorer\'s star', async () => {
    apiGet.mockResolvedValue({ rows: [] })
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<WatchlistTab onChange={vi.fn()} />)
    const empty = await screen.findByTestId('empty-state')
    expect(empty).toHaveTextContent(/Explorer/)
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('the Watchlist still reaches an EmptyState when the request fails',
    async () => {
      reject()
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<WatchlistTab onChange={vi.fn()} />)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })

  it('a week with no trace draws no "Why this move" control at all',
    async () => {
      // Not an empty disclosure: a control that opens on nothing is a promise
      // the payload cannot keep, and the reader has no way to tell it from a
      // week whose moves genuinely cost nothing.
      apiGet.mockImplementation((path: string) => (
        path.startsWith('/api/prices/movers')
          ? Promise.resolve({ available: true, as_of: null, rows: [] })
          : Promise.resolve(UNTRACED)))
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<PlannerBoard gw={5} />)
      expect(await screen.findByTestId('board-week-5')).toBeInTheDocument()
      expect(screen.queryByTestId('board-why-5')).toBeNull()
      expect(screen.queryByText('Why this move')).toBeNull()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })

  it('the board still reaches an EmptyState with nothing on disk', async () => {
    reject()
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<PlannerBoard gw={5} />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})
