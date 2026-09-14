import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Timeline from './Timeline'
import { difficultyTone } from '../../kit'

const { ApiError, apiGet } = vi.hoisted(() => {
  // `usePageData` narrows on `instanceof ApiError` to fill `status`, and
  // `Timeline` splits a failed read on that status (v18e ruling 7) — so a
  // double whose rejections are plain Errors would exercise the broken-server
  // branch on every test that means the cold clone.
  class ApiError extends Error {
    status: number
    detail: unknown = null
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
  return { ApiError, apiGet: vi.fn() }
})

vi.mock('../../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
  // `usePageData` reads every rejection through this, so a double that
  // omitted it would make the failure path throw rather than render.
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

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
}

/** The ticker window this plan asks for, with no cells for anybody. The
 *  tint is a separate suite's subject; what matters here is that the second
 *  read is answered with a *ticker*. Answering it with the plan used to build
 *  a map from `undefined.teams` inside a promise nobody awaited, which the
 *  runner swallowed; the same mistake is now a render. */
const TICKER = { gws: [5, 6], source: 'elo', teams: [] }

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation((path: string) => Promise.resolve(
    path.startsWith('/api/fixtures/ticker') ? TICKER : TIMELINE))
})

describe('Timeline', () => {
  it('draws one column per horizon gameweek', async () => {
    render(<Timeline gw={5} />)
    expect(await screen.findByTestId('plan-week-5')).toBeInTheDocument()
    expect(screen.getByTestId('plan-week-6')).toBeInTheDocument()
  })

  it('colours ins up and outs down, with prices', async () => {
    render(<Timeline gw={5} />)
    const week = await screen.findByTestId('plan-week-5')
    expect(within(week).getByText(/Wirtz/)).toHaveClass('text-up')
    expect(within(week).getByText(/Isak/)).toHaveClass('text-down')
    expect(within(week).getByText(/8.5/)).toBeInTheDocument()
  })

  it('prices a hit as an explicit cost chip', async () => {
    render(<Timeline gw={5} />)
    const week = await screen.findByTestId('plan-week-5')
    expect(within(week).getByText('-4')).toBeInTheDocument()
  })

  it('badges the chip on the week that plays it', async () => {
    render(<Timeline gw={5} />)
    const week = await screen.findByTestId('plan-week-6')
    expect(within(week).getByText('bboost')).toBeInTheDocument()
  })

  it('renders a dash where no armband was recorded', async () => {
    render(<Timeline gw={5} />)
    const week = await screen.findByTestId('plan-week-6')
    expect(within(week).getByTestId('plan-captain-6')).toHaveTextContent('—')
  })

  it('shows an empty state naming the run when there is no plan', async () => {
    apiGet.mockRejectedValue(new ApiError(
      404, 'no advice for GW5 — run `gaffer advise` first'))
    render(<Timeline gw={5} />)
    expect(await screen.findByText(/no plan/i)).toBeInTheDocument()
    expect(screen.getByText('Run advise')).toBeInTheDocument()
  })

  it('shows the same empty state for the cold clone\'s 422', async () => {
    // The 404 above is `/api/plan`'s own; a clone with nothing on disk never
    // reaches it, because the read raises a `GafferError` the app-wide handler
    // maps to 422 (app.py:67-69). Both mean "run the job" (v18e ruling 7).
    apiGet.mockRejectedValue(new ApiError(
      422, 'no advice on disk yet — run `gaffer advise` first'))
    render(<Timeline gw={5} />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText('Run advise')).toBeInTheDocument()
  })

  it('says the server broke rather than that nothing has been solved',
    async () => {
      apiGet.mockRejectedValue(new ApiError(500, 'boom'))
      render(<Timeline gw={5} />)
      const callout = await screen.findByText('boom')
      expect(callout.closest('[data-tone="error"]')).toBeInTheDocument()
      expect(screen.queryByText(/no plan to draw/i)).not.toBeInTheDocument()
    })
})

describe('Timeline difficulty chips', () => {
  const TICKER = {
    gws: [5], source: 'odds',
    teams: [{
      code: 43, name: 'Man City', short_name: 'MCI', mean_difficulty: 0.5,
      cells: [{ gw: 5, opponent: 'ARS', home: true, difficulty: 0.7 }],
    }],
  }

  function mockBoth() {
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/plan/')) return Promise.resolve(TIMELINE)
      if (path.startsWith('/api/fixtures/ticker')) {
        return Promise.resolve(TICKER)
      }
      return Promise.reject(new Error(`unexpected ${path}`))
    })
  }

  it('tints each named team by the ticker\'s own difficulty for that week',
    async () => {
      mockBoth()
      render(<Timeline gw={5} teamByCode={new Map([[3, 43]])} />)
      const chip = await screen.findByTestId('gw-fixture-43-5')
      // The same number and the same function as the ticker square: two
      // scales for one idea is how two views end up disagreeing about how
      // hard a fixture is, on the same page. 0.7 is above the hard cut.
      expect(chip).toHaveTextContent('ARS (H)')
      expect(chip).toHaveAttribute('data-tone', difficultyTone(0.7))
    })

  it('draws no strip for a gameweek the ticker payload does not cover',
    async () => {
      // Spec D6: absent, not guessed. A horizon that runs past the ticker's
      // window is the ordinary case in the last weeks of a season.
      mockBoth()
      render(<Timeline gw={5} teamByCode={new Map([[3, 43]])} />)
      expect(await screen.findByTestId('plan-week-6')).toBeInTheDocument()
      expect(screen.queryByTestId('gw-strip-6')).not.toBeInTheDocument()
    })

  it('draws no strip at all when the ticker fetch fails', async () => {
    // The timeline is the feature; the tint is a decoration on it. A failed
    // decoration must cost the decoration and nothing else.
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/plan/')
        ? Promise.resolve(TIMELINE)
        : Promise.reject(new Error('ticker down'))))
    render(<Timeline gw={5} teamByCode={new Map([[3, 43]])} />)
    expect(await screen.findByTestId('plan-week-5')).toBeInTheDocument()
    expect(screen.queryByTestId('gw-strip-5')).not.toBeInTheDocument()
  })

  it('draws nothing for a player the advice payload never named', async () => {
    mockBoth()
    render(<Timeline gw={5} teamByCode={new Map()} />)
    expect(await screen.findByTestId('plan-week-5')).toBeInTheDocument()
    expect(screen.queryByTestId('gw-strip-5')).not.toBeInTheDocument()
  })
})
