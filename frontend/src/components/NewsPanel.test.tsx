import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NewsPanel from './NewsPanel'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const MOVED = {
  gw: 5,
  moved: 2,
  rows: [
    {
      code: 1, name: 'Gibbs-White', team_name: "Nott'm Forest",
      p_play_news: 0.0, p_play_flags: 0.75,
      e_min_news: 0.0, e_min_flags: 62.0,
      status: 'd', chance_of_playing: 75,
      official_note: 'Knock - 75% chance of playing',
      injury_type: 'knock', expected_return_gw: 6, p_start_hint: 0.0,
      lineup_hint: 'out', source: 'premierinjuries|lineups',
      fetched_at: '2026-09-04T08:00:00Z',
    },
    {
      code: 2, name: 'Fit Lad', team_name: 'Arsenal',
      p_play_news: 0.8, p_play_flags: 0.9,
      e_min_news: 70.0, e_min_flags: 80.0,
      status: 'a', chance_of_playing: null, official_note: null,
      injury_type: null, expected_return_gw: null, p_start_hint: 0.5,
      lineup_hint: 'doubt', source: 'lineups', fetched_at: 'x',
    },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(MOVED)
})

describe('NewsPanel', () => {
  it('counts the players the layer moved', async () => {
    render(<MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    expect(await screen.findByText(/news moved 2 players/i))
      .toBeInTheDocument()
  })

  it('shows both sides of each prediction', async () => {
    render(<MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await screen.findByText('Gibbs-White')
    expect(screen.getByText('0% / 75%')).toBeInTheDocument()
    expect(screen.getByText('0 / 62')).toBeInTheDocument()
  })

  it('spells out the sources that fired', async () => {
    render(<MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await screen.findByText('Gibbs-White')
    expect(screen.getByText(/official 75%/i)).toBeInTheDocument()
    expect(screen.getByText(/knock, back GW6/i)).toBeInTheDocument()
    expect(screen.getByText(/line-up: out/i)).toBeInTheDocument()
  })

  it('says nothing at all when the layer moved nobody', async () => {
    apiGet.mockResolvedValue({ gw: 5, moved: 0, rows: [] })
    const { container } = render(
      <MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })

  it('says nothing at all when the endpoint fails', async () => {
    apiGet.mockRejectedValue(new Error('nope'))
    const { container } = render(
      <MemoryRouter><NewsPanel gw={5} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })
})
