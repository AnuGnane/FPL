import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Players from './Players'

// vi.mock's factory is hoisted above the file body, so the spy has to be
// hoisted with it (same pattern as WhatIf.test.tsx).
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const ROWS = [
  { code: 100, element: 7, name: 'Salah', position: 'MID', team_code: 300,
    team_name: 'Liverpool', price: 13.0, ep_next: 6.4, ep_horizon: 11.5,
    ownership: 45.0, league_eo: 62.5, available: true, status: 'a',
    news: '', chance_of_playing: null, penalties_order: 1,
    free_kicks_order: 1, corners_order: 2, in_squad: true },
  { code: 101, element: 8, name: 'Bloke', position: 'DEF', team_code: 301,
    team_name: 'Arsenal', price: 4.5, ep_next: 2.0, ep_horizon: 4.2,
    ownership: 5.0, league_eo: 0.0, available: false, status: 'd',
    news: 'knock - 75%', chance_of_playing: 75, penalties_order: null,
    free_kicks_order: null, corners_order: null, in_squad: false },
]

const EXPLAIN = {
  code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
  ep_next: 6.4,
  fixtures: [{
    gw: 3, opponent: 'Arsenal', home: true, kickoff_time: null,
    components: [{ label: 'Attacking', points: 2.71 }],
    minutes: { p_play: 0.95, p60: 0.88 }, calibration_delta: 0.5,
    odds: { weight: 0, e_goals_against: null, p_cs_model: 0.25,
            p_cs_blended: 0.25, e_gc_model: 1.4, e_gc_blended: 1.4 },
    ep: 6.4,
  }],
  next_fixtures: [], set_pieces: { penalties: 1, free_kicks: 1, corners: 2 },
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/players/100/explain')) return EXPLAIN
    if (path.startsWith('/api/players')) return ROWS
    throw new Error(`unexpected GET ${path}`)
  })
})

describe('Players', () => {
  it('renders the pool with price, EP, EO and availability', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    expect(await screen.findByText('Salah')).toBeInTheDocument()
    expect(screen.getByText('13')).toBeInTheDocument()
    expect(screen.getByText('62.5')).toBeInTheDocument()
    expect(screen.getByTitle('knock - 75%')).toBeInTheDocument()
    expect(screen.getByText('1 / 1 / 2')).toBeInTheDocument()
  })

  it('passes filters and sort through to the API', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await screen.findByText('Salah')
    await userEvent.selectOptions(screen.getByLabelText('Position'), 'DEF')
    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(expect.stringContaining(
        'position=DEF')))
    await userEvent.type(screen.getByLabelText('Search'), 'blo')
    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(expect.stringContaining(
        'search=blo')))
    await userEvent.selectOptions(screen.getByLabelText('Sort'), 'price')
    await waitFor(() =>
      expect(apiGet).toHaveBeenCalledWith(expect.stringContaining(
        'sort=price')))
  })

  it('debounces the search box instead of fetching per keystroke',
    async () => {
      render(<MemoryRouter><Players /></MemoryRouter>)
      await screen.findByText('Salah')
      apiGet.mockClear()
      await userEvent.type(screen.getByLabelText('Search'), 'bloke')
      await waitFor(() =>
        expect(apiGet).toHaveBeenCalledWith(expect.stringContaining(
          'search=bloke')))
      expect(apiGet).toHaveBeenCalledTimes(1)
    })

  it('opens the shared explain modal from a player name', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Salah' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Attacking')
    expect(dialog).toHaveTextContent(/Add an odds key/)
  })
})
