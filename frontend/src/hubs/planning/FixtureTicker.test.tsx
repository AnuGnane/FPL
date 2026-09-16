import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FixtureTicker from './FixtureTicker'

const { FakeApiError, apiGet } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status = 0
    detail: unknown = null
  }
  return { FakeApiError, apiGet: vi.fn() }
})

vi.mock('../../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
  // `usePageData` reads the real one to turn a rejection into a card's error
  // string (v17h §2), so the mock must carry it for the two refusals below.
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

/** A rejection with a status, which is what the status split reads. */
const refusal = (status: number, text: string) =>
  Object.assign(new FakeApiError(text), { status })

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
      expect(cell).toHaveAttribute('data-tone', 'up')
      expect(screen.getByText(/Elo-implied/)).toBeInTheDocument()
    })

  it('sorts by a gameweek column when its header is clicked', async () => {
    render(<FixtureTicker weeks={2} />)
    await screen.findByText('Liverpool')
    await userEvent.click(screen.getByRole('button', { name: /^GW3/ }))
    const names = screen.getAllByRole('rowheader').map((cell) =>
      cell.textContent)
    expect(names).toEqual(['Liverpool', 'Arsenal'])
    await userEvent.click(screen.getByRole('button', { name: /^GW3/ }))
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

  // v19b §2.6 settles what v18e ruling 7 left open here. A 404 and a 422 both
  // mean "nothing on disk yet, run the job", which is an empty state; a 500
  // is a server that broke, and a page must never render a failure as a
  // healthy empty.
  it('shows an empty state when there is no snapshot to rate', async () => {
    apiGet.mockRejectedValue(refusal(422, 'live/teams.parquet is missing'))
    render(<FixtureTicker weeks={2} />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText('No fixtures yet')).toBeInTheDocument()
    expect(screen.getByText('Refresh data')).toBeInTheDocument()
  })

  it('says the same for a route that declares the artifact absent',
    async () => {
      apiGet.mockRejectedValue(refusal(404, 'no ticker'))
      render(<FixtureTicker weeks={2} />)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    })

  it('keeps the error callout for a server that broke', async () => {
    apiGet.mockRejectedValue(refusal(500, 'the ticker blew up'))
    render(<FixtureTicker weeks={2} />)
    expect(await screen.findByText('the ticker blew up')).toBeInTheDocument()
    expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument()
  })

  it('hides the key notice on Elo when a key is already configured',
    async () => {
      render(<FixtureTicker weeks={2} oddsKeyPresent />)
      expect(await screen.findByText(/Elo-implied/)).toBeInTheDocument()
      expect(screen.queryByText(/add an odds key/i)).not.toBeInTheDocument()
    })
})
