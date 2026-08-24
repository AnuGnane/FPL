import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FixtureTicker from './FixtureTicker'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue({
    gws: [3, 4], source: 'elo',
    teams: [
      { code: 300, name: 'Liverpool', short_name: 'LIV', mean_difficulty: 0.3,
        cells: [{ gw: 3, opponent: 'ARS', home: true, difficulty: 0.2 },
                { gw: 4, opponent: 'CHE', home: false, difficulty: 0.4 }] },
      { code: 301, name: 'Arsenal', short_name: 'ARS', mean_difficulty: 0.6,
        cells: [{ gw: 3, opponent: 'LIV', home: false, difficulty: 0.8 },
                { gw: 4, opponent: 'BOU', home: true, difficulty: 0.4 }] },
    ],
  })
})

describe('FixtureTicker', () => {
  it('renders a cell per team per gameweek, coloured by difficulty',
    async () => {
      render(<FixtureTicker weeks={2} />)
      const cell = await screen.findByTitle('LIV vs ARS (GW3) — 0.2')
      expect(cell).toHaveTextContent('ARS (H)')
      expect(cell.getAttribute('style')).toContain('background')
      expect(screen.getByText(/Elo-implied/)).toBeInTheDocument()
    })

  it('sorts by a gameweek column when its header is clicked', async () => {
    render(<FixtureTicker weeks={2} />)
    await screen.findByText('Liverpool')
    await userEvent.click(screen.getByRole('button', { name: 'GW3' }))
    const names = screen.getAllByRole('rowheader').map((cell) =>
      cell.textContent)
    expect(names).toEqual(['Liverpool', 'Arsenal'])
    await userEvent.click(screen.getByRole('button', { name: 'GW3' }))
    const reversed = screen.getAllByRole('rowheader').map((cell) =>
      cell.textContent)
    expect(reversed).toEqual(['Arsenal', 'Liverpool'])
  })

  it('names the odds source and drops the key notice when odds are in use',
    async () => {
      apiGet.mockResolvedValue({
        gws: [3], source: 'odds',
        teams: [{ code: 300, name: 'Liverpool', short_name: 'LIV',
                  mean_difficulty: 0.2,
                  cells: [{ gw: 3, opponent: 'ARS', home: true,
                            difficulty: 0.2 }] }],
      })
      render(<FixtureTicker weeks={1} />)
      expect(await screen.findByText(/odds-implied/)).toBeInTheDocument()
      expect(screen.queryByText(/add an odds key/i)).not.toBeInTheDocument()
    })

  it('hides the key notice on Elo when a key is already configured',
    async () => {
      render(<FixtureTicker weeks={2} oddsKeyPresent />)
      expect(await screen.findByText(/Elo-implied/)).toBeInTheDocument()
      expect(screen.queryByText(/add an odds key/i)).not.toBeInTheDocument()
    })
})
