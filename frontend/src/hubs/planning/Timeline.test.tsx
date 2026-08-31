import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Timeline from './Timeline'
import { difficultyBackground } from '../../kit'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
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

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(TIMELINE)
})

describe('Timeline', () => {
  it('draws one column per horizon gameweek', async () => {
    render(<Timeline gw={5} />)
    expect(await screen.findByTestId('plan-week-5')).toBeInTheDocument()
    expect(screen.getByTestId('plan-week-6')).toBeInTheDocument()
  })

  it('colours ins sage and outs rust, with prices', async () => {
    render(<Timeline gw={5} />)
    const week = await screen.findByTestId('plan-week-5')
    expect(within(week).getByText(/Wirtz/)).toHaveClass('text-sage')
    expect(within(week).getByText(/Isak/)).toHaveClass('text-rust')
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
    apiGet.mockRejectedValue(Object.assign(
      new Error('no advice for GW5 — run `gaffer advise` first'),
      { status: 404 }))
    render(<Timeline gw={5} />)
    expect(await screen.findByText(/no plan/i)).toBeInTheDocument()
    expect(screen.getByText('Run advise')).toBeInTheDocument()
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
      // The same number and the same function as the ticker square: two ramps
      // for one idea is how two views end up disagreeing about how hard a
      // fixture is, in the same colour scale, on the same page.
      expect(chip).toHaveTextContent('ARS (H)')
      expect(chip.getAttribute('style'))
        .toContain(difficultyBackground(0.7).slice(0, 20))
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
