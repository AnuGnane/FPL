/**
 * v12 W5 §6.1 — the four hubs that have tabs, deep-linked.
 *
 * One file rather than four additions, because the claim is about all four at
 * once: every hub with a `Tabs.Root` reads `?tab=` and writes it back. Live
 * and This Week have no tabs and are deliberately absent.
 *
 * Model and Players render their strip on a cold clone and are tested that
 * way: every fetch rejected. League and Planning do not, and that is their own
 * pre-existing answer rather than something §6.1 changes — League replaces the
 * whole hub with "No league configured" when `/api/league/race` fails
 * (`League.tsx:113`), and Planning with "Nothing planned yet" when there is no
 * advice (`Planning.tsx:75`). Both are deliberate empty states with no tab
 * strip in them at all, so those two hubs are given the one payload each needs
 * to get past its own gate and no more. The claim under test is the same for
 * all four: the strip reads `?tab=` and writes it back.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import League from './League'
import Model from './Model'
import Planning from './Planning'
import Players from './Players'

const { apiGet, ApiError } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
}))

vi.mock('../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  errorText: (e: unknown) => String(e),
}))

// League's Race tab is the one that draws, and `ResponsiveContainer` reaches
// for a `ResizeObserver` jsdom does not have. The same clone-with-a-fixed-box
// stand-in `League.test.tsx:15-30` already uses.
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

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

// The minimum each hub needs to render a tab strip at all. `cold` is the
// honest default; the two entries below are the two hubs whose own empty state
// stands in front of the strip.
const RACE = {
  league_id: 1, entry_id: 1, standings: [], trajectory: [], gap: [],
  win_probability: [], lam: 1, stance: 'balanced', lam_explained: '',
}

const WARM: Record<string, (path: string) => Promise<unknown>> = {
  League: (path) => (path === '/api/league/race' ? Promise.resolve(RACE)
    : path === '/api/league/rivals' ? Promise.resolve([])
      : Promise.reject(new ApiError('cold'))),
  Planning: (path) => (path === '/api/advice/latest'
    ? Promise.resolve({ gw: 5, advice: {} })
    : Promise.reject(new ApiError('cold'))),
}

function serve(hub: string) {
  const warm = WARM[hub]
  if (warm) apiGet.mockImplementation(warm)
}

function Search() {
  return <span data-testid="search">{useLocation().search}</span>
}

function show(node: React.ReactNode, at: string) {
  render(
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route path="*" element={<>{node}<Search /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockRejectedValue(new ApiError('cold'))
})

describe('the tab in the URL', () => {
  it.each([
    ['Model', <Model key="m" />, '/model', 'Health', 'health'],
    ['Players', <Players key="p" />, '/players', 'Fixture matrix', 'matrix'],
    ['League', <League key="l" />, '/league', 'Rivals', 'rivals'],
    ['Planning', <Planning key="n" />, '/planning', 'Chips', 'chips'],
    // v12 W5 §6.3: the watchlist joined the strip after the hook did, so this
    // row is here to hold `TABS` and the hook's whitelist together.
    ['Players', <Players key="pw" />, '/players', 'Watchlist', 'watchlist'],
  ])('%s opens the tab the link names', async (name, node, at, label, value) => {
    serve(name)
    show(node, `${at}?tab=${value}`)
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: label }))
        .toHaveAttribute('data-state', 'active')
    })
  })

  it.each([
    ['Model', <Model key="m" />, '/model', 'Health', 'health'],
    ['Players', <Players key="p" />, '/players', 'Fixture matrix', 'matrix'],
    ['League', <League key="l" />, '/league', 'Rivals', 'rivals'],
    ['Planning', <Planning key="n" />, '/planning', 'Chips', 'chips'],
  ])('%s writes the tab it was clicked to', async (name, node, at, label, value) => {
    serve(name)
    show(node, at)
    await userEvent.click(await screen.findByRole('tab', { name: label }))
    await waitFor(() => {
      expect(screen.getByTestId('search').textContent).toBe(`?tab=${value}`)
    })
  })

  it.each([
    ['Model', <Model key="m" />, '/model', 'Quality'],
    ['Players', <Players key="p" />, '/players', 'Explorer'],
    ['League', <League key="l" />, '/league', 'Race'],
    ['Planning', <Planning key="n" />, '/planning', 'Timeline'],
  ])('%s ignores a tab it does not have', async (name, node, at, first) => {
    serve(name)
    show(node, `${at}?tab=not-a-tab`)
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: first }))
        .toHaveAttribute('data-state', 'active')
    })
  })
})
