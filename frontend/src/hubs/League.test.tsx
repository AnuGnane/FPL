import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import League from './League'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    // The chart itself needs the measured box: cloning it with a fixed one is
    // what the real container does once it has measured.
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 200 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 200 })
          : children}
      </div>
    ),
  }
})

// The field names are the ones `/api/league/race` actually emits
// (`trajectory`, `gap`, `win_probability`) — see web/schemas.py::LeagueRace.
const RACE = {
  league_id: 1234,
  entry_id: 1,
  standings: [
    { entry: 1, name: 'Mine', player_name: 'Me', rank: 1, total: 300,
      event_total: 60, is_you: true },
    { entry: 2, name: 'Ten Hag Hive', player_name: 'Them', rank: 2,
      total: 290, event_total: 55, is_you: false },
  ],
  trajectory: [
    { entry: 1, name: 'Mine',
      points: [{ gw: 4, points: 60, total: 240 },
               { gw: 5, points: 60, total: 300 }] },
    { entry: 2, name: 'Ten Hag Hive',
      points: [{ gw: 4, points: 55, total: 235 },
               { gw: 5, points: 55, total: 290 }] },
  ],
  gap: [{ gw: 5, gap: 10 }],
  win_probability: [{ name: 'Ten Hag Hive', total: 290, p_win: 0.41 }],
  lam: 1.0,
  stance: 'balanced',
  lam_explained: 'second place, chasing',
}

const RIVALS = [
  { entry: 2, name: 'Ten Hag Hive', player_name: 'Them', rank: 2, total: 290,
    event_total: 55, overlap: 11, differentials: 4 },
]

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation((path: string) => (
    path === '/api/league/race' ? Promise.resolve(RACE)
      : path === '/api/league/rivals' ? Promise.resolve(RIVALS)
        : Promise.reject(new Error(`unexpected ${path}`))
  ))
})

describe('League hub', () => {
  it('draws the race chart', async () => {
    const { container } = render(<MemoryRouter><League /></MemoryRouter>)
    await screen.findByText('Ten Hag Hive')
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull()
  })

  it('lists the standings with you marked', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByText('Mine')).toBeInTheDocument()
    expect(screen.getByTestId('standing-1')).toHaveAttribute('data-you', 'true')
  })

  it('links each rival to their detail route', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('tab', { name: 'Rivals' }))
    expect(await screen.findByRole('link', { name: /Ten Hag Hive/ }))
      .toHaveAttribute('href', '/league/rival/2')
  })

  it('shows an empty state naming the config when there is no league',
    async () => {
      apiGet.mockRejectedValue(Object.assign(
        new Error('set fpl.league_id in config.toml first'), { status: 422 }))
      render(<MemoryRouter><League /></MemoryRouter>)
      expect(await screen.findByText(/no league configured/i))
        .toBeInTheDocument()
      expect(screen.getByText('config.toml')).toBeInTheDocument()
    })
})

describe('two rivals with the same team name', () => {
  // FPL does not make team names unique. Keying the chart rows by name meant
  // the second writer of a gameweek overwrote the first, so two managers
  // called "The Invincibles" were drawn as one line and the other vanished.
  const CLASH = {
    ...RACE,
    standings: RACE.standings.map((row) => ({ ...row, name: 'Same Name' })),
    trajectory: RACE.trajectory.map((t) => ({ ...t, name: 'Same Name' })),
  }

  beforeEach(() => {
    apiGet.mockImplementation((path: string) => (
      path.includes('/race') ? Promise.resolve(CLASH)
        : Promise.resolve(RIVALS)))
  })

  it('draws a line per entry, not per name', async () => {
    const { container } = render(<MemoryRouter><League /></MemoryRouter>)
    await screen.findByText('Cumulative points')
    const paths = [...container.querySelectorAll('.recharts-line-curve')]
      .map((node) => node.getAttribute('d'))
    expect(paths).toHaveLength(CLASH.trajectory.length)
    // Keyed by name, both series read the same column, so both lines were
    // drawn through the same points and one manager's season disappeared.
    expect(paths[0]).not.toEqual(paths[1])
  })

  it('keeps both entries distinguishable in the standings', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    await screen.findByText('Cumulative points')
    expect(screen.getByTestId('standing-1')).toBeInTheDocument()
    expect(screen.getByTestId('standing-2')).toBeInTheDocument()
  })
})
