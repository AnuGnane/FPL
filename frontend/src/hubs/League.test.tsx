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
    // Named twice on this tab now: once in standings, once in win probability.
    await screen.findAllByText('Ten Hag Hive')
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
    // Named paths only: a catch-all here handed the league-sim fetch a rival
    // list, which is not a sim payload, and the card blew up on it.
    apiGet.mockImplementation((path: string) => (
      path.includes('/race') ? Promise.resolve(CLASH)
        : path.includes('/rivals') ? Promise.resolve(RIVALS)
          : Promise.reject(new Error(`unexpected ${path}`))))
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

const SIM = {
  gw: 7, entries: 2, weeks_left: 31, n: 2000, seed: 20260831,
  rival_drift: 0.5, p_win: 0.42, p_top3: 1.0, exp_finish: 1.6,
  per_rival: [{ entry: 2, name: 'Ten Hag Hive', p_beat: 0.58 }],
  margin_quantiles: { p05: -60, p25: -12, p50: 18, p75: 50, p95: 120 },
  history: [
    { gw: 5, p_win: 0.3, p_top3: 1, exp_finish: 1.8,
      run_at: '2026-09-05T09:00:00+00:00' },
    { gw: 6, p_win: 0.36, p_top3: 1, exp_finish: 1.7,
      run_at: '2026-09-12T09:00:00+00:00' },
  ],
  field_rate: 54.2, notice: null, legacy_win_probability: [],
}

describe('the simulated win-probability card', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') return Promise.resolve(SIM)
      return Promise.reject(new Error(`unexpected ${path}`))
    })
  })

  it('leads with the simulated title odds, not the pairwise ones', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-p-win')).toHaveTextContent('42%')
    expect(screen.getByTestId('sim-p-top3')).toHaveTextContent('100%')
  })

  it('says how many simulations produced the number', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-provenance'))
      .toHaveTextContent('2,000')
  })

  it('lists every rival with the odds of beating him', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('beat-2')).toHaveTextContent('58%')
  })

  it('draws the sparkline once two gameweeks are banked', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-sparkline')).toBeInTheDocument()
  })

  it('falls back to the parametric table when the sim will not load',
     async () => {
       apiGet.mockImplementation((path: string) => {
         if (path === '/api/league/race') return Promise.resolve(RACE)
         if (path === '/api/league/rivals') return Promise.resolve([])
         return Promise.reject(new Error('422'))
       })
       render(<MemoryRouter><League /></MemoryRouter>)
       expect(await screen.findByTestId('legacy-win-probability'))
         .toBeInTheDocument()
       expect(screen.queryByTestId('sim-p-win')).not.toBeInTheDocument()
     })

  it('shows the notice when no field sample is banked', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') {
        return Promise.resolve({ ...SIM, field_rate: null,
                                 notice: 'no field sample banked' })
      }
      return Promise.reject(new Error('x'))
    })
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByText(/no field sample banked/))
      .toBeInTheDocument()
  })

  it('offers the What if tab', async () => {
    render(<MemoryRouter><League /></MemoryRouter>)
    expect(await screen.findByRole('tab', { name: 'What if' }))
      .toBeInTheDocument()
  })
})
