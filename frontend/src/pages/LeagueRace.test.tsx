import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LeagueRace from './LeagueRace'

// vi.mock's factory is hoisted above the file body, so the spy has to be
// hoisted with it.
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const RACE = {
  league_id: 5,
  entry_id: 1,
  standings: [
    {
      entry: 2, name: 'Ten Hag Hive', player_name: 'Riv', rank: 1,
      total: 190, event_total: 60, is_you: false,
    },
    {
      entry: 1, name: 'You FC', player_name: 'Me', rank: 2, total: 106,
      event_total: 55, is_you: true,
    },
  ],
  trajectory: [
    {
      entry: 1,
      name: 'You FC',
      points: [
        { gw: 1, points: 51, total: 51 },
        { gw: 2, points: 55, total: 106 },
      ],
    },
    {
      entry: 2,
      name: 'Ten Hag Hive',
      points: [
        { gw: 1, points: 90, total: 90 },
        { gw: 2, points: 100, total: 190 },
      ],
    },
  ],
  gap: [{ gw: 1, gap: -39 }, { gw: 2, gap: -84 }],
  win_probability: [{ name: 'Ten Hag Hive', total: 190, p_win: 0.14 }],
  lam: 0.4,
  stance: 'chase',
  lam_explained: 'λ +0.40: you are 84 points behind Ten Hag Hive…',
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(RACE)
})

describe('League Race', () => {
  it('renders standings, charts, win probability and the λ explainer',
    async () => {
      render(<MemoryRouter><LeagueRace /></MemoryRouter>)
      // The rival's name is in the standings, the chart legend and the
      // win-probability table, so query the standings link specifically.
      expect(await screen.findByRole('link', { name: 'Ten Hag Hive' }))
        .toHaveAttribute('href', '/league/rivals/2')
      const yourRow = screen.getAllByText('You FC')
        .map((el) => el.closest('tr')).find(Boolean)
      expect(yourRow?.className).toContain('you')
      expect(screen.getByLabelText('Points by gameweek')).toBeInTheDocument()
      expect(screen.getByLabelText('Gap to the leader')).toBeInTheDocument()
      expect(screen.getByText('14%')).toBeInTheDocument()
      expect(screen.getByText(/84 points behind/)).toBeInTheDocument()
    })

  it('offers a retry when the FPL API is down', async () => {
    apiGet.mockRejectedValue(new Error('FPL API unavailable — retry'))
    render(<MemoryRouter><LeagueRace /></MemoryRouter>)
    expect(await screen.findByText(/FPL API unavailable/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
