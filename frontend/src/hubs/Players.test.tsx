import {
  act, render, screen, waitFor, within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Players from './Players'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiDelete: vi.fn(),
}))

vi.mock('./players/ComparePanel', () => ({
  default: ({ players }: { players: Array<{ code: number }> }) => (
    <p>comparing {players.length}</p>
  ),
}))
vi.mock('./players/FixtureMatrix', () => ({ default: () => <p>matrix panel</p> }))

const ROWS = [
  { code: 1, element: 7, name: 'Salah', position: 'MID', team_code: 300,
    team_name: 'Liverpool', price: 13.0, ep_next: 6.4, ep_horizon: 12.0,
    ownership: 42.1, league_eo: 61.5, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: 1, free_kicks_order: 1,
    corners_order: null, in_squad: true, last4: [2, 9, 5, 12],
    field_eo: 78.0, field_class: 'shield' },
  { code: 2, element: 8, name: 'Saka', position: 'MID', team_code: 301,
    team_name: 'Arsenal', price: 10.0, ep_next: 5.5, ep_horizon: 10.5,
    ownership: 30.0, league_eo: 22.0, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: null, free_kicks_order: null,
    corners_order: 1, in_squad: false, last4: [6, 1, 8, 3],
    field_eo: null, field_class: null },
]

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiPost.mockResolvedValue({ active: true, rows: [], warning: null })
  apiGet.mockImplementation((path: string) => (
    path.startsWith('/api/players') ? Promise.resolve(ROWS)
      : path === '/api/overrides'
        ? Promise.resolve({ active: true, rows: [], warning: null })
        : path === '/api/advice/latest'
        ? Promise.resolve({ gw: 5, mode: 'weekly',
                            deadline: '2099-09-18T17:30:00Z', advice: {},
                            staleness: { advice_gw: 5, current_gw: 5,
                                         generated_at: '2026-08-29T09:00:00Z',
                                         deadline: '2099-09-18T17:30:00Z',
                                         deadline_passed: false, stale: false,
                                         reason: 'current for GW5',
                                         data_through_gw: 4,
                                         data_warning: null } })
        : Promise.reject(new Error(`unexpected ${path}`))
  ))
})

