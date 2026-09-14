import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../api/pageData'
import Live from './Live'

/**
 * What Live asks the server for, on one render (v18e §1 part 1).
 *
 * The rail counts *paths*, not a total, for the reason `Planning.fetches`
 * gives: a total that held could still hide the one artifact this hub reads
 * quietly dropping out. Live polls `/api/live` every `POLL_MS` (60s), so the
 * test unmounts before the interval can fire rather than reaching for fake
 * timers — the claim being pinned is the first render's request, not the
 * poll loop, and the first render finishes well inside 60s of real time.
 * Committed first against the count as it stands before the refactor, so
 * this file's own history is the control arm (CONVENTIONS §3, §4).
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
      <div style={{ width: 400, height: 220 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 220 })
          : children}
      </div>
    ),
  }
})

const LIVE = {
  active: true, gw: 3, my_points: 66, matches_in_play: 2,
  players: [{ element: 7, code: 100, name: 'Salah', position: 'MID',
              multiplier: 2, points: 9, provisional_bonus: 3, minutes: 90,
              status: 'playing', tier_eo: 143.5, tier_eo_se: 2.1,
              selected_by_percent: 45, projected_out: false,
              projected_in: false, sub_partner: null, sub_reason: null,
              remaining_ep: 0 }],
  table: [{ entry: 1, name: 'You', pre_total: 106, live: 66, projected: 172,
            delta: 1, projected_live: 66, remaining_ep: 1.5, race: 67.5 }],
  notice: null,
  my_projected_points: 70,
  my_race: 71.5,
  race_reference: 61.5,
  race_series: [
    { at: '2026-08-31T14:00:00+00:00', you: 40, rival: 38 },
    { at: '2026-08-31T14:01:00+00:00', you: 71.5, rival: 44 },
  ],
  safety: [],
  rival_name: 'Above',
  race_notice: null,
}

const BODIES: Record<string, unknown> = {
  '/api/live': LIVE,
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

describe("Live's first render", () => {
  it('asks for exactly these paths, exactly this many times', async () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/live']}><Live /></MemoryRouter>,
    )
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/live'))
    expect(counted()).toEqual({ '/api/live': 1 })
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiDelete).not.toHaveBeenCalled()
    // Unmounted before POLL_MS (60s) so the interval this hub sets up on
    // mount never fires and never adds a second `/api/live` to the count
    // above — the claim here is the first render's request, not the loop.
    unmount()
  })
})
