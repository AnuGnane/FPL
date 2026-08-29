import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Live from './Live'

// vi.mock's factory is hoisted above the file body, so the spy has to be
// hoisted with it.
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const ACTIVE = {
  active: true, gw: 3, my_points: 66, matches_in_play: 2,
  players: [{ element: 7, code: 100, name: 'Salah', position: 'MID',
              multiplier: 2, points: 9, provisional_bonus: 3, minutes: 90,
              status: 'playing', tier_eo: 143.5, tier_eo_se: 2.1,
              selected_by_percent: 45 }],
  table: [{ entry: 1, name: 'You', pre_total: 106, live: 66, projected: 172,
            delta: 1 }],
  notice: null,
}

const NO_TIER = {
  ...ACTIVE,
  players: [{ ...ACTIVE.players[0], tier_eo: null, tier_eo_se: null,
              selected_by_percent: null }],
  notice: 'top-10k EO unavailable (429) — league EO only',
}

const IDLE = {
  active: false, gw: null, my_points: 0, matches_in_play: 0, players: [],
  table: [],
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(ACTIVE)
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

describe('Live', () => {
  it('shows points, provisional bonus and the projected table', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    // "66" is both your running total and your row in the live table.
    expect(screen.getAllByText('66')).toHaveLength(2)
    expect(screen.getByText(/2 match/)).toBeInTheDocument()
    expect(screen.getByText(/provisional/i)).toBeInTheDocument()
    expect(screen.getByText('+3')).toBeInTheDocument()
    expect(screen.getByText('172')).toBeInTheDocument()
    expect(screen.getByText('▲1')).toBeInTheDocument()
  })

  it('polls every 60 seconds while a gameweek is live', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(apiGet).toHaveBeenCalledTimes(1)
    await act(() => vi.advanceTimersByTimeAsync(60000))
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('stops polling once the page unmounts', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    let unmount = () => {}
    await act(async () => {
      unmount = render(<MemoryRouter><Live /></MemoryRouter>).unmount
    })
    expect(apiGet).toHaveBeenCalledTimes(1)
    unmount()
    await act(() => vi.advanceTimersByTimeAsync(180000))
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('says nothing is on when no gameweek is live and stops polling',
    async () => {
      apiGet.mockResolvedValue(IDLE)
      await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
      expect(screen.getByText(/no gameweek in progress/i)).toBeInTheDocument()
      await act(() => vi.advanceTimersByTimeAsync(120000))
      expect(apiGet).toHaveBeenCalledTimes(1)
    })

  it('shows the sampled top-10k EO with its error bar', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('Top 10k EO')).toBeInTheDocument()
    expect(screen.getByText('143.5% ±2.1')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('renders the table and a notice when tier EO is unavailable', async () => {
    apiGet.mockResolvedValue(NO_TIER)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getAllByText('–').length).toBeGreaterThan(0)
    expect(screen.getByText(/top-10k EO unavailable/)).toBeInTheDocument()
  })

  // The suite runs on fake timers, under which RTL's `findBy*` never settles,
  // so these three flush with `act` like every test above them.
  it('heads the page with the live gameweek', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByRole('heading', { level: 1, name: /live/i }))
      .toBeInTheDocument()
  })

  it('offers an auto-poll toggle', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByRole('checkbox', { name: /auto-refresh/i }))
      .toBeInTheDocument()
  })

  it('shows an empty state between gameweeks', async () => {
    apiGet.mockResolvedValue({ active: false, gw: null, my_points: 0,
                               matches_in_play: 0, players: [], table: [] })
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText(/no gameweek in progress/i)).toBeInTheDocument()
  })
})
