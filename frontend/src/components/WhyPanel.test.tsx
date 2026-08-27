import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WhyPanel from './WhyPanel'

const { FakeApiError, apiGet } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn() }
})

vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const COMPONENTS = {
  gw: 5,
  players: [
    {
      code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
      ep: 6.4,
      fixtures: [{
        gw: 5, opponent: 'ARS', home: true,
        kickoff_time: '2026-09-05T14:00:00Z',
        components: [
          { label: 'Minutes', points: 1.9 },
          { label: 'Goals', points: 2.6 },
          { label: 'Penalty duty', points: 0.31 },
        ],
        minutes: { p_play: 0.96, p60: 0.9 },
        ep: 6.4,
      }],
    },
  ],
}

const DIFF = {
  gw: 5, available: true, changed: true,
  previous_at: '2026-09-03T09:00:00+00:00',
  current_at: '2026-09-04T09:00:00+00:00',
  buys_added: [{ code: 201, name: 'Wirtz' }],
  buys_dropped: [{ code: 200, name: 'Isak' }],
  sells_added: [], sells_dropped: [],
  captain_from: { code: 100, name: 'Salah' },
  captain_to: { code: 101, name: 'Haaland' },
  chip_from: null, chip_to: 'bboost',
  expected_pts_delta: 2.5,
}

const CODES = [100]

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation((path: string) => (
    path.startsWith('/api/components')
      ? Promise.resolve(COMPONENTS)
      : Promise.resolve(DIFF)))
})

describe('WhyPanel', () => {
  it('asks only for the players the plan actually shows', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(apiGet).toHaveBeenCalledWith('/api/components/5?codes=100')
  })

  it('expands a player into his additive terms', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /salah/i }))
    expect(screen.getByText('Goals')).toBeInTheDocument()
    expect(screen.getByText('2.6')).toBeInTheDocument()
    expect(screen.getByText('Penalty duty')).toBeInTheDocument()
    expect(screen.getByText(/vs ARS/)).toBeInTheDocument()
  })

  it('shows what changed since the previous run', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/since last run/i)).toBeInTheDocument()
    expect(screen.getByText(/Wirtz/)).toBeInTheDocument()
    expect(screen.getByText(/Isak/)).toBeInTheDocument()
    expect(screen.getByText(/Salah → Haaland/)).toBeInTheDocument()
    expect(screen.getByText(/\+2.5/)).toBeInTheDocument()
  })

  it('shows no strip at all when there is no previous run', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components')
        ? Promise.resolve(COMPONENTS)
        : Promise.resolve({ gw: 5, available: false, changed: false })))
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(screen.queryByText(/since last run/i)).not.toBeInTheDocument()
  })

  it('hides itself when no components file exists', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components')
        ? Promise.reject(new FakeApiError(404, 'no component breakdown'))
        : Promise.resolve({ gw: 5, available: false, changed: false })))
    const { container } = render(
      <MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })
})
