import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import League from './League'
import Model from './Model'
import Planning from './Planning'
import Players from './Players'
import ThisWeek from './ThisWeek'
import ChipsTab from './planning/ChipsTab'
import DraftsTab from './planning/DraftsTab'
import SensitivityCard from './planning/SensitivityCard'
import type { WhatIfRequest } from '../types'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

// recharts' ResponsiveContainer measures with a ResizeObserver, which jsdom
// does not implement. The chart-bearing suites clone it with a fixed box; this
// file only cares about layout classes, so an inert observer is enough.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function phone() {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: true, media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

beforeEach(() => {
  apiGet.mockReset()
  // Every hub must survive a total absence of artifacts on a phone: the
  // cold-clone-on-mobile case, which is the one that used to crash.
  apiGet.mockRejectedValue(Object.assign(
    new Error('no advice on disk yet — run `gaffer advise` first'),
    { status: 422 }))
  phone()
  vi.stubGlobal('ResizeObserver', NoopResizeObserver)
})

afterEach(() => { vi.unstubAllGlobals() })

describe('hubs on a phone', () => {
  const hubs: Array<[string, () => JSX.Element]> = [
    ['This Week', ThisWeek],
    ['Planning', Planning],
    ['Players', Players],
    ['League', League],
    ['Model', Model],
  ]

  for (const [name, Hub] of hubs) {
    it(`${name} renders an empty state and no console error`, async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<MemoryRouter><Hub /></MemoryRouter>)
      expect(await screen.findByRole('heading', { level: 1 }))
        .toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })
  }
})

describe('a phone screen scrolls nothing sideways', () => {
  const EMPTY_WHATIF: WhatIfRequest = {
    lock: [], ban: [], force_in: [], max_hits: 0, chip: 'none', horizon: null,
  }

  const CHIPS = {
    gw: 5,
    chips: [{ chip: 'wildcard', gw: 5, gain: 9.4, per_week: 3.1,
              threshold: 8.0, play_now: true, note: null }],
    wildcard: null,
  }

  const REPORT = {
    available: true, gw: 5, k: 20, completed: 20, failures: 0, seed: 1,
    horizon: 5, wall_s: 10, generated_at: '2026-08-31T09:00:00+00:00',
    notice: null, modal: null, runner_up: null, margin: null, verdict: null,
    frequencies: [{ kind: 'buy', code: 100, gw: 5, label: 'buy',
                    name: 'Salah', count: 18, frequency: 0.9 }],
  }

  const COMPARE = {
    gw: 5, weeks: 4,
    rows: [{ name: 'the optimum', is_reference: true,
             solved_at: '2026-08-31T09:10:00+00:00', horizon_pts: 210.4,
             expected_pts: 61.5, delta_xpts: 0, hits: 0, chip: null,
             horizon: 4, buys: [], sells: [], captain: null, error: null }],
  }

  function wrapped() {
    for (const table of document.querySelectorAll('table')) {
      // Each table owns its overflow. A page-level scrollbar means one of
      // them is pushing the body, and the reader loses the nav to find out
      // which.
      expect(table.closest('.overflow-x-auto')).not.toBeNull()
    }
  }

  for (const [name, Hub] of [['Model', Model], ['Players', Players]] as
    Array<[string, () => JSX.Element]>) {
    it(`lets ${name}'s tab strip scroll within its own bounds`, async () => {
      render(<MemoryRouter><Hub /></MemoryRouter>)
      const strip = await screen.findByRole('tablist')
      // Five tabs do not fit in 390px. The strip may scroll or wrap; what it
      // may not do is make the page wider than the phone.
      expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
    })
  }

  it("lets Planning's tab strip scroll within its own bounds", async () => {
    apiGet.mockResolvedValue({
      gw: 5, mode: 'weekly', deadline: '2099-09-18T17:30:00Z',
      advice: { expected_pts: 61.5, xi: [], bench: [], buys: [], sells: [],
                captain: null, vice: null },
      staleness: { advice_gw: 5, current_gw: 5,
                   generated_at: '2026-08-29T09:00:00Z',
                   deadline: '2099-09-18T17:30:00Z', deadline_passed: false,
                   stale: false, reason: 'current for GW5',
                   data_through_gw: 4, data_warning: null },
    })
    render(<MemoryRouter><Planning /></MemoryRouter>)
    const strip = await screen.findByRole('tablist')
    expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
  })

  it("lets League's tab strip scroll within its own bounds", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') {
        return Promise.resolve({
          league_id: 1, entry_id: 1,
          standings: [{ entry: 1, name: 'Mine', player_name: 'Me', rank: 1,
                        total: 300, event_total: 60, is_you: true }],
          trajectory: [{ entry: 1, name: 'Mine',
                         points: [{ gw: 5, points: 60, total: 300 }] }],
          gap: [{ gw: 5, gap: 10 }],
          win_probability: [{ name: 'Mine', total: 300, p_win: 0.5 }],
          lam: 1, stance: 'balanced', lam_explained: 'leading',
        })
      }
      if (path === '/api/league/rivals') return Promise.resolve([])
      // The other two degrade to their own empty states by design.
      return Promise.reject(new Error('not on this clone'))
    })
    render(<MemoryRouter><League /></MemoryRouter>)
    const strip = await screen.findByRole('tablist')
    expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
  })

  it('wraps the sensitivity table in its own scroller', async () => {
    apiGet.mockResolvedValue(REPORT)
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    await screen.findByText('Salah')
    wrapped()
  })

  it('wraps the chip table in its own scroller', async () => {
    apiGet.mockResolvedValue(CHIPS)
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await screen.findAllByText(/wildcard/i)
    wrapped()
  })

  it('wraps the draft compare table in its own scroller', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/drafts'
        ? Promise.resolve({ drafts: [] })
        : Promise.resolve({ id: 'j1', status: 'done', result: COMPARE,
                            error: null })))
    render(<MemoryRouter><DraftsTab current={EMPTY_WHATIF} /></MemoryRouter>)
    await screen.findByTestId('empty-state')
    wrapped()
  })
})