describe('Players hub', () => {
  it('lists the pool', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    expect(await screen.findByText('Salah')).toBeInTheDocument()
    expect(screen.getByText('Saka')).toBeInTheDocument()
  })

  it('filters by position through the query string', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await screen.findByText('Salah')
    const filters = screen.getByRole('group', { name: 'Position' })
    await userEvent.click(within(filters).getByRole('button', { name: 'DEF' }))
    expect(apiGet).toHaveBeenCalledWith(expect.stringContaining('position=DEF'))
  })

  it('paints the active position filter in that position’s own hue', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await screen.findByText('Salah')
    const filters = screen.getByRole('group', { name: 'Position' })
    const def = within(filters).getByRole('button', { name: 'DEF' })
    expect(def.style.color).toBe('')
    await userEvent.click(def)
    expect(def).toHaveAttribute('aria-pressed', 'true')
    expect(def.style.color).toBe('var(--color-pos-def)')
  })

  it('selects players for comparison and counts them', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await screen.findByText('Salah')
    await userEvent.click(screen.getByRole('checkbox', { name: /compare Salah/i }))
    await userEvent.click(screen.getByRole('checkbox', { name: /compare Saka/i }))
    await userEvent.click(screen.getByRole('tab', { name: 'Compare' }))
    expect(await screen.findByText('comparing 2')).toBeInTheDocument()
  })

  it('shows the fixture matrix tab', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('tab',
                                                  { name: 'Fixture matrix' }))
    expect(await screen.findByText('matrix panel')).toBeInTheDocument()
  })

  it('shows an empty state naming the run when the pool is unavailable',
    async () => {
      apiGet.mockImplementation((path: string) => (
        path.startsWith('/api/players')
          ? Promise.reject(Object.assign(
            new Error('no saved solve state — run `gaffer advise` first'),
            { status: 422 }))
          : Promise.resolve({ gw: 5, mode: 'weekly',
                              deadline: '2099-09-18T17:30:00Z', advice: {},
                              staleness: { advice_gw: 5, current_gw: 5,
                                           generated_at: '2026-08-29T09:00:00Z',
                                           deadline: '2099-09-18T17:30:00Z',
                                           deadline_passed: false,
                                           stale: false,
                                           reason: 'current for GW5',
                                           data_through_gw: 4,
                                           data_warning: null } })
      ))
      render(<MemoryRouter><Players /></MemoryRouter>)
      expect(await screen.findByText(/no candidate pool/i)).toBeInTheDocument()
      expect(screen.getByText('Run advise')).toBeInTheDocument()
    })

  // gw === null meant both "still loading" and "there is nothing to load",
  // so a failed /api/advice/latest left the Compare tab on "Loading…" for ever.
  it('offers the run instead of loading for ever when advice is missing',
    async () => {
      apiGet.mockImplementation((path: string) => (
        path.startsWith('/api/players') ? Promise.resolve(ROWS)
          : Promise.reject(new Error('no advice on disk yet'))
      ))
      render(<MemoryRouter><Players /></MemoryRouter>)
      await screen.findByText('Salah')
      await userEvent.click(screen.getByRole('tab', { name: 'Compare' }))
      const empty = await screen.findByTestId('empty-state')
      expect(empty).toHaveTextContent(/advise/i)
      expect(screen.queryByText('Loading…')).toBeNull()
    })

  it('still says Loading while the advice request is in flight', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/players') ? Promise.resolve(ROWS)
        : new Promise(() => {})      // never settles
    ))
    render(<MemoryRouter><Players /></MemoryRouter>)
    await screen.findByText('Salah')
    await userEvent.click(screen.getByRole('tab', { name: 'Compare' }))
    expect(await screen.findByText('Loading…')).toBeInTheDocument()
    expect(screen.queryByTestId('empty-state')).toBeNull()
  })

  it('debounces the search box into one request', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      render(<MemoryRouter><Players /></MemoryRouter>)
      await screen.findByText('Salah')
      apiGet.mockClear()
      await userEvent.type(screen.getByLabelText('Search'), 'Salah')
      await act(async () => { vi.advanceTimersByTime(400) })
      const searches = apiGet.mock.calls
        .map(([path]) => String(path))
        .filter((path) => path.includes('search='))
      // One request for the settled word, not one per keystroke.
      expect(searches).toHaveLength(1)
      expect(searches[0]).toContain('search=Salah')
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows an em dash rather than a nought when the field is unknown',
     async () => {
       // A 0 here would read as "the top 10k have written him off", which is
       // a claim, and we have not measured it.
       render(<MemoryRouter><Players /></MemoryRouter>)
       expect(await screen.findByText('—')).toBeInTheDocument()
     })

  it('makes every explorer name the click-to-explain control', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Salah' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saka' })).toBeInTheDocument()
  })

  it('opens the pin dialog from a row, for that row', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: 'pin Saka' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAttribute('aria-label', 'Pin availability for Saka')
    expect(within(dialog).getByLabelText('probability of playing'))
      .toBeInTheDocument()
  })

  it('pins through the overrides endpoint and closes', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: 'pin Salah' }))
    await userEvent.type(screen.getByLabelText('probability of playing'), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Pin' }))
    expect(apiPost).toHaveBeenCalledWith('/api/overrides',
      { code: 1, p_play: 1, e_min: null, note: '' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })

  it('marks the row it has just pinned', async () => {
    // The dialog hands back the whole panel; the table is the one place the
    // manager can see which of his own numbers are standing.
    apiPost.mockResolvedValue({
      active: true, warning: null,
      rows: [{ code: 1, name: 'Salah', p_play: 1, e_min: null, note: '',
               set_at: '2026-08-31T09:00:00+00:00', model_p_play: 0.8,
               model_e_min: 60 }],
    })
    render(<MemoryRouter><Players /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: 'pin Salah' }))
    await userEvent.type(screen.getByLabelText('probability of playing'), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Pin' }))
    expect(await screen.findByRole('button', { name: 'pin Salah' }))
      .toHaveTextContent('Pinned')
    expect(screen.getByRole('button', { name: 'pin Saka' }))
      .toHaveTextContent('Pin')
  })
})
