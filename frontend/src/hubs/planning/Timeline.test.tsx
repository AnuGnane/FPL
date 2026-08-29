import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Timeline from './Timeline'

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
